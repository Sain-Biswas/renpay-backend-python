from fastapi import APIRouter, Depends, HTTPException, status, Query
from app.services.supabase_client import get_supabase
from app.models.tax import (
    GSTCalculationRequest, GSTCalculationResponse,
    TaxFilingRequest, TaxFilingResponse, TaxFilingSummary, TaxTransactionDetail,
    TaxSubmissionRequest, TaxSubmissionResponse,
    TaxReportRequest, TaxReportResponse, TaxReportSummary,
    TaxType, TaxPeriod
)
from app.models.transaction import TransactionType
from app.dependencies import get_current_user
from typing import List, Optional, Dict
from datetime import datetime, date, timedelta
from uuid import UUID
import calendar
import random
import string

router = APIRouter()

@router.get("/gst", response_model=GSTCalculationResponse)
async def calculate_gst(
    amount: float = Query(..., description="Amount for GST calculation"),
    tax_included: bool = Query(False, description="Whether the amount already includes tax"),
    tax_rate: float = Query(18.0, description="GST rate (default: 18%)"),
    current_user: dict = Depends(get_current_user)
):
    """
    Calculate GST for a given transaction amount.
    """
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero")
    
    if tax_rate <= 0:
        raise HTTPException(status_code=400, detail="Tax rate must be greater than zero")
    
    # Calculate tax amount and total
    if tax_included:
        # If tax is included, we need to extract it
        original_amount = amount * 100 / (100 + tax_rate)
        tax_amount = amount - original_amount
    else:
        # If tax is not included, we add it
        original_amount = amount
        tax_amount = amount * tax_rate / 100
    
    total_amount = original_amount + tax_amount
    
    # Calculate CGST, SGST, IGST breakdown (for India's GST system)
    # In a real application, this would depend on the location of buyer and seller
    # For simplicity, we're splitting it 50/50 between CGST and SGST
    half_tax = tax_amount / 2
    
    return GSTCalculationResponse(
        original_amount=round(original_amount, 2),
        tax_rate=tax_rate,
        tax_amount=round(tax_amount, 2),
        total_amount=round(total_amount, 2),
        tax_included=tax_included,
        breakdown={
            "cgst": round(half_tax, 2),
            "sgst": round(half_tax, 2),
            "igst": 0.0
        }
    )

@router.get("/calculate-for-invoice/{invoice_id}", response_model=GSTCalculationResponse)
async def calculate_gst_for_invoice(
    invoice_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """
    Calculate GST for a specific invoice.
    """
    supabase = get_supabase()
    
    # Get the invoice
    invoice_result = supabase.table("invoices").select("*").eq("id", str(invoice_id)).eq("user_id", current_user["id"]).execute()
    
    if not invoice_result.data or len(invoice_result.data) == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    invoice = invoice_result.data[0]
    
    # Calculate GST
    subtotal = invoice["subtotal"]
    tax_rate = invoice["tax_rate"]
    
    # Calculate tax amount
    tax_amount = invoice["tax_amount"]
    total_amount = invoice["total_amount"]
    
    # Calculate CGST, SGST breakdown
    half_tax = tax_amount / 2
    
    return GSTCalculationResponse(
        original_amount=subtotal,
        tax_rate=tax_rate,
        tax_amount=tax_amount,
        total_amount=total_amount,
        tax_included=False,  # Invoices typically show amounts without tax included
        breakdown={
            "cgst": round(half_tax, 2),
            "sgst": round(half_tax, 2),
            "igst": 0.0
        }
    )

@router.get("/filing", response_model=TaxFilingResponse)
async def get_tax_filing(
    start_date: date = Query(..., description="Start date for the filing period"),
    end_date: date = Query(..., description="End date for the filing period"),
    tax_type: TaxType = Query(TaxType.GST, description="Type of tax filing"),
    period: TaxPeriod = Query(TaxPeriod.QUARTERLY, description="Filing period type"),
    current_user: dict = Depends(get_current_user)
):
    """
    Retrieve tax filing data prepared from recent transactions.
    """
    supabase = get_supabase()
    
    # Check if a filing already exists for this period
    existing_filing = supabase.table("tax_filings").select("*").eq("user_id", current_user["id"]).eq("period_start", start_date.isoformat()).eq("period_end", end_date.isoformat()).eq("tax_type", tax_type).execute()
    
    if existing_filing.data and len(existing_filing.data) > 0:
        # Return the existing filing data
        filing = existing_filing.data[0]
        
        # Get transactions for this period
        transactions = supabase.table("transactions").select("*").eq("user_id", current_user["id"]).gte("date", start_date.isoformat()).lte("date", end_date.isoformat()).execute()
        
        # Get invoices for this period
        invoices = supabase.table("invoices").select("*").eq("user_id", current_user["id"]).gte("issue_date", start_date.isoformat()).lte("issue_date", end_date.isoformat()).execute()
        
        # Prepare transaction details
        transaction_details = []
        for transaction in transactions.data:
            # Only include sales and expenses for GST
            if tax_type == TaxType.GST and transaction["transaction_type"] in ["sale", "expense"]:
                # For sales, we collected tax; for expenses, we paid tax
                is_sale = transaction["transaction_type"] == "sale"
                
                # Find matching invoice for sales to get tax details
                tax_amount = 0.0
                if is_sale:
                    for invoice in invoices.data:
                        if invoice.get("notes") and transaction["id"] in invoice["notes"]:
                            tax_amount = invoice["tax_amount"]
                            break
                    
                    # If no matching invoice, estimate tax (18% GST)
                    if tax_amount == 0.0:
                        tax_amount = transaction["amount"] * 0.18
                else:
                    # For expenses, estimate tax paid (18% GST)
                    tax_amount = transaction["amount"] * 0.18 / 1.18
                
                transaction_details.append(TaxTransactionDetail(
                    transaction_id=transaction["id"],
                    date=transaction["date"],
                    description=transaction["description"],
                    amount=transaction["amount"],
                    tax_amount=round(tax_amount, 2),
                    transaction_type=transaction["transaction_type"],
                    category=transaction.get("category")
                ))
        
        # Create summary from filing data
        summary = TaxFilingSummary(
            period_start=filing["period_start"],
            period_end=filing["period_end"],
            tax_type=filing["tax_type"],
            total_sales=filing["total_sales"],
            total_tax_collected=filing["total_tax_collected"],
            total_tax_paid=filing["total_tax_paid"],
            net_tax_liability=filing["net_tax_liability"],
            transaction_count=filing["transaction_count"],
            status=filing["status"]
        )
        
        return TaxFilingResponse(
            summary=summary,
            transactions=transaction_details
        )
    
    # If no filing exists, calculate it from transactions
    transactions = supabase.table("transactions").select("*").eq("user_id", current_user["id"]).gte("date", start_date.isoformat()).lte("date", end_date.isoformat()).execute()
    
    if not transactions.data:
        raise HTTPException(status_code=404, detail="No transactions found for the specified period")
    
    # Get invoices for this period (to get accurate tax amounts)
    invoices = supabase.table("invoices").select("*").eq("user_id", current_user["id"]).gte("issue_date", start_date.isoformat()).lte("issue_date", end_date.isoformat()).execute()
    
    # Calculate tax filing data
    total_sales = 0.0
    total_tax_collected = 0.0
    total_tax_paid = 0.0
    transaction_count = 0
    transaction_details = []
    
    for transaction in transactions.data:
        # Only include sales and expenses for GST
        if tax_type == TaxType.GST and transaction["transaction_type"] in ["sale", "expense"]:
            transaction_count += 1
            
            # For sales, we collected tax; for expenses, we paid tax
            is_sale = transaction["transaction_type"] == "sale"
            
            if is_sale:
                total_sales += transaction["amount"]
                
                # Find matching invoice to get tax details
                tax_amount = 0.0
                for invoice in invoices.data:
                    if invoice.get("notes") and transaction["id"] in invoice["notes"]:
                        tax_amount = invoice["tax_amount"]
                        break
                
                # If no matching invoice, estimate tax (18% GST)
                if tax_amount == 0.0:
                    tax_amount = transaction["amount"] * 0.18
                
                total_tax_collected += tax_amount
            else:
                # For expenses, estimate tax paid (18% GST)
                tax_amount = transaction["amount"] * 0.18 / 1.18
                total_tax_paid += tax_amount
            
            transaction_details.append(TaxTransactionDetail(
                transaction_id=transaction["id"],
                date=transaction["date"],
                description=transaction["description"],
                amount=transaction["amount"],
                tax_amount=round(tax_amount, 2),
                transaction_type=transaction["transaction_type"],
                category=transaction.get("category")
            ))
    
    # Calculate net tax liability
    net_tax_liability = total_tax_collected - total_tax_paid
    
    # Create a new tax filing record
    filing_data = {
        "period_start": start_date.isoformat(),
        "period_end": end_date.isoformat(),
        "tax_type": tax_type,
        "period_type": period,
        "total_sales": total_sales,
        "total_tax_collected": total_tax_collected,
        "total_tax_paid": total_tax_paid,
        "net_tax_liability": net_tax_liability,
        "transaction_count": transaction_count,
        "status": "draft",
        "user_id": current_user["id"]
    }
    
    filing_result = supabase.table("tax_filings").insert(filing_data).execute()
    
    if not filing_result.data or len(filing_result.data) == 0:
        raise HTTPException(status_code=500, detail="Failed to create tax filing record")
    
    # Create summary
    summary = TaxFilingSummary(
        period_start=start_date,
        period_end=end_date,
        tax_type=tax_type,
        total_sales=total_sales,
        total_tax_collected=total_tax_collected,
        total_tax_paid=total_tax_paid,
        net_tax_liability=net_tax_liability,
        transaction_count=transaction_count,
        status="draft"
    )
    
    return TaxFilingResponse(
        summary=summary,
        transactions=transaction_details
    )

@router.get("/filing/auto-generate", response_model=TaxFilingResponse)
async def auto_generate_tax_filing(
    period: TaxPeriod = Query(TaxPeriod.QUARTERLY, description="Filing period type"),
    tax_type: TaxType = Query(TaxType.GST, description="Type of tax filing"),
    current_user: dict = Depends(get_current_user)
):
    """
    Automatically generate a tax filing for the most recent period.
    """
    # Calculate the appropriate date range based on the period
    today = date.today()
    
    if period == TaxPeriod.MONTHLY:
        # Last month
        if today.month == 1:
            # January - go back to December of previous year
            start_date = date(today.year - 1, 12, 1)
            end_date = date(today.year - 1, 12, 31)
        else:
            # Any other month
            previous_month = today.month - 1
            last_day = calendar.monthrange(today.year, previous_month)[1]
            start_date = date(today.year, previous_month, 1)
            end_date = date(today.year, previous_month, last_day)
    
    elif period == TaxPeriod.QUARTERLY:
        # Determine which quarter we're in and get the previous one
        current_quarter = (today.month - 1) // 3 + 1
        previous_quarter = current_quarter - 1 if current_quarter > 1 else 4
        
        if previous_quarter == 4 and current_quarter == 1:
            # Q4 of previous year
            start_date = date(today.year - 1, 10, 1)
            end_date = date(today.year - 1, 12, 31)
        else:
            # Q1, Q2, or Q3 of current year
            start_month = (previous_quarter - 1) * 3 + 1
            end_month = previous_quarter * 3
            start_date = date(today.year, start_month, 1)
            end_date = date(today.year, end_month, calendar.monthrange(today.year, end_month)[1])
    
    else:  # ANNUALLY
        # Previous year
        start_date = date(today.year - 1, 1, 1)
        end_date = date(today.year - 1, 12, 31)
    
    # Call the regular filing endpoint with the calculated dates
    return await get_tax_filing(start_date, end_date, tax_type, period, current_user)

@router.post("/submit", response_model=TaxSubmissionResponse)
async def submit_tax_filing(
    submission: TaxSubmissionRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Submit tax filing information (simulated integration with government APIs).
    """
    supabase = get_supabase()
    
    # Check if filing exists if filing_id is provided
    if submission.filing_id:
        filing = supabase.table("tax_filings").select("*").eq("id", str(submission.filing_id)).eq("user_id", current_user["id"]).execute()
        
        if not filing.data or len(filing.data) == 0:
            raise HTTPException(status_code=404, detail="Tax filing not found")
        
        filing = filing.data[0]
        
        # Check if filing is already submitted
        if filing["status"] != "draft":
            raise HTTPException(status_code=400, detail=f"Tax filing is already {filing['status']}")
        
        # Update filing status
        supabase.table("tax_filings").update({"status": "submitted"}).eq("id", str(submission.filing_id)).execute()
    else:
        # Check if a filing exists for this period
        filing = supabase.table("tax_filings").select("*").eq("user_id", current_user["id"]).eq("period_start", submission.period_start.isoformat()).eq("period_end", submission.period_end.isoformat()).eq("tax_type", submission.tax_type).execute()
        
        if filing.data and len(filing.data) > 0:
            filing = filing.data[0]
            submission.filing_id = filing["id"]
            
            # Update filing status
            supabase.table("tax_filings").update({"status": "submitted"}).eq("id", filing["id"]).execute()
        else:
            # Create a new filing record
            filing_data = {
                "period_start": submission.period_start.isoformat(),
                "period_end": submission.period_end.isoformat(),
                "tax_type": submission.tax_type,
                "net_tax_liability": submission.total_tax_liability,
                "status": "submitted",
                "user_id": current_user["id"]
            }
            
            filing_result = supabase.table("tax_filings").insert(filing_data).execute()
            
            if not filing_result.data or len(filing_result.data) == 0:
                raise HTTPException(status_code=500, detail="Failed to create tax filing record")
            
            submission.filing_id = filing_result.data[0]["id"]
    
    # Generate a confirmation number (in a real app, this would come from the tax authority)
    confirmation_number = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
    
    # Create submission record
    submission_data = {
        "filing_id": str(submission.filing_id),
        "submission_date": datetime.now().isoformat(),
        "period_start": submission.period_start.isoformat(),
        "period_end": submission.period_end.isoformat(),
        "tax_type": submission.tax_type,
        "total_tax_liability": submission.total_tax_liability,
        "payment_reference": submission.payment_reference,
        "confirmation_number": confirmation_number,
        "status": "submitted",  # In a real app, this might start as "pending" until confirmed
        "notes": submission.notes,
        "user_id": current_user["id"]
    }
    
    submission_result = supabase.table("tax_submissions").insert(submission_data).execute()
    
    if not submission_result.data or len(submission_result.data) == 0:
        raise HTTPException(status_code=500, detail="Failed to create tax submission record")
    
    submission_record = submission_result.data[0]
    
    # Create a transaction for the tax payment if payment reference is provided
    if submission.payment_reference:
        # Find or create a default account
        accounts = supabase.table("accounts").select("*").eq("user_id", current_user["id"]).execute()
        
        account_id = None
        if not accounts.data or len(accounts.data) == 0:
            # Create a default account
            default_account = {
                "name": "Default Account",
                "balance": 0.0,
                "user_id": current_user["id"]
            }
            account_result = supabase.table("accounts").insert(default_account).execute()
            account_id = account_result.data[0]["id"]
        else:
            account_id = accounts.data[0]["id"]
        
        # Create a transaction for the tax payment
        transaction_data = {
            "amount": submission.total_tax_liability,
            "description": f"Tax payment for {submission.tax_type} ({submission.period_start.isoformat()} to {submission.period_end.isoformat()})",
            "transaction_type": "expense",
            "category": "Tax Payment",
            "date": datetime.now().isoformat(),
            "user_id": current_user["id"],
            "account_id": account_id
        }
        
        supabase.table("transactions").insert(transaction_data).execute()
        
        # Update account balance
        account = supabase.table("accounts").select("*").eq("id", account_id).execute().data[0]
        new_balance = account["balance"] - submission.total_tax_liability
        supabase.table("accounts").update({"balance": new_balance}).eq("id", account_id).execute()
    
    return TaxSubmissionResponse(
        id=submission_record["id"],
        submission_date=submission_record["submission_date"],
        period_start=submission_record["period_start"],
        period_end=submission_record["period_end"],
        tax_type=submission_record["tax_type"],
        total_tax_liability=submission_record["total_tax_liability"],
        payment_reference=submission_record["payment_reference"],
        confirmation_number=submission_record["confirmation_number"],
        status=submission_record["status"]
    )

@router.get("/report", response_model=TaxReportResponse)
async def get_tax_report(
    year: int = Query(..., description="Year for the tax report"),
    tax_type: Optional[TaxType] = Query(None, description="Type of tax to filter by"),
    current_user: dict = Depends(get_current_user)
):
    """
    Fetch historical tax reports to view past filings and compliance status.
    """
    supabase = get_supabase()
    
    # Calculate date range for the year
    start_date = date(year, 1, 1)
    end_date = date(year, 12, 31)
    
    # Query tax submissions for the year
    query = supabase.table("tax_submissions").select("*").eq("user_id", current_user["id"]).gte("period_start", start_date.isoformat()).lte("period_end", end_date.isoformat())
    
    if tax_type:
        query = query.eq("tax_type", tax_type)
    
    submissions = query.execute()
    
    if not submissions.data:
        # Check if there are any filings for this year
        query = supabase.table("tax_filings").select("*").eq("user_id", current_user["id"]).gte("period_start", start_date.isoformat()).lte("period_end", end_date.isoformat())
        
        if tax_type:
            query = query.eq("tax_type", tax_type)
        
        filings = query.execute()
        
        if not filings.data:
            return TaxReportResponse(
                year=year,
                total_tax_paid=0.0,
                filings=[]
            )
        
        # Create report from filings
        filing_summaries = []
        total_tax_paid = 0.0
        
        for filing in filings.data:
            if filing["status"] == "submitted" or filing["status"] == "accepted":
                total_tax_paid += filing["net_tax_liability"]
            
            filing_summaries.append(TaxReportSummary(
                id=filing["id"],
                period_start=filing["period_start"],
                period_end=filing["period_end"],
                tax_type=filing["tax_type"],
                total_tax_liability=filing["net_tax_liability"],
                submission_date=None,  # No submission date since not submitted
                status=filing["status"]
            ))
        
        return TaxReportResponse(
            year=year,
            total_tax_paid=total_tax_paid,
            filings=filing_summaries
        )
    
    # Create report from submissions
    filing_summaries = []
    total_tax_paid = 0.0
    
    for submission in submissions.data:
        if submission["status"] == "submitted" or submission["status"] == "accepted":
            total_tax_paid += submission["total_tax_liability"]
        
        filing_summaries.append(TaxReportSummary(
            id=submission["id"],
            period_start=submission["period_start"],
            period_end=submission["period_end"],
            tax_type=submission["tax_type"],
            total_tax_liability=submission["total_tax_liability"],
            submission_date=submission["submission_date"],
            status=submission["status"]
        ))
    
    return TaxReportResponse(
        year=year,
        total_tax_paid=total_tax_paid,
        filings=filing_summaries
    ) 