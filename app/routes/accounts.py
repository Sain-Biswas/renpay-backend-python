from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from app.services.supabase_client import get_supabase, with_retry, run_in_threadpool
from app.models.account import Account, AccountCreate, AccountUpdate, AccountSummary, AccountFilter
from app.models.transaction import TransactionType, Transaction
from app.dependencies import get_current_user
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from uuid import UUID
from decimal import Decimal
import asyncio
from app.models.user import User

router = APIRouter(
    prefix="/accounts",
    tags=["accounts"],
    responses={404: {"description": "Not found"}},
)

@router.get("/", response_model=List[AccountSummary])
async def get_accounts(
    user: User = Depends(get_current_user),
    account_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    balance_min: Optional[float] = None,
    balance_max: Optional[float] = None,
    search_term: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="created_at", regex="^(name|account_type|balance|created_at)$"),
    sort_order: str = Query(default="desc", regex="^(asc|desc)$"),
):
    """
    Get accounts for the current user with optional filtering and sorting.
    """
    # Convert float parameters to Decimal for the filter
    balance_min_decimal = Decimal(str(balance_min)) if balance_min is not None else None
    balance_max_decimal = Decimal(str(balance_max)) if balance_max is not None else None
    
    # Create filter object
    filter_data = {
        "account_type": account_type,
        "is_active": is_active,
        "balance_min": balance_min_decimal,
        "balance_max": balance_max_decimal,
        "search_term": search_term
    }
    
    # Remove None values
    filter_data = {k: v for k, v in filter_data.items() if v is not None}
    
    # Create filter if any parameters are provided
    account_filter = AccountFilter(**filter_data) if filter_data else None
    
    # Build query
    query = (
        get_supabase().table("accounts")
        .select("*")
        .eq("user_id", str(user.id))
    )
    
    # Apply filters
    if account_filter:
        if account_filter.account_type:
            query = query.eq("account_type", account_filter.account_type)
        
        if account_filter.is_active is not None:
            query = query.eq("is_active", account_filter.is_active)
        
        if account_filter.balance_min is not None:
            query = query.gte("balance", str(account_filter.balance_min))
        
        if account_filter.balance_max is not None:
            query = query.lte("balance", str(account_filter.balance_max))
        
        if account_filter.search_term:
            search = f"%{account_filter.search_term}%"
            query = query.or_(f"name.ilike.{search},description.ilike.{search}")
    
    # Apply sorting
    query = query.order(sort_by, ascending=(sort_order == "asc"))
    
    # Apply pagination
    query = query.range(offset, offset + limit - 1)
    
    # Execute query
    response = await run_in_threadpool(with_retry(query.execute))
    
    if response.error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=response.error.message)
    
    return response.data

@router.post("/", response_model=Account, status_code=status.HTTP_201_CREATED)
async def create_account(
    account_data: AccountCreate,
    user: User = Depends(get_current_user),
):
    """Create a new account for the current user."""
    now = datetime.now(timezone.utc)
    
    # Use model_dump() instead of dict() for Pydantic v2 compatibility
    account_dict = account_data.model_dump()
    account_dict["user_id"] = str(user.id)
    account_dict["created_at"] = now
    account_dict["updated_at"] = now
    account_dict["balance"] = str(account_dict["balance"])  # Convert Decimal to string for Supabase
    
    response = await run_in_threadpool(
        with_retry(
            get_supabase().table("accounts")
            .insert(account_dict)
            .execute
        )
    )
    
    if response.error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=response.error.message)
    
    return response.data[0]

@router.get("/{account_id}", response_model=Account)
async def get_account(
    account_id: UUID = Path(..., title="The ID of the account to get"),
    user: User = Depends(get_current_user),
):
    """Get a specific account by ID."""
    response = await run_in_threadpool(
        with_retry(
            get_supabase().table("accounts")
            .select("*")
            .eq("id", str(account_id))
            .eq("user_id", str(user.id))
            .execute
        )
    )
    
    if response.error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=response.error.message)
    
    if not response.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    
    return response.data[0]

@router.get("/{account_id}/transactions", response_model=List[Transaction])
async def get_account_transactions(
    account_id: UUID,
    current_user: dict = Depends(get_current_user),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    transaction_type: Optional[TransactionType] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    Get all transactions for a specific account with pagination.
    """
    supabase = get_supabase()
    
    query = supabase.table("transactions").select("*").eq("from_account_id", str(account_id)).eq("user_id", str(current_user["id"]))
    
    if start_date:
        query = query.gte("date", start_date.isoformat())
    if end_date:
        query = query.lte("date", end_date.isoformat())
    if transaction_type:
        query = query.eq("transaction_type", transaction_type.value)
    
    # Add pagination
    query = query.order("date", desc=True).range(offset, offset + limit - 1)
    
    result = await run_in_threadpool(lambda: query.execute())
    
    return result.data if result.data else []

@router.patch("/{account_id}", response_model=Account)
async def update_account(
    account_data: AccountUpdate,
    account_id: UUID = Path(..., title="The ID of the account to update"),
    user: User = Depends(get_current_user),
):
    """Update an account."""
    # Verify account exists and belongs to user
    account_check = await run_in_threadpool(
        with_retry(
            get_supabase().table("accounts")
            .select("id")
            .eq("id", str(account_id))
            .eq("user_id", str(user.id))
            .execute
        )
    )
    
    if account_check.error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=account_check.error.message)
    
    if not account_check.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    
    # Use model_dump() with exclude_unset=True to only update provided fields
    update_data = account_data.model_dump(exclude_unset=True)
    
    # If there's nothing to update, return the account
    if not update_data:
        return await get_account(account_id, user)
    
    # Add updated_at
    update_data["updated_at"] = datetime.now(timezone.utc)
    
    # Convert Decimal to string if present
    if "balance" in update_data and update_data["balance"] is not None:
        update_data["balance"] = str(update_data["balance"])
    
    # Update account
    response = await run_in_threadpool(
        with_retry(
            get_supabase().table("accounts")
            .update(update_data)
            .eq("id", str(account_id))
            .eq("user_id", str(user.id))
            .execute
        )
    )
    
    if response.error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=response.error.message)
    
    return response.data[0]

@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: UUID = Path(..., title="The ID of the account to delete"),
    user: User = Depends(get_current_user),
):
    """Delete an account."""
    # Check if this account has any transactions
    transactions_check = await run_in_threadpool(
        with_retry(
            get_supabase().table("transactions")
            .select("id", count="exact")
            .eq("account_id", str(account_id))
            .execute
        )
    )
    
    if transactions_check.error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=transactions_check.error.message)
    
    if transactions_check.count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete account with transactions. Delete transactions first or mark account as inactive."
        )
    
    # Delete account
    response = await run_in_threadpool(
        with_retry(
            get_supabase().table("accounts")
            .delete()
            .eq("id", str(account_id))
            .eq("user_id", str(user.id))
            .execute
        )
    )
    
    if response.error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=response.error.message)
    
    if not response.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    
    return None

@router.get("/summary/balances", response_model=Dict[str, Any])
async def get_account_balances(
    user: User = Depends(get_current_user),
):
    """Get summary of account balances by type."""
    response = await run_in_threadpool(
        with_retry(
            get_supabase().table("accounts")
            .select("account_type, balance, currency")
            .eq("user_id", str(user.id))
            .eq("is_active", True)
            .execute
        )
    )
    
    if response.error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=response.error.message)
    
    # Group by account type and calculate totals
    summary = {}
    for account in response.data:
        account_type = account["account_type"]
        balance = Decimal(account["balance"])
        currency = account["currency"]
        
        if account_type not in summary:
            summary[account_type] = {}
        
        if currency not in summary[account_type]:
            summary[account_type][currency] = 0
        
        summary[account_type][currency] += float(balance)
    
    # Calculate total across all accounts
    total = {}
    for account_type, currencies in summary.items():
        for currency, amount in currencies.items():
            if currency not in total:
                total[currency] = 0
            total[currency] += amount
    
    return {
        "by_type": summary,
        "total": total
    }
