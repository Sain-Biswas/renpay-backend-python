from fastapi import APIRouter, Depends, HTTPException, status, Query, Body, Path, BackgroundTasks
from fastapi.responses import ORJSONResponse
from app.services.supabase_client import get_supabase, run_in_threadpool, with_retry
from app.models.transaction import (
    Transaction, TransactionCreate, TransactionUpdate, 
    TransactionType, TransactionInDB, TransactionSummary, TransactionFilter
)
from app.dependencies import get_current_user
from typing import List, Dict, Optional, Any, Annotated
from uuid import UUID
from datetime import datetime, date, timezone, timedelta
import orjson
from decimal import Decimal
import logging
from pydantic import conint
from app.models.user import User
from app.services.transaction_service import (
    get_transaction_summary, 
    handle_transaction_balance_update,
    get_category_summary
)

router = APIRouter(
    prefix="/transactions",
    tags=["transactions"],
    responses={404: {"description": "Not found"}}
)
logger = logging.getLogger(__name__)

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

async def update_account_balance(
    supabase, 
    account_id: UUID, 
    amount: float, 
    transaction_type: TransactionType
):
    """Update account balance based on transaction type"""
    # Get current account balance
    account_result = await run_in_threadpool(
        with_retry(lambda: supabase.table("accounts")
        .select("*")
        .eq("id", str(account_id))
        .execute())
    )
    
    if not account_result.data or len(account_result.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found"
        )
    
    account = account_result.data[0]
    current_balance = account["balance"]
    
    # Calculate new balance based on transaction type
    new_balance = current_balance
    if transaction_type == TransactionType.SALE:
        new_balance += amount
    elif transaction_type == TransactionType.EXPENSE:
        new_balance -= amount
    elif transaction_type == TransactionType.TRANSFER:
        # For transfers, we handle separately in the transfer endpoint
        pass
    
    # Update account balance
    await run_in_threadpool(
        with_retry(lambda: supabase.table("accounts")
        .update({"balance": new_balance})
        .eq("id", str(account_id))
        .execute())
    )
    
    return new_balance

@router.get("/", response_model=List[TransactionInDB])
async def get_transactions(
    current_user: User = Depends(get_current_user),
    transaction_type: Optional[TransactionType] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    account_id: Optional[UUID] = None,
    category_id: Optional[UUID] = None,
    is_reconciled: Optional[bool] = None,
    payment_method: Optional[str] = None,
    reference_number: Optional[str] = None,
    tags: Optional[List[str]] = Query(None),
    limit: conint(ge=1, le=100) = 25,
    offset: conint(ge=0) = 0,
    sort_by: str = "date",
    sort_order: str = "desc"
):
    """
    Get list of transactions with filtering options
    """
    try:
        # Build query
        query = get_supabase().table("transactions").select("*").eq("user_id", str(current_user.id))
        
        # Apply filters
        if transaction_type:
            query = query.eq("transaction_type", transaction_type)
        
        if from_date:
            query = query.gte("date", datetime.combine(from_date, datetime.min.time()).isoformat())
        
        if to_date:
            query = query.lte("date", datetime.combine(to_date, datetime.max.time()).isoformat())
        
        if min_amount is not None:
            query = query.gte("amount", min_amount)
        
        if max_amount is not None:
            query = query.lte("amount", max_amount)
            
        if account_id:
            query = query.eq("from_account_id", str(account_id))
            
        if category_id:
            query = query.eq("category_id", str(category_id))
            
        if is_reconciled is not None:
            query = query.eq("is_reconciled", is_reconciled)
            
        if payment_method:
            query = query.eq("payment_method", payment_method)
            
        if reference_number:
            query = query.eq("reference_number", reference_number)
            
        if tags:
            # Filter by any of the provided tags (array contains)
            for tag in tags:
                query = query.contains("tags", [tag])
        
        # Apply sorting
        sort_direction = "desc" if sort_order.lower() == "desc" else "asc"
        query = query.order(sort_by, sort_direction)
        
        # Apply pagination
        query = query.range(offset, offset + limit - 1)
        
        # Execute query
        response = await run_in_threadpool(query.execute)
        
        if response.error:
            logger.error(f"Error fetching transactions: {response.error}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch transactions"
            )
        
        return response.data
    
    except Exception as e:
        logger.error(f"Error in get_transactions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching transactions"
        )

@router.get("/summary", response_model=TransactionSummary)
async def get_transactions_summary(
    period: str = "month",
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    transaction_type: Optional[TransactionType] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Get a summary of transactions for analysis
    """
    try:
        summary = await get_transaction_summary(
            user_id=current_user.id,
            period=period,
            from_date=from_date,
            to_date=to_date,
            transaction_type=transaction_type
        )
        return summary
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating transaction summary: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate transaction summary"
        )

@router.get("/categories", response_model=Dict[str, Dict[str, float]])
async def get_transactions_by_category(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    transaction_type: Optional[TransactionType] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Get transactions grouped by category
    """
    try:
        categories = await get_category_summary(
            user_id=current_user.id,
            transaction_type=transaction_type,
            from_date=from_date,
            to_date=to_date
        )
        return categories
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating category summary: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate category summary"
        )

@router.get("/{transaction_id}", response_model=TransactionInDB)
async def get_transaction(
    transaction_id: UUID = Path(..., description="Transaction ID"),
    current_user: User = Depends(get_current_user)
):
    """
    Get a specific transaction by ID
    """
    try:
        response = await run_in_threadpool(
            get_supabase().table("transactions")
            .select("*")
            .eq("id", str(transaction_id))
            .eq("user_id", str(current_user.id))
            .single()
            .execute
        )
        
        if response.error or not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transaction not found"
            )
        
        return response.data
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching transaction {transaction_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch transaction"
        )

@router.post("/", response_model=TransactionInDB, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    transaction: TransactionCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """
    Create a new transaction and update account balances
    """
    try:
        # Create transaction data
        transaction_data = transaction.model_dump()
        transaction_data["user_id"] = str(current_user.id)
        transaction_data["created_at"] = datetime.now().isoformat()
        transaction_data["updated_at"] = datetime.now().isoformat()
        
        # Ensure ID is a string
        if "id" in transaction_data:
            transaction_data["id"] = str(transaction_data["id"])
            
        # Convert all UUID fields to strings
        for field in ["from_account_id", "to_account_id", "category_id", "related_invoice_id", "related_tax_filing_id"]:
            if field in transaction_data and transaction_data[field] is not None:
                transaction_data[field] = str(transaction_data[field])
        
        # Insert transaction
        response = await run_in_threadpool(
            get_supabase().table("transactions").insert(transaction_data).execute
        )
        
        if response.error:
            logger.error(f"Error creating transaction: {response.error}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create transaction: {response.error.message}"
            )
        
        created_transaction = response.data[0]
        
        # Update account balances in background
        background_tasks.add_task(
            handle_transaction_balance_update,
            transaction=created_transaction,
            is_new=True
        )
        
        return created_transaction
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in create_transaction: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the transaction"
        )

@router.put("/{transaction_id}", response_model=TransactionInDB)
async def update_transaction(
    transaction_update: TransactionUpdate,
    transaction_id: UUID = Path(..., description="Transaction ID"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_user)
):
    """
    Update an existing transaction
    """
    try:
        # Get the current transaction
        current_txn_response = await run_in_threadpool(
            get_supabase().table("transactions")
            .select("*")
            .eq("id", str(transaction_id))
            .eq("user_id", str(current_user.id))
            .single()
            .execute
        )
        
        if current_txn_response.error or not current_txn_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transaction not found"
            )
        
        current_transaction = current_txn_response.data
        
        # Prepare update data
        update_data = transaction_update.model_dump(exclude_unset=True)
        update_data["updated_at"] = datetime.now().isoformat()
        
        # Convert UUID fields to strings
        for field in ["from_account_id", "to_account_id", "category_id", "related_invoice_id", "related_tax_filing_id"]:
            if field in update_data and update_data[field] is not None:
                update_data[field] = str(update_data[field])
        
        # Update transaction
        response = await run_in_threadpool(
            get_supabase().table("transactions")
            .update(update_data)
            .eq("id", str(transaction_id))
            .eq("user_id", str(current_user.id))
            .execute
        )
        
        if response.error or not response.data:
            logger.error(f"Error updating transaction: {response.error}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update transaction"
            )
        
        updated_transaction = response.data[0]
        
        # Update account balances in background if relevant fields changed
        balance_fields = ["amount", "transaction_type", "from_account_id", "to_account_id"]
        if any(field in update_data for field in balance_fields):
            background_tasks.add_task(
                handle_transaction_balance_update,
                transaction=updated_transaction,
                is_new=False,
                old_transaction=current_transaction
            )
        
        return updated_transaction
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in update_transaction: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the transaction"
        )

@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    transaction_id: UUID = Path(..., description="Transaction ID"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_user)
):
    """
    Delete a transaction and reverse its impact on account balances
    """
    try:
        # Get the current transaction
        current_txn_response = await run_in_threadpool(
            get_supabase().table("transactions")
            .select("*")
            .eq("id", str(transaction_id))
            .eq("user_id", str(current_user.id))
            .single()
            .execute
        )
        
        if current_txn_response.error or not current_txn_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transaction not found"
            )
        
        current_transaction = current_txn_response.data
        
        # Delete the transaction
        response = await run_in_threadpool(
            get_supabase().table("transactions")
            .delete()
            .eq("id", str(transaction_id))
            .eq("user_id", str(current_user.id))
            .execute
        )
        
        if response.error:
            logger.error(f"Error deleting transaction: {response.error}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete transaction"
            )
        
        # Reverse account balance changes in background
        # To reverse, we swap income/expense logic
        if current_transaction.get("transaction_type") == "income":
            current_transaction["transaction_type"] = "expense"
        elif current_transaction.get("transaction_type") == "expense":
            current_transaction["transaction_type"] = "income"
            
        background_tasks.add_task(
            handle_transaction_balance_update,
            transaction=current_transaction,
            is_new=True  # Treating as new but with reversed type
        )
        
        return None
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in delete_transaction: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting the transaction"
        )

@router.post("/bulk-delete", status_code=status.HTTP_204_NO_CONTENT)
async def bulk_delete_transactions(
    transaction_ids: List[UUID],
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_user)
):
    """
    Delete multiple transactions at once
    """
    try:
        # Convert UUIDs to strings
        ids_str = [str(id) for id in transaction_ids]
        
        # Get all transactions first to update account balances later
        transactions_response = await run_in_threadpool(
            get_supabase().table("transactions")
            .select("*")
            .in_("id", ids_str)
            .eq("user_id", str(current_user.id))
            .execute
        )
        
        if transactions_response.error:
            logger.error(f"Error fetching transactions: {transactions_response.error}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch transactions for bulk delete"
            )
        
        transactions_to_delete = transactions_response.data
        
        # Make sure all transactions belong to current user
        if len(transactions_to_delete) != len(transaction_ids):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="One or more transactions not found or not accessible"
            )
        
        # Delete transactions
        delete_response = await run_in_threadpool(
            get_supabase().table("transactions")
            .delete()
            .in_("id", ids_str)
            .eq("user_id", str(current_user.id))
            .execute
        )
        
        if delete_response.error:
            logger.error(f"Error in bulk delete: {delete_response.error}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete transactions"
            )
        
        # Update account balances for each deleted transaction
        for txn in transactions_to_delete:
            # Reverse transaction type to undo balance effect
            if txn.get("transaction_type") == "income":
                txn["transaction_type"] = "expense"
            elif txn.get("transaction_type") == "expense":
                txn["transaction_type"] = "income"
                
            background_tasks.add_task(
                handle_transaction_balance_update,
                transaction=txn,
                is_new=True  # Treating as new but with reversed type
            )
        
        return None
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk_delete_transactions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during bulk delete operation"
        )