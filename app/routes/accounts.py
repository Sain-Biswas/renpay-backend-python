from fastapi import APIRouter, Depends, HTTPException, status, Query
from app.services.supabase_client import get_supabase
from app.models.account import Account, AccountCreate, AccountUpdate
from app.models.transaction import TransactionType, Transaction
from app.dependencies import get_current_user
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from uuid import UUID

router = APIRouter()

@router.get("/", response_model=List[Account])
async def get_accounts(current_user: dict = Depends(get_current_user)):
    """
    Retrieve a list of all accounts for the current user.
    """
    supabase = get_supabase()
    result = supabase.table("accounts").select("*").eq("user_id", current_user["id"]).execute()
    
    return result.data if result.data else []

@router.get("/{account_id}", response_model=Account)
async def get_account(account_id: UUID, current_user: dict = Depends(get_current_user)):
    """
    Fetch details of a specific account.
    """
    supabase = get_supabase()
    result = supabase.table("accounts").select("*").eq("id", str(account_id)).eq("user_id", current_user["id"]).execute()
    
    if not result.data:
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
    
    query = supabase.table("transactions").select("*").eq("account_id", str(account_id)).eq("user_id", current_user["id"])
    
    if start_date:
        query = query.gte("date", start_date.isoformat())
    if end_date:
        query = query.lte("date", end_date.isoformat())
    if transaction_type:
        query = query.eq("transaction_type", transaction_type)
    
    result = query.execute()
    
    return result.data if result.data else []

@router.put("/{account_id}", response_model=Account)
async def update_account(account_id: UUID, account_update: AccountUpdate, current_user: dict = Depends(get_current_user)):
    """
    Update an existing account.
    """
    supabase = get_supabase()
    
    existing = supabase.table("accounts").select("*").eq("id", str(account_id)).eq("user_id", current_user["id"]).execute()
    
    if not existing.data:
        raise HTTPException(status_code=404, detail="Account not found")
    
    update_data = {k: v for k, v in account_update.dict().items() if v is not None}
    
    result = supabase.table("accounts").update(update_data).eq("id", str(account_id)).execute()
    
    return result.data[0] if result.data else existing.data[0]

@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(account_id: UUID, current_user: dict = Depends(get_current_user)):
    """
    Delete an account.
    """
    supabase = get_supabase()
    
    existing = supabase.table("accounts").select("*").eq("id", str(account_id)).eq("user_id", current_user["id"]).execute()
    
    if not existing.data:
        raise HTTPException(status_code=404, detail="Account not found")

    supabase.table("accounts").delete().eq("id", str(account_id)).execute()
    return None

@router.get("/balance/", response_model=dict)  # Note the trailing slash
async def get_balance(current_user: dict = Depends(get_current_user)):
    """
    Retrieve the current balance, aggregated from all accounts.
    """
    supabase = get_supabase()
    accounts = supabase.table("accounts").select("balance").eq("user_id", current_user["id"]).execute()
    
    total_balance = sum(account["balance"] for account in accounts.data) if accounts.data else 0.0
    
    return {"balance": float(total_balance)}  # Ensure we return a float
