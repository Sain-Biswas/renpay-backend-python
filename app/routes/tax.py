from fastapi import APIRouter, Depends, HTTPException, status, Query
from app.services.supabase_client import get_supabase, run_in_threadpool, with_retry
from app.models.tax import (
    GSTCalculationRequest, GSTCalculationResponse,
    TaxFilingRequest, TaxFilingResponse, TaxFilingSummary, TaxTransactionDetail,
    TaxSubmissionRequest, TaxSubmissionResponse,
    TaxReportRequest, TaxReportResponse, TaxReportSummary,
    TaxType, TaxPeriod
)
from app.models.transaction import TransactionType
from app.dependencies import get_current_user
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timezone, timedelta
from uuid import UUID
import calendar
import random
import string
import functools

router = APIRouter()

@router.get("/gst", response_model=GSTCalculationResponse)
async def calculate_gst(
    amount: float = Query(..., description="Amount for GST calculation"),
    tax_included: bool = Query(False, description="Whether the amount already includes tax"),
    tax_rate: float = Query(18.0, description="GST rate (default: 18%)"),
    current_user: dict = Depends(get_current_user)
):
    """Calculate GST for a given amount with caching for performance"""
    request = GSTCalculationRequest(
        amount=amount,
        tax_included=tax_included,
        tax_rate=tax_rate
    )
    
    # Use the factory method to create the response
    return GSTCalculationResponse.from_calculation(request)

@router.get("/calculate-for-invoice/{invoice_id}", response_model=GSTCalculationResponse)
async def calculate_gst_for_invoice(
    invoice_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Calculate GST for a specific invoice"""
    supabase = get_supabase()
    
    # First get the invoice
    invoice_result = await run_in_threadpool(
        lambda: supabase.table("invoices")
            .select("*")
            .eq("id", str(invoice_id))
            .eq("user_id", str(current_user["id"]))
            .execute()
    )
    
    if not invoice_result.data or len(invoice_result.data) == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    invoice = invoice_result.data[0]
    
    # Get invoice items for detailed calculation
    items_result = await run_in_threadpool(
        lambda: supabase.table("invoice_items")
            .select("*")
            .eq("invoice_id", str(invoice_id))
            .execute()
    )
    
    # Calculate tax for each item
    total_amount = 0.0
    tax_amount = 0.0
    original_amount = 0.0
    cgst = 0.0
    sgst = 0.0
    
    if items_result.data:
        for item in items_result.data:
            # Use the item's tax rate if available
            item_tax_rate = item.get("tax_rate", invoice.get("tax_rate", 18.0))
            item_amount = item.get("amount", 0.0)
            tax_included = item.get("tax_included", True)
            
            # Create a request for calculation
            request = GSTCalculationRequest(
                amount=item_amount,
                tax_included=tax_included,
                tax_rate=item_tax_rate
            )
            
            # Calculate tax
            result = GSTCalculationResponse.from_calculation(request)
            
            # Accumulate totals
            total_amount += result.total_amount
            tax_amount += result.tax_amount
            original_amount += result.original_amount
            cgst += result.breakdown.get("cgst", 0.0)
            sgst += result.breakdown.get("sgst", 0.0)
    else:
        # If no items, calculate based on invoice subtotal
        request = GSTCalculationRequest(
            amount=invoice.get("subtotal", 0.0),
            tax_included=False,  # Subtotal doesn't include tax
            tax_rate=invoice.get("tax_rate", 18.0)
        )
        result = GSTCalculationResponse.from_calculation(request)
        total_amount = result.total_amount
        tax_amount = result.tax_amount
        original_amount = result.original_amount
        cgst = result.breakdown.get("cgst", 0.0)
        sgst = result.breakdown.get("sgst", 0.0)
    
    # Return the calculation response
    return GSTCalculationResponse(
        original_amount=original_amount,
        tax_rate=invoice.get("tax_rate", 18.0),
        tax_amount=tax_amount,
        total_amount=total_amount,
        tax_included=False,  # Subtotal doesn't include tax
        breakdown={
            "cgst": cgst,
            "sgst": sgst,
            "igst": 0.0  # Set IGST to 0 for local transactions
        }
    )

@router.get("/filing", response_model=Dict[str, Any])
async def get_tax_filing(
    start_date: date = Query(..., description="Start date for the filing period"),
    end_date: date = Query(..., description="End date for the filing period"),
    tax_type: TaxType = Query(TaxType.GST, description="Type of tax filing"),
    period: TaxPeriod = Query(TaxPeriod.QUARTERLY, description="Filing period type"),
    current_user: dict = Depends(get_current_user)
):
    """Generate a tax filing for a specific period"""
    supabase = get_supabase()
    
    # Check if a filing already exists for this period
    existing_filing = await run_in_threadpool(
        lambda: supabase.table("tax_filings")
            .select("*")
            .eq("user_id", str(current_user["id"]))
            .eq("period_start", start_date.isoformat())
            .eq("period_end", end_date.isoformat())
            .eq("tax_type", tax_type.value)
            .execute()
    )
    
    if existing_filing.data and len(existing_filing.data) > 0:
        # Return existing filing
        filing = existing_filing.data[0]
        
        # Get transaction details
        transactions = await run_in_threadpool(
            lambda: supabase.table("tax_filing_items")
                .select("*")
                .eq("filing_id", filing["id"])
                .execute()
        )
        
        return {
            "filing_id": filing["id"],
            "summary": filing,
            "transactions": transactions.data if transactions.data else []
        }
    
    # Get all sales transactions for the period
    sales_transactions = await run_in_threadpool(
        lambda: supabase.table("transactions")
            .select("*")
            .eq("user_id", str(current_user["id"]))
            .eq("transaction_type", TransactionType.SALE.value)
            .gte("date", start_date.isoformat())
            .lte("date", end_date.isoformat())
            .execute()
    )
    
    # Get all expense transactions for the period
    expense_transactions = await run_in_threadpool(
        lambda: supabase.table("transactions")
            .select("*")
            .eq("user_id", str(current_user["id"]))
            .eq("transaction_type", TransactionType.EXPENSE.value)
            .gte("date", start_date.isoformat())
            .lte("date", end_date.isoformat())
            .execute()
    )
    
    # Calculate tax totals
    total_sales = sum(tx["amount"] for tx in sales_transactions.data) if sales_transactions.data else 0.0
    total_expenses = sum(tx["amount"] for tx in expense_transactions.data) if expense_transactions.data else 0.0
    
    # GST calculation logic
    tax_rate = 18.0  # Default GST rate
    total_tax_collected = total_sales * tax_rate / 100.0
    total_tax_paid = total_expenses * tax_rate / 100.0
    net_tax_liability = total_tax_collected - total_tax_paid
    
    # Create a new filing
    filing_data = {
        "user_id": str(current_user["id"]),
        "period_start": start_date.isoformat(),
        "period_end": end_date.isoformat(),
        "tax_type": tax_type.value,
        "period_type": period.value,
        "total_sales": float(total_sales),
        "total_tax_collected": float(total_tax_collected),
        "total_tax_paid": float(total_tax_paid),
        "net_tax_liability": float(net_tax_liability),
        "transaction_count": len(sales_transactions.data or []) + len(expense_transactions.data or []),
        "status": "draft",
        "auto_generated": True
    }
    
    filing_result = await run_in_threadpool(
        lambda: supabase.table("tax_filings")
            .insert(filing_data)
            .execute()
    )
    
    if not filing_result.data or len(filing_result.data) == 0:
        raise HTTPException(status_code=400, detail="Failed to create tax filing")
    
    filing = filing_result.data[0]
    filing_id = filing["id"]
    
    # Add transaction details
    transaction_items = []
    
    # Process sales transactions
    for tx in sales_transactions.data or []:
        tx_tax = tx["amount"] * tax_rate / 100.0
        item = {
            "filing_id": filing_id,
            "transaction_id": tx["id"],
            "amount": tx["amount"],
            "tax_amount": tx_tax,
            "type": "sale",
            "included_on": datetime.now(timezone.utc).isoformat()
        }
        transaction_items.append(item)
    
    # Process expense transactions
    for tx in expense_transactions.data or []:
        tx_tax = tx["amount"] * tax_rate / 100.0
        item = {
            "filing_id": filing_id,
            "transaction_id": tx["id"],
            "amount": tx["amount"],
            "tax_amount": tx_tax,
            "type": "expense",
            "included_on": datetime.now(timezone.utc).isoformat()
        }
        transaction_items.append(item)
    
    # Insert transaction items
    if transaction_items:
        await run_in_threadpool(
            lambda: supabase.table("tax_filing_items")
                .insert(transaction_items)
                .execute()
        )
    
    return {
        "filing_id": filing_id,
        "summary": filing,
        "transactions": transaction_items
    }

@router.get("/filing/auto-generate", response_model=Dict[str, Any])
async def auto_generate_tax_filing(
    period: TaxPeriod = Query(TaxPeriod.QUARTERLY, description="Filing period type"),
    tax_type: TaxType = Query(TaxType.GST, description="Type of tax filing"),
    current_user: dict = Depends(get_current_user)
):
    """Auto-generate a tax filing for the most recent period"""
    # Determine the period dates based on current date
    today = datetime.now(timezone.utc).date()
    
    if period == TaxPeriod.MONTHLY:
        # Previous month
        if today.month == 1:
            # January - go back to December of previous year
            start_date = date(today.year - 1, 12, 1)
            end_date = date(today.year - 1, 12, 31)
        else:
            # Any other month
            previous_month = today.month - 1
            year = today.year
            start_date = date(year, previous_month, 1)
            end_date = date(year, previous_month, calendar.monthrange(year, previous_month)[1])
    
    elif period == TaxPeriod.QUARTERLY:
        # Previous quarter
        current_quarter = (today.month - 1) // 3 + 1
        previous_quarter = current_quarter - 1 if current_quarter > 1 else 4
        year = today.year if previous_quarter < 4 else today.year - 1
        
        quarter_start_month = (previous_quarter - 1) * 3 + 1
        quarter_end_month = quarter_start_month + 2
        
        start_date = date(year, quarter_start_month, 1)
        end_date = date(year, quarter_end_month, calendar.monthrange(year, quarter_end_month)[1])
    
    elif period == TaxPeriod.ANNUALLY:
        # Previous year
        start_date = date(today.year - 1, 1, 1)
        end_date = date(today.year - 1, 12, 31)
    
    else:
        # Default to previous month
        if today.month == 1:
            start_date = date(today.year - 1, 12, 1)
            end_date = date(today.year - 1, 12, 31)
        else:
            previous_month = today.month - 1
            year = today.year
            start_date = date(year, previous_month, 1)
            end_date = date(year, previous_month, calendar.monthrange(year, previous_month)[1])
    
    # Reuse the existing filing generation logic
    return await get_tax_filing(
        start_date=start_date,
        end_date=end_date,
        tax_type=tax_type,
        period=period,
        current_user=current_user
    )

@router.post("/submit", response_model=Dict[str, Any])
async def submit_tax_filing(
    submission: TaxSubmissionRequest,
    current_user: dict = Depends(get_current_user)
):
    """Submit a tax filing and create a transaction for payment"""
    supabase = get_supabase()
    
    # Check if filing exists if filing_id is provided
    if submission.filing_id:
        filing_result = await run_in_threadpool(
            lambda: supabase.table("tax_filings")
                .select("*")
                .eq("id", str(submission.filing_id))
                .eq("user_id", str(current_user["id"]))
                .execute()
        )
        
        if not filing_result.data or len(filing_result.data) == 0:
            raise HTTPException(status_code=404, detail="Tax filing not found")
            
        filing = filing_result.data[0]
        
        # Set values from existing filing if not provided
        if not submission.period_start:
            submission.period_start = filing["period_start"]
        if not submission.period_end:
            submission.period_end = filing["period_end"]
        if not submission.tax_type:
            submission.tax_type = filing["tax_type"]
        if not submission.total_tax_liability:
            submission.total_tax_liability = filing["net_tax_liability"]
    
    # Create a confirmation number
    confirmation_number = f"TX-{datetime.now().strftime('%Y%m%d')}-{datetime.now().strftime('%H%M%S')}"
    
    # Create the submission record
    submission_data = {
        "user_id": str(current_user["id"]),
        "filing_id": str(submission.filing_id) if submission.filing_id else None,
        "period_start": submission.period_start.isoformat(),
        "period_end": submission.period_end.isoformat(),
        "tax_type": submission.tax_type.value,
        "total_tax_liability": float(submission.total_tax_liability),
        "payment_reference": submission.payment_reference,
        "confirmation_number": confirmation_number,
        "submission_date": datetime.now(timezone.utc).isoformat(),
        "status": "submitted",
        "notes": submission.notes
    }
    
    submission_result = await run_in_threadpool(
        lambda: supabase.table("tax_submissions")
            .insert(submission_data)
            .execute()
    )
    
    if not submission_result.data or len(submission_result.data) == 0:
        raise HTTPException(status_code=400, detail="Failed to create tax submission")
        
    submission_record = submission_result.data[0]
    
    # Create a transaction for this tax payment
    transaction_data = {
        "user_id": str(current_user["id"]),
        "amount": float(submission.total_tax_liability),
        "description": f"Tax payment - {submission.tax_type.value.upper()} for period {submission.period_start.strftime('%d/%m/%Y')} to {submission.period_end.strftime('%d/%m/%Y')}",
        "transaction_type": TransactionType.EXPENSE.value,
        "category": "Tax Payment",
        "reference_number": confirmation_number,
        "payment_method": "Bank Transfer",
        "date": datetime.now(timezone.utc).isoformat(),
        "notes": submission.notes,
        "related_tax_filing_id": str(submission.filing_id) if submission.filing_id else None
    }
    
    # Find default account
    account_result = await run_in_threadpool(
        lambda: supabase.table("accounts")
            .select("*")
            .eq("user_id", str(current_user["id"]))
            .eq("is_default", True)
            .execute()
    )
    
    if account_result.data and len(account_result.data) > 0:
        transaction_data["from_account_id"] = account_result.data[0]["id"]
    
    # Create the transaction
    transaction_result = await run_in_threadpool(
        lambda: supabase.table("transactions")
            .insert(transaction_data)
            .execute()
    )
    
    # If filing_id is provided, update the filing status
    if submission.filing_id:
        await run_in_threadpool(
            lambda: supabase.table("tax_filings")
                .update({"status": "submitted"})
                .eq("id", str(submission.filing_id))
                .execute()
        )
    
    return {
        "submission": submission_record,
        "transaction": transaction_result.data[0] if transaction_result.data else None,
        "confirmation_number": confirmation_number
    }

@router.get("/report", response_model=Dict[str, Any])
async def get_tax_report(
    year: int = Query(..., description="Year for the tax report"),
    tax_type: Optional[TaxType] = Query(None, description="Type of tax to filter by"),
    current_user: dict = Depends(get_current_user)
):
    """Get a tax report for a specific year"""
    supabase = get_supabase()
    
    # Set date range for the year
    start_date = date(year, 1, 1)
    end_date = date(year, 12, 31)
    
    # Build query
    query = supabase.table("tax_submissions").\
        select("*").\
        eq("user_id", str(current_user["id"])).\
        gte("period_start", start_date.isoformat()).\
        lte("period_end", end_date.isoformat())
    
    # Add tax type filter if provided
    if tax_type:
        query = query.eq("tax_type", tax_type.value)
    
    # Sort by date
    query = query.order("submission_date", desc=True)
    
    submissions_result = await run_in_threadpool(lambda: query.execute())
    
    # Get total tax paid for the year
    total_tax_paid = sum(
        submission["total_tax_liability"] 
        for submission in submissions_result.data or []
        if submission["status"] == "submitted"
    )
    
    # Get tax filings for the year
    filings_query = supabase.table("tax_filings").\
        select("*").\
        eq("user_id", str(current_user["id"])).\
        gte("period_start", start_date.isoformat()).\
        lte("period_end", end_date.isoformat())
    
    # Add tax type filter if provided
    if tax_type:
        filings_query = filings_query.eq("tax_type", tax_type.value)
    
    # Sort by date
    filings_query = filings_query.order("period_start", desc=False)
    
    filings_result = await run_in_threadpool(lambda: filings_query.execute())
    
    # Prepare the report
    return {
        "year": year,
        "total_tax_paid": float(total_tax_paid),
        "submissions": submissions_result.data or [],
        "filings": filings_result.data or []
    } 