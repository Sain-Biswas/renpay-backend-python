from typing import Dict, List, Optional, Tuple, Any, Union
from datetime import datetime, date, timedelta
from decimal import Decimal
from uuid import UUID
import asyncio
import logging
from fastapi import HTTPException, status

from app.services.supabase_client import supabase, run_in_threadpool, with_retry
from app.models.transaction import TransactionInDB, TransactionSummary

logger = logging.getLogger(__name__)

async def get_transaction_summary(
    user_id: UUID,
    period: str = "month",
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    transaction_type: Optional[str] = None
) -> TransactionSummary:
    """
    Generate a summary of transactions for a given period
    """
    today = date.today()
    
    # Set default date range based on period
    if not from_date and not to_date:
        if period == "day":
            from_date = today
            to_date = today
        elif period == "week":
            # Monday to Sunday of current week
            from_date = today - timedelta(days=today.weekday())
            to_date = from_date + timedelta(days=6)
        elif period == "month":
            from_date = date(today.year, today.month, 1)
            # Get the last day of the month
            if today.month == 12:
                to_date = date(today.year + 1, 1, 1) - timedelta(days=1)
            else:
                to_date = date(today.year, today.month + 1, 1) - timedelta(days=1)
        elif period == "year":
            from_date = date(today.year, 1, 1)
            to_date = date(today.year, 12, 31)
        elif period == "all_time":
            # No date filters for all time
            from_date = None
            to_date = None
    
    # Convert to datetime with time for database query
    from_datetime = datetime.combine(from_date, datetime.min.time()) if from_date else None
    to_datetime = datetime.combine(to_date, datetime.max.time()) if to_date else None
    
    # Build query
    query = supabase.table("transactions").select("*").eq("user_id", str(user_id))
    
    if transaction_type:
        query = query.eq("transaction_type", transaction_type)
    
    if from_datetime:
        query = query.gte("date", from_datetime.isoformat())
    
    if to_datetime:
        query = query.lte("date", to_datetime.isoformat())
    
    # Execute query
    try:
        response = await run_in_threadpool(query.execute)
        transactions = response.data
    except Exception as e:
        logger.error(f"Error fetching transactions for summary: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate transaction summary"
        )
    
    # Process data
    total_income = Decimal(0)
    total_expense = Decimal(0)
    categories: Dict[str, Dict[str, float]] = {"income": {}, "expense": {}}
    
    for txn in transactions:
        amount = Decimal(str(txn.get("amount", 0)))
        txn_type = txn.get("transaction_type", "")
        category = txn.get("category", "Uncategorized")
        
        if txn_type == "income":
            total_income += amount
            if category not in categories["income"]:
                categories["income"][category] = 0
            categories["income"][category] += float(amount)
        elif txn_type == "expense":
            total_expense += amount
            if category not in categories["expense"]:
                categories["expense"][category] = 0
            categories["expense"][category] += float(amount)
    
    # Create summary
    summary = TransactionSummary(
        total_income=float(total_income),
        total_expense=float(total_expense),
        net_amount=float(total_income - total_expense),
        count=len(transactions),
        categories=categories,
        period=period,
        start_date=from_date or date(1970, 1, 1),  # Default for all_time
        end_date=to_date or today  # Default to today for all_time
    )
    
    return summary

async def update_account_balance(
    account_id: UUID,
    amount: Decimal,
    operation: str  # "add" or "subtract"
) -> bool:
    """
    Update an account balance by adding or subtracting the given amount
    """
    try:
        # Get current account balance
        response = await run_in_threadpool(
            supabase.table("accounts")
            .select("balance")
            .eq("id", str(account_id))
            .execute
        )
        
        if not response.data:
            logger.error(f"Account not found: {account_id}")
            return False
        
        current_balance = Decimal(str(response.data[0].get("balance", 0)))
        
        # Calculate new balance
        if operation == "add":
            new_balance = current_balance + amount
        elif operation == "subtract":
            new_balance = current_balance - amount
        else:
            logger.error(f"Invalid operation: {operation}")
            return False
        
        # Update balance
        update_response = await run_in_threadpool(
            supabase.table("accounts")
            .update({"balance": float(new_balance), "updated_at": datetime.now().isoformat()})
            .eq("id", str(account_id))
            .execute
        )
        
        if not update_response.data:
            logger.error(f"Failed to update account balance: {account_id}")
            return False
        
        return True
    
    except Exception as e:
        logger.error(f"Error updating account balance: {str(e)}")
        return False

async def handle_transaction_balance_update(
    transaction: Dict[str, Any],
    is_new: bool = True,
    old_transaction: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Update account balances when creating, updating, or deleting a transaction
    """
    account_id = transaction.get("account_id")
    if not account_id:
        return True  # No account to update
    
    amount = Decimal(str(transaction.get("amount", 0)))
    transaction_type = transaction.get("transaction_type", "")
    
    # For new transactions
    if is_new:
        if transaction_type == "income":
            return await update_account_balance(account_id, amount, "add")
        elif transaction_type == "expense":
            return await update_account_balance(account_id, amount, "subtract")
    
    # For updates (need to reverse old transaction and apply new one)
    elif old_transaction:
        old_amount = Decimal(str(old_transaction.get("amount", 0)))
        old_type = old_transaction.get("transaction_type", "")
        old_account_id = old_transaction.get("account_id")
        
        # Reverse old transaction's effect on balance
        if old_account_id:
            if old_type == "income":
                await update_account_balance(old_account_id, old_amount, "subtract")
            elif old_type == "expense":
                await update_account_balance(old_account_id, old_amount, "add")
        
        # Apply new transaction
        if transaction_type == "income":
            return await update_account_balance(account_id, amount, "add")
        elif transaction_type == "expense":
            return await update_account_balance(account_id, amount, "subtract")
    
    return True

async def get_category_summary(
    user_id: UUID,
    transaction_type: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None
) -> Dict[str, Dict[str, float]]:
    """
    Get summary of transactions by category
    """
    # Build query
    query = supabase.table("transactions").select("*").eq("user_id", str(user_id))
    
    if transaction_type:
        query = query.eq("transaction_type", transaction_type)
    
    if from_date:
        from_datetime = datetime.combine(from_date, datetime.min.time())
        query = query.gte("date", from_datetime.isoformat())
    
    if to_date:
        to_datetime = datetime.combine(to_date, datetime.max.time())
        query = query.lte("date", to_datetime.isoformat())
    
    # Execute query
    try:
        response = await run_in_threadpool(query.execute)
        transactions = response.data
    except Exception as e:
        logger.error(f"Error fetching transactions for category summary: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate category summary"
        )
    
    # Process data
    result: Dict[str, Dict[str, float]] = {}
    
    for txn in transactions:
        amount = Decimal(str(txn.get("amount", 0)))
        txn_type = txn.get("transaction_type", "")
        category = txn.get("category", "Uncategorized")
        
        if txn_type not in result:
            result[txn_type] = {}
        
        if category not in result[txn_type]:
            result[txn_type][category] = 0
        
        result[txn_type][category] += float(amount)
    
    return result 