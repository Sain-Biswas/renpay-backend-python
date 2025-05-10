from fastapi import APIRouter, Depends, HTTPException, status, Query
from app.services.supabase_client import get_supabase
from app.models.transaction import Transaction, TransactionCreate, TransactionUpdate, TransactionType
from app.dependencies import get_current_user
from typing import List, Optional
from datetime import datetime, timezone
from uuid import UUID

router = APIRouter()

def json_serializer(obj):
    """Custom JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, type):  # Handle class types
        return obj.__name__
    if hasattr(obj, '__str__'):  # Handle other objects with string representation
        return str(obj)
    raise TypeError(f"Type {type(obj)} not serializable")

async def update_account_balance(supabase, account_id: UUID, amount: float, transaction_type: TransactionType, is_new: bool = True):
    """
    Update account balance based on transaction type.
    If is_new is True, we're adding a new transaction.
    If is_new is False, we're removing a transaction.
    """
    if not account_id:
        return
    
    # Get current account balance
    account_result = supabase.table("accounts").select("*").eq("id", str(account_id)).execute()
    if not account_result.data or len(account_result.data) == 0:
        return
    
    account = account_result.data[0]
    current_balance = account["balance"]
    new_balance = current_balance
    
    # Calculate new balance based on transaction type
    if transaction_type == TransactionType.SALE:
        # Sales increase the balance
        new_balance = current_balance + (amount if is_new else -amount)
    elif transaction_type == TransactionType.EXPENSE:
        # Expenses decrease the balance
        new_balance = current_balance - (amount if is_new else -amount)
    elif transaction_type == TransactionType.TRANSFER:
        # For transfers, we need to handle both accounts separately
        # This function only updates one account, so no special handling needed here
        pass
    
    # Update account balance
    supabase.table("accounts").update({"balance": new_balance}).eq("id", str(account_id)).execute()

@router.get("/", response_model=List[Transaction])
async def get_transactions(
    current_user: dict = Depends(get_current_user),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    transaction_type: Optional[TransactionType] = None,
    category: Optional[str] = None,
    account_id: Optional[UUID] = None
):
    """
    Retrieve a list of all transactions, optionally filtered by date, type, category, or account.
    """
    supabase = get_supabase()
    
    # First get the user's account
    account_query = supabase.table("accounts").select("id").eq("user_id", str(current_user["id"])).execute()
    if not account_query.data:
        return []
        
    account_id = account_query.data[0]["id"]
    
    # Then get transactions for that account
    query = supabase.table("transactions").select("*").eq("user_id", str(current_user["id"])).order("date", desc=True)
    
    # Apply filters if provided
    if start_date:
        query = query.gte("date", start_date.isoformat())
    if end_date:
        query = query.lte("date", end_date.isoformat())
    if transaction_type:
        query = query.eq("transaction_type", transaction_type)
    if category:
        query = query.eq("category", category)
    if account_id:
        query = query.eq("account_id", str(account_id))
    
    result = query.execute()
    print(f"Transactions query result: {result.data}")  # Debug print
    
    return result.data if result.data else []

@router.post("/", response_model=Transaction, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    transaction: TransactionCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a new transaction record and update account balance."""
    supabase = get_supabase()
    
    # Convert the transaction data to a dict and ensure all values are JSON serializable
    transaction_data = {
        k: (str(v) if isinstance(v, (UUID, type)) else v)
        for k, v in transaction.dict().items()
    }
    
    # Set user_id
    transaction_data["user_id"] = str(current_user["id"])
    
    # Convert account_id to string if it exists
    if transaction_data.get("account_id"):
        transaction_data["account_id"] = str(transaction_data["account_id"])
    
    # Add current UTC datetime
    transaction_data["date"] = datetime.now(timezone.utc).isoformat()

    try:
        print("Sending transaction data:", transaction_data)  # Debug print
        result = supabase.table("transactions").insert(transaction_data).execute()
        
        if not result.data or len(result.data) == 0:
            raise HTTPException(status_code=400, detail="Failed to create transaction")
        
        # Update account balance
        await update_account_balance(
            supabase, 
            UUID(json_serializer(result.data[0]["account_id"])), 
            result.data[0]["amount"], 
            result.data[0]["transaction_type"]
        )
        
        # If this is a sale, create an invoice automatically
        if result.data[0]["transaction_type"] == TransactionType.SALE:
            # Create an invoice for this sale
            invoice_data = {
                "invoice_number": f"INV-{datetime.now().strftime('%Y%m%d')}-{result.data[0]['id'][:8]}",
                "customer_name": result.data[0]["description"] or "Customer",
                "subtotal": result.data[0]["amount"],
                "tax_rate": 18.0,  # Default GST rate
                "tax_amount": round(result.data[0]["amount"] * 18.0 / 100, 2),
                "total_amount": round(result.data[0]["amount"] * 1.18, 2),
                "status": "paid",
                "notes": f"Auto-generated from transaction {result.data[0]['id']}",
                "user_id": current_user["id"],
                "issue_date": result.data[0]["date"]
            }
            
            # Create invoice item
            invoice_item = {
                "description": result.data[0]["description"] or "Sale",
                "quantity": 1,
                "unit_price": result.data[0]["amount"],
                "amount": result.data[0]["amount"],
                "tax_included": True
            }
            
            # Insert invoice
            invoice_result = supabase.table("invoices").insert(invoice_data).execute()
            if invoice_result.data and len(invoice_result.data) > 0:
                invoice_id = invoice_result.data[0]["id"]
                
                # Insert invoice item
                item_data = {
                    "invoice_id": invoice_id,
                    **invoice_item
                }
                supabase.table("invoice_items").insert(item_data).execute()
        
        return result.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{transaction_id}", response_model=Transaction)
async def get_transaction(
    transaction_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """
    Fetch details of a specific transaction.
    """
    supabase = get_supabase()
    result = supabase.table("transactions").select("*").eq("id", str(transaction_id)).eq("user_id", str(current_user["id"])).execute()
    
    if not result.data or len(result.data) == 0:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    return result.data[0]

@router.put("/{transaction_id}", response_model=Transaction)
async def update_transaction(
    transaction_id: UUID,
    transaction_update: TransactionUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Update an existing transaction record and adjust account balance.
    """
    supabase = get_supabase()
    
    # Check if transaction exists and belongs to the user
    existing = supabase.table("transactions").select("*").eq("id", str(transaction_id)).eq("user_id", current_user["id"]).execute()
    
    if not existing.data or len(existing.data) == 0:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    existing_transaction = existing.data[0]
    
    # Filter out None values
    update_data = {k: v for k, v in transaction_update.dict().items() if v is not None}
    
    try:
        # If amount or transaction_type is changing, update account balance
        if "amount" in update_data or "transaction_type" in update_data or "account_id" in update_data:
            # First, reverse the effect of the old transaction
            await update_account_balance(
                supabase, 
                UUID(existing_transaction["account_id"]), 
                existing_transaction["amount"], 
                existing_transaction["transaction_type"],
                is_new=False
            )
            
            # Then apply the new transaction
            new_amount = update_data.get("amount", existing_transaction["amount"])
            new_type = update_data.get("transaction_type", existing_transaction["transaction_type"])
            new_account_id = update_data.get("account_id", existing_transaction["account_id"])
            
            await update_account_balance(
                supabase, 
                UUID(new_account_id), 
                new_amount, 
                new_type
            )
        
        # Update the transaction
        result = supabase.table("transactions").update(update_data).eq("id", str(transaction_id)).execute()
        return result.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    transaction_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a transaction record and update account balance.
    """
    supabase = get_supabase()
    
    # Check if transaction exists and belongs to the user
    existing = supabase.table("transactions").select("*").eq("id", str(transaction_id)).eq("user_id", current_user["id"]).execute()
    
    if not existing.data or len(existing.data) == 0:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    existing_transaction = existing.data[0]
    
    try:
        # Reverse the effect of the transaction on the account balance
        await update_account_balance(
            supabase, 
            UUID(existing_transaction["account_id"]), 
            existing_transaction["amount"], 
            existing_transaction["transaction_type"],
            is_new=False
        )
        
        # Delete the transaction
        supabase.table("transactions").delete().eq("id", str(transaction_id)).execute()
        return None
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/totals/", response_model=dict)
async def get_transaction_totals(current_user: dict = Depends(get_current_user)):
    """
    Get total sales and expenses for the current user.
    """
    supabase = get_supabase()
    
    # Get sales total
    sales_query = supabase.table("transactions").select("amount").eq("user_id", str(current_user["id"])).eq("transaction_type", "sale").execute()
    total_sales = sum(transaction["amount"] for transaction in sales_query.data) if sales_query.data else 0.0
    
    # Get expenses total
    expenses_query = supabase.table("transactions").select("amount").eq("user_id", str(current_user["id"])).eq("transaction_type", "expense").execute()
    total_expenses = sum(transaction["amount"] for transaction in expenses_query.data) if expenses_query.data else 0.0
    
    return {
        "total_sales": float(total_sales),
        "total_expenses": float(total_expenses)
    }