from fastapi import APIRouter, Depends, HTTPException, status, Query
from app.services.supabase_client import get_supabase
from app.models.account import Account, AccountCreate, AccountUpdate
from app.models.transaction import TransactionType, Transaction
from app.dependencies import get_current_user
from app.routes.transactions import update_account_balance
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from uuid import UUID

router = APIRouter()

@router.get("/", response_model=List[Account])
async def get_accounts(
    current_user: dict = Depends(get_current_user)
):
    """
    Retrieve a list of all accounts for the current user.
    """
    supabase = get_supabase()
    result = supabase.table("accounts").select("*").eq("user_id", current_user["id"]).execute()
    
    if result.data is None:
        return []
    return result.data

@router.post("/", response_model=Account, status_code=status.HTTP_201_CREATED)
async def create_account(
    account: AccountCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new account.
    """
    supabase = get_supabase()
    
    # Set the user_id from the authenticated user
    account_data = account.dict()
    account_data["user_id"] = current_user["id"]
    
    try:
        result = supabase.table("accounts").insert(account_data).execute()
        if result.data and len(result.data) > 0:
            return result.data[0]
        raise HTTPException(status_code=400, detail="Failed to create account")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{account_id}", response_model=Account)
async def get_account(
    account_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """
    Fetch details of a specific account.
    """
    supabase = get_supabase()
    result = supabase.table("accounts").select("*").eq("id", str(account_id)).eq("user_id", current_user["id"]).execute()
    
    if not result.data or len(result.data) == 0:
        raise HTTPException(status_code=404, detail="Account not found")
    
    return result.data[0]

@router.get("/{account_id}/transactions", response_model=List[Transaction])
async def get_account_transactions(
    account_id: UUID,
    current_user: dict = Depends(get_current_user),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    transaction_type: Optional[TransactionType] = None
):
    """
    Get all transactions for a specific account.
    """
    supabase = get_supabase()
    
    # Check if account exists and belongs to the user
    account = supabase.table("accounts").select("*").eq("id", str(account_id)).eq("user_id", current_user["id"]).execute()
    
    if not account.data or len(account.data) == 0:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Get transactions for this account
    query = supabase.table("transactions").select("*").eq("account_id", str(account_id)).eq("user_id", current_user["id"])
    
    # Apply filters if provided
    if start_date:
        query = query.gte("date", start_date.isoformat())
    if end_date:
        query = query.lte("date", end_date.isoformat())
    if transaction_type:
        query = query.eq("transaction_type", transaction_type)
    
    result = query.execute()
    
    if result.data is None:
        return []
    return result.data

@router.put("/{account_id}", response_model=Account)
async def update_account(
    account_id: UUID,
    account_update: AccountUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Update an existing account.
    """
    supabase = get_supabase()
    
    # Check if account exists and belongs to the user
    existing = supabase.table("accounts").select("*").eq("id", str(account_id)).eq("user_id", current_user["id"]).execute()
    
    if not existing.data or len(existing.data) == 0:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Filter out None values
    update_data = {k: v for k, v in account_update.dict().items() if v is not None}
    
    try:
        result = supabase.table("accounts").update(update_data).eq("id", str(account_id)).execute()
        return result.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: UUID,
    current_user: dict = Depends(get_current_user),
    transfer_to_account_id: Optional[UUID] = None
):
    """
    Delete an account. Optionally transfer all transactions to another account.
    """
    supabase = get_supabase()
    
    # Check if account exists and belongs to the user
    existing = supabase.table("accounts").select("*").eq("id", str(account_id)).eq("user_id", current_user["id"]).execute()
    
    if not existing.data or len(existing.data) == 0:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Check if this is the user's only account
    accounts = supabase.table("accounts").select("*").eq("user_id", current_user["id"]).execute()
    if len(accounts.data) == 1 and accounts.data[0]["id"] == str(account_id):
        raise HTTPException(status_code=400, detail="Cannot delete the only account. Create another account first.")
    
    try:
        # If transfer_to_account_id is provided, move all transactions to that account
        if transfer_to_account_id:
            # Check if target account exists and belongs to the user
            target_account = supabase.table("accounts").select("*").eq("id", str(transfer_to_account_id)).eq("user_id", current_user["id"]).execute()
            
            if not target_account.data or len(target_account.data) == 0:
                raise HTTPException(status_code=404, detail="Target account not found")
            
            # Get all transactions for the account being deleted
            transactions = supabase.table("transactions").select("*").eq("account_id", str(account_id)).execute()
            
            # Update all transactions to the new account
            if transactions.data:
                supabase.table("transactions").update({"account_id": str(transfer_to_account_id)}).eq("account_id", str(account_id)).execute()
            
            # Transfer the balance to the target account
            target_balance = target_account.data[0]["balance"] + existing.data[0]["balance"]
            supabase.table("accounts").update({"balance": target_balance}).eq("id", str(transfer_to_account_id)).execute()
        else:
            # If not transferring, check if there are any transactions
            transactions = supabase.table("transactions").select("*").eq("account_id", str(account_id)).execute()
            
            if transactions.data and len(transactions.data) > 0:
                raise HTTPException(
                    status_code=400, 
                    detail="Cannot delete account with transactions. Transfer them to another account first."
                )
        
        # Delete the account
        supabase.table("accounts").delete().eq("id", str(account_id)).execute()
        return None
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/balance", response_model=dict)
async def get_balance(
    current_user: dict = Depends(get_current_user)
):
    """
    Retrieve the current balance, aggregated from all accounts.
    """
    supabase = get_supabase()
    
    # Get all accounts for the user
    accounts = supabase.table("accounts").select("*").eq("user_id", current_user["id"]).execute()
    
    if not accounts.data:
        return {"balance": 0.0}
    
    # Calculate total balance from all accounts
    total_balance = sum(account["balance"] for account in accounts.data)
    
    return {"balance": total_balance}

@router.get("/summary", response_model=Dict)
async def get_account_summary(
    current_user: dict = Depends(get_current_user),
    period: Optional[str] = Query("month", enum=["week", "month", "quarter", "year"])
):
    """
    Get a summary of account activity including income, expenses, and balance over time.
    """
    supabase = get_supabase()
    
    # Calculate date range based on period
    now = datetime.now()
    if period == "week":
        start_date = now - timedelta(days=7)
    elif period == "month":
        start_date = now - timedelta(days=30)
    elif period == "quarter":
        start_date = now - timedelta(days=90)
    else:  # year
        start_date = now - timedelta(days=365)
    
    # Get all accounts for the user
    accounts = supabase.table("accounts").select("*").eq("user_id", current_user["id"]).execute()
    
    if not accounts.data:
        return {
            "total_balance": 0.0,
            "income": 0.0,
            "expenses": 0.0,
            "net_change": 0.0,
            "accounts": [],
            "period": period
        }
    
    # Get transactions for the period
    transactions = supabase.table("transactions").select("*").eq("user_id", current_user["id"]).gte("date", start_date.isoformat()).execute()
    
    # Calculate income and expenses
    income = sum(t["amount"] for t in transactions.data if t["transaction_type"] == TransactionType.SALE)
    expenses = sum(t["amount"] for t in transactions.data if t["transaction_type"] == TransactionType.EXPENSE)
    
    # Get invoices for the period
    invoices = supabase.table("invoices").select("*").eq("user_id", current_user["id"]).gte("issue_date", start_date.isoformat()).execute()
    
    # Count paid invoices
    paid_invoices = len([i for i in invoices.data if i["status"] == "paid"])
    
    # Calculate total balance
    total_balance = sum(account["balance"] for account in accounts.data)
    
    # Prepare account summaries
    account_summaries = []
    for account in accounts.data:
        account_transactions = [t for t in transactions.data if t["account_id"] == account["id"]]
        account_income = sum(t["amount"] for t in account_transactions if t["transaction_type"] == TransactionType.SALE)
        account_expenses = sum(t["amount"] for t in account_transactions if t["transaction_type"] == TransactionType.EXPENSE)
        
        account_summaries.append({
            "id": account["id"],
            "name": account["name"],
            "balance": account["balance"],
            "income": account_income,
            "expenses": account_expenses,
            "transaction_count": len(account_transactions)
        })
    
    return {
        "total_balance": total_balance,
        "income": income,
        "expenses": expenses,
        "net_change": income - expenses,
        "accounts": account_summaries,
        "invoices_count": len(invoices.data),
        "paid_invoices_count": paid_invoices,
        "period": period
    } 