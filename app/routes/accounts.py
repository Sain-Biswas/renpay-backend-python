from fastapi import APIRouter, Depends, HTTPException, status
from app.services.supabase_client import get_supabase
from app.models.account import Account, AccountCreate, AccountUpdate
from app.models.transaction import TransactionType
from app.dependencies import get_current_user
from typing import List, Optional
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
    current_user: dict = Depends(get_current_user)
):
    """
    Delete an account.
    """
    supabase = get_supabase()
    
    # Check if account exists and belongs to the user
    existing = supabase.table("accounts").select("*").eq("id", str(account_id)).eq("user_id", current_user["id"]).execute()
    
    if not existing.data or len(existing.data) == 0:
        raise HTTPException(status_code=404, detail="Account not found")
    
    try:
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