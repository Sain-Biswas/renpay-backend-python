from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from app.services.supabase_client import get_supabase
from app.models.invoice import (
    Invoice, InvoiceCreate, InvoiceUpdate, InvoiceStatus,
    InvoiceItem, InvoiceItemCreate, InvoiceItemUpdate
)
from app.models.transaction import TransactionType
from app.dependencies import get_current_user
from app.routes.transactions import update_account_balance
from typing import List, Optional
from datetime import datetime, timedelta, date, calendar
from uuid import UUID
import random
import string

router = APIRouter()

def generate_invoice_number():
    """Generate a unique invoice number with prefix INV-YYYY-MM-XXXX"""
    now = datetime.now()
    year_month = now.strftime("%Y-%m")
    random_suffix = ''.join(random.choices(string.digits, k=4))
    return f"INV-{year_month}-{random_suffix}"

def calculate_invoice_taxes(subtotal: float, tax_rate: float = 18.0):
    """
    Calculate tax amount and total for an invoice.
    
    Args:
        subtotal: The subtotal amount before tax
        tax_rate: The tax rate (default: 18.0 for GST)
        
    Returns:
        tuple: (tax_amount, total_amount)
    """
    tax_amount = round(subtotal * tax_rate / 100, 2)
    total_amount = subtotal + tax_amount
    return tax_amount, total_amount

@router.get("/", response_model=List[Invoice])
async def get_invoices(
    current_user: dict = Depends(get_current_user),
    status: Optional[InvoiceStatus] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    customer_name: Optional[str] = None
):
    """
    List all invoices generated by the merchant, with optional filtering.
    """
    supabase = get_supabase()
    query = supabase.table("invoices").select("*").eq("user_id", current_user["id"])
    
    # Apply filters if provided
    if status:
        query = query.eq("status", status)
    if start_date:
        query = query.gte("issue_date", start_date.isoformat())
    if end_date:
        query = query.lte("issue_date", end_date.isoformat())
    if customer_name:
        query = query.ilike("customer_name", f"%{customer_name}%")
    
    invoices_result = query.execute()
    
    if not invoices_result.data:
        return []
    
    # For each invoice, fetch its items
    invoices = []
    for invoice in invoices_result.data:
        invoice_id = invoice["id"]
        items_result = supabase.table("invoice_items").select("*").eq("invoice_id", invoice_id).execute()
        invoice["items"] = items_result.data if items_result.data else []
        invoices.append(invoice)
    
    return invoices

@router.post("/", response_model=Invoice, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    invoice_data: InvoiceCreate,
    current_user: dict = Depends(get_current_user),
    create_transaction: bool = Query(False, description="Whether to create a transaction for this invoice")
):
    """
    Create a new invoice with GST compliance and customizable templates.
    Optionally create a transaction for this invoice.
    """
    supabase = get_supabase()
    
    # Generate invoice number if not provided
    if not invoice_data.invoice_number:
        invoice_data.invoice_number = generate_invoice_number()
    
    # Calculate subtotal from items
    items = invoice_data.items
    subtotal = sum(item.quantity * item.unit_price for item in items)
    
    # Calculate tax amount and total
    tax_amount, total_amount = calculate_invoice_taxes(subtotal, invoice_data.tax_rate)
    
    # Prepare invoice data for insertion
    invoice_dict = {
        "invoice_number": invoice_data.invoice_number,
        "customer_name": invoice_data.customer_name,
        "customer_email": invoice_data.customer_email,
        "customer_address": invoice_data.customer_address,
        "issue_date": invoice_data.issue_date.isoformat() if invoice_data.issue_date else datetime.now().isoformat(),
        "due_date": invoice_data.due_date.isoformat() if invoice_data.due_date else (datetime.now() + timedelta(days=30)).isoformat(),
        "subtotal": subtotal,
        "tax_rate": invoice_data.tax_rate,
        "tax_amount": tax_amount,
        "total_amount": total_amount,
        "status": invoice_data.status,
        "notes": invoice_data.notes,
        "template": invoice_data.template,
        "user_id": current_user["id"]
    }
    
    try:
        # Insert invoice
        invoice_result = supabase.table("invoices").insert(invoice_dict).execute()
        
        if not invoice_result.data or len(invoice_result.data) == 0:
            raise HTTPException(status_code=400, detail="Failed to create invoice")
        
        invoice_id = invoice_result.data[0]["id"]
        
        # Insert invoice items
        for item in items:
            item_dict = {
                "invoice_id": invoice_id,
                "description": item.description,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "amount": item.amount if item.amount else round(item.quantity * item.unit_price, 2),
                "tax_included": item.tax_included
            }
            supabase.table("invoice_items").insert(item_dict).execute()
        
        # Create a transaction if requested
        if create_transaction and invoice_data.status == InvoiceStatus.PAID:
            # Find default account or create one
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
            
            # Create transaction
            transaction_data = {
                "amount": total_amount,
                "description": f"Payment for invoice {invoice_data.invoice_number}",
                "transaction_type": TransactionType.SALE,
                "category": "Invoice Payment",
                "date": invoice_dict["issue_date"],
                "user_id": current_user["id"],
                "account_id": account_id
            }
            
            transaction_result = supabase.table("transactions").insert(transaction_data).execute()
            
            # Update account balance
            if transaction_result.data and len(transaction_result.data) > 0:
                await update_account_balance(
                    supabase,
                    UUID(account_id),
                    total_amount,
                    TransactionType.SALE
                )
        
        # Fetch the complete invoice with items
        complete_invoice = supabase.table("invoices").select("*").eq("id", invoice_id).execute()
        items_result = supabase.table("invoice_items").select("*").eq("invoice_id", invoice_id).execute()
        
        result = complete_invoice.data[0]
        result["items"] = items_result.data if items_result.data else []
        
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{invoice_id}", response_model=Invoice)
async def get_invoice(
    invoice_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """
    Retrieve detailed information for a specific invoice.
    """
    supabase = get_supabase()
    
    # Fetch the invoice
    invoice_result = supabase.table("invoices").select("*").eq("id", str(invoice_id)).eq("user_id", current_user["id"]).execute()
    
    if not invoice_result.data or len(invoice_result.data) == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    # Fetch the invoice items
    items_result = supabase.table("invoice_items").select("*").eq("invoice_id", str(invoice_id)).execute()
    
    result = invoice_result.data[0]
    result["items"] = items_result.data if items_result.data else []
    
    return result

@router.put("/{invoice_id}", response_model=Invoice)
async def update_invoice(
    invoice_id: UUID,
    invoice_update: InvoiceUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Update an existing invoice (e.g., change status, add details).
    """
    supabase = get_supabase()
    
    # Check if invoice exists and belongs to the user
    existing = supabase.table("invoices").select("*").eq("id", str(invoice_id)).eq("user_id", current_user["id"]).execute()
    
    if not existing.data or len(existing.data) == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    existing_invoice = existing.data[0]
    
    # Filter out None values
    update_data = {k: v for k, v in invoice_update.dict().items() if v is not None}
    
    # Convert datetime objects to ISO format strings
    if "issue_date" in update_data and update_data["issue_date"]:
        update_data["issue_date"] = update_data["issue_date"].isoformat()
    if "due_date" in update_data and update_data["due_date"]:
        update_data["due_date"] = update_data["due_date"].isoformat()
    
    # If tax_rate is updated, recalculate tax_amount and total_amount
    if "tax_rate" in update_data:
        tax_amount, total_amount = calculate_invoice_taxes(existing_invoice["subtotal"], update_data["tax_rate"])
        update_data["tax_amount"] = tax_amount
        update_data["total_amount"] = total_amount
    
    try:
        # If status is changing to PAID, create a transaction
        if "status" in update_data and update_data["status"] == InvoiceStatus.PAID and existing_invoice["status"] != InvoiceStatus.PAID:
            # Find default account or create one
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
            
            # Create transaction
            transaction_data = {
                "amount": existing_invoice["total_amount"],
                "description": f"Payment for invoice {existing_invoice['invoice_number']}",
                "transaction_type": TransactionType.SALE,
                "category": "Invoice Payment",
                "date": datetime.now().isoformat(),
                "user_id": current_user["id"],
                "account_id": account_id
            }
            
            transaction_result = supabase.table("transactions").insert(transaction_data).execute()
            
            # Update account balance
            if transaction_result.data and len(transaction_result.data) > 0:
                await update_account_balance(
                    supabase,
                    UUID(account_id),
                    existing_invoice["total_amount"],
                    TransactionType.SALE
                )
        
        # Update the invoice
        result = supabase.table("invoices").update(update_data).eq("id", str(invoice_id)).execute()
        
        # Fetch the updated invoice with items
        updated_invoice = result.data[0]
        items_result = supabase.table("invoice_items").select("*").eq("invoice_id", str(invoice_id)).execute()
        updated_invoice["items"] = items_result.data if items_result.data else []
        
        return updated_invoice
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{invoice_id}/mark-as-paid", response_model=Invoice)
async def mark_invoice_as_paid(
    invoice_id: UUID,
    current_user: dict = Depends(get_current_user),
    create_tax_filing: bool = Query(False, description="Whether to include this invoice in a tax filing")
):
    """
    Mark an invoice as paid and create a corresponding transaction.
    Optionally include this invoice in a tax filing.
    """
    supabase = get_supabase()
    
    # Check if invoice exists and belongs to the user
    existing = supabase.table("invoices").select("*").eq("id", str(invoice_id)).eq("user_id", current_user["id"]).execute()
    
    if not existing.data or len(existing.data) == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    existing_invoice = existing.data[0]
    
    if existing_invoice["status"] == InvoiceStatus.PAID:
        raise HTTPException(status_code=400, detail="Invoice is already marked as paid")
    
    try:
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
        
        # Create transaction
        transaction_data = {
            "amount": existing_invoice["total_amount"],
            "description": f"Payment for invoice {existing_invoice['invoice_number']}",
            "transaction_type": TransactionType.SALE,
            "category": "Invoice Payment",
            "date": datetime.now().isoformat(),
            "user_id": current_user["id"],
            "account_id": account_id
        }
        
        transaction_result = supabase.table("transactions").insert(transaction_data).execute()
        
        # Update account balance
        if transaction_result.data and len(transaction_result.data) > 0:
            await update_account_balance(
                supabase,
                UUID(account_id),
                existing_invoice["total_amount"],
                TransactionType.SALE
            )
            
            # Add transaction ID to invoice notes for reference
            notes = existing_invoice["notes"] or ""
            updated_notes = f"{notes}\nTransaction ID: {transaction_result.data[0]['id']}"
            
            # Update the invoice status and notes
            result = supabase.table("invoices").update({
                "status": InvoiceStatus.PAID,
                "notes": updated_notes
            }).eq("id", str(invoice_id)).execute()
        else:
            # Just update the invoice status
            result = supabase.table("invoices").update({
                "status": InvoiceStatus.PAID
            }).eq("id", str(invoice_id)).execute()
        
        # If requested, include this invoice in a tax filing
        if create_tax_filing:
            # Get the current quarter dates
            today = date.today()
            current_quarter = (today.month - 1) // 3 + 1
            start_month = (current_quarter - 1) * 3 + 1
            end_month = current_quarter * 3
            start_date = date(today.year, start_month, 1)
            end_date = date(today.year, end_month, calendar.monthrange(today.year, end_month)[1])
            
            # Check if a filing already exists for this period
            existing_filing = supabase.table("tax_filings").select("*").eq("user_id", current_user["id"]).eq("period_start", start_date.isoformat()).eq("period_end", end_date.isoformat()).eq("tax_type", "gst").execute()
            
            if existing_filing.data and len(existing_filing.data) > 0:
                # Update existing filing
                filing = existing_filing.data[0]
                
                # Update the filing with this invoice's tax amount
                new_total_sales = filing["total_sales"] + existing_invoice["subtotal"]
                new_tax_collected = filing["total_tax_collected"] + existing_invoice["tax_amount"]
                new_net_liability = filing["net_tax_liability"] + existing_invoice["tax_amount"]
                
                supabase.table("tax_filings").update({
                    "total_sales": new_total_sales,
                    "total_tax_collected": new_tax_collected,
                    "net_tax_liability": new_net_liability,
                    "transaction_count": filing["transaction_count"] + 1
                }).eq("id", filing["id"]).execute()
            else:
                # Create a new filing
                filing_data = {
                    "period_start": start_date.isoformat(),
                    "period_end": end_date.isoformat(),
                    "tax_type": "gst",
                    "period_type": "quarterly",
                    "total_sales": existing_invoice["subtotal"],
                    "total_tax_collected": existing_invoice["tax_amount"],
                    "total_tax_paid": 0.0,
                    "net_tax_liability": existing_invoice["tax_amount"],
                    "transaction_count": 1,
                    "status": "draft",
                    "user_id": current_user["id"]
                }
                
                supabase.table("tax_filings").insert(filing_data).execute()
        
        # Fetch the updated invoice with items
        updated_invoice = result.data[0]
        items_result = supabase.table("invoice_items").select("*").eq("invoice_id", str(invoice_id)).execute()
        updated_invoice["items"] = items_result.data if items_result.data else []
        
        return updated_invoice
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invoice(
    invoice_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """
    Remove an unwanted or duplicate invoice.
    """
    supabase = get_supabase()
    
    # Check if invoice exists and belongs to the user
    existing = supabase.table("invoices").select("*").eq("id", str(invoice_id)).eq("user_id", current_user["id"]).execute()
    
    if not existing.data or len(existing.data) == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    try:
        # Delete the invoice (cascade will delete related items)
        supabase.table("invoices").delete().eq("id", str(invoice_id)).execute()
        return None
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{invoice_id}/recalculate-taxes", response_model=Invoice)
async def recalculate_invoice_taxes(
    invoice_id: UUID,
    tax_rate: Optional[float] = Query(None, description="New tax rate to apply. If not provided, uses the existing rate."),
    current_user: dict = Depends(get_current_user)
):
    """
    Recalculate taxes for an existing invoice.
    """
    supabase = get_supabase()
    
    # Check if invoice exists and belongs to the user
    existing = supabase.table("invoices").select("*").eq("id", str(invoice_id)).eq("user_id", current_user["id"]).execute()
    
    if not existing.data or len(existing.data) == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    invoice = existing.data[0]
    
    # Get invoice items to recalculate subtotal
    items_result = supabase.table("invoice_items").select("*").eq("invoice_id", str(invoice_id)).execute()
    
    if not items_result.data:
        raise HTTPException(status_code=400, detail="Invoice has no items")
    
    # Recalculate subtotal
    subtotal = sum(item["quantity"] * item["unit_price"] for item in items_result.data)
    
    # Use provided tax rate or existing one
    rate_to_use = tax_rate if tax_rate is not None else invoice["tax_rate"]
    
    # Calculate tax amount and total
    tax_amount, total_amount = calculate_invoice_taxes(subtotal, rate_to_use)
    
    # Update invoice
    update_data = {
        "subtotal": subtotal,
        "tax_rate": rate_to_use,
        "tax_amount": tax_amount,
        "total_amount": total_amount
    }
    
    try:
        result = supabase.table("invoices").update(update_data).eq("id", str(invoice_id)).execute()
        
        # Fetch the updated invoice with items
        updated_invoice = result.data[0]
        updated_invoice["items"] = items_result.data
        
        return updated_invoice
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) 