from fastapi import APIRouter, Depends, HTTPException, status, Query
from app.services.supabase_client import get_supabase
from app.models.transaction import Transaction, TransactionCreate, TransactionUpdate, TransactionType
from app.dependencies import get_current_user
from typing import List, Optional
from datetime import datetime
from uuid import UUID

router = APIRouter()

@router.get("/", response_model=List[Transaction])
async def get_transactions(
    current_user: dict = Depends(get_current_user),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    transaction_type: Optional[TransactionType] = None,
    category: Optional[str] = None
):
    """
    Retrieve a list of all transactions, optionally filtered by date, type, or category.
    """
    supabase = get_supabase()
    query = supabase.table("transactions").select("*").eq("user_id", current_user["id"])
    
    # Apply filters if provided
    if start_date:
        query = query.gte("date", start_date.isoformat())
    if end_date:
        query = query.lte("date", end_date.isoformat())
    if transaction_type:
        query = query.eq("transaction_type", transaction_type)
    if category:
        query = query.eq("category", category)
    
    result = query.execute()
    
    if result.data is None:
        return []
    return result.data

@router.post("/", response_model=Transaction, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    transaction: TransactionCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new transaction record.
    """
    supabase = get_supabase()
    
    # Set the user_id from the authenticated user
    transaction_data = transaction.dict()
    transaction_data["user_id"] = current_user["id"]
    
    try:
        result = supabase.table("transactions").insert(transaction_data).execute()
        if result.data and len(result.data) > 0:
            return result.data[0]
        raise HTTPException(status_code=400, detail="Failed to create transaction")
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
    result = supabase.table("transactions").select("*").eq("id", str(transaction_id)).eq("user_id", current_user["id"]).execute()
    
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
    Update an existing transaction record.
    """
    supabase = get_supabase()
    
    # Check if transaction exists and belongs to the user
    existing = supabase.table("transactions").select("*").eq("id", str(transaction_id)).eq("user_id", current_user["id"]).execute()
    
    if not existing.data or len(existing.data) == 0:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    # Filter out None values
    update_data = {k: v for k, v in transaction_update.dict().items() if v is not None}
    
    try:
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
    Delete a transaction record.
    """
    supabase = get_supabase()
    
    # Check if transaction exists and belongs to the user
    existing = supabase.table("transactions").select("*").eq("id", str(transaction_id)).eq("user_id", current_user["id"]).execute()
    
    if not existing.data or len(existing.data) == 0:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    try:
        supabase.table("transactions").delete().eq("id", str(transaction_id)).execute()
        return None
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) 