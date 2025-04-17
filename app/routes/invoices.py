from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from fastapi.responses import ORJSONResponse
from app.services.supabase_client import get_supabase, run_in_threadpool, with_retry
from app.models.invoice import (
    Invoice, InvoiceCreate, InvoiceUpdate, InvoiceStatus,
    InvoiceItem, InvoiceItemCreate, InvoiceItemUpdate, InvoiceInDB, InvoiceSummary, InvoiceWithItems
)
from app.models.transaction import TransactionType
from app.dependencies import get_current_user
from app.routes.transactions import update_account_balance
from typing import List, Optional, Dict, Any, Annotated
from datetime import datetime, timedelta, date, timezone
import calendar
from uuid import UUID, uuid4
import random
import string
import orjson

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

@router.get("/", response_model=List[InvoiceInDB], response_class=ORJSONResponse)
async def get_invoices(
    current_user: dict = Depends(get_current_user),
    status: Optional[InvoiceStatus] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    client_id: Optional[UUID] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort_by: str = "created_at",
    sort_order: str = "desc"
):
    """
    Retrieve all invoices for the current user with filtering options
    """
    supabase = get_supabase()
    
    # Start building the query
    query = supabase.table("invoices").select("*").eq("user_id", current_user["id"])
    
    # Apply filters
    if status:
        query = query.eq("status", status.value)
    
    if from_date:
        query = query.gte("invoice_date", from_date.isoformat())
    
    if to_date:
        query = query.lte("invoice_date", to_date.isoformat())
    
    if client_id:
        query = query.eq("client_id", str(client_id))
    
    # Apply sorting
    order = sort_order.lower()
    if order not in ["asc", "desc"]:
        order = "desc"
    
    valid_sort_fields = ["created_at", "invoice_date", "due_date", "amount", "status"]
    if sort_by not in valid_sort_fields:
        sort_by = "created_at"
    
    query = query.order(sort_by, order=order)
    
    # Apply pagination
    query = query.range(offset, offset + limit - 1)
    
    # Execute query
    result = await run_in_threadpool(with_retry(lambda: query.execute()))
    
    if not result.data:
        return []
    
    return result.data

@router.get("/summary", response_model=InvoiceSummary, response_class=ORJSONResponse)
async def get_invoice_summary(
    current_user: dict = Depends(get_current_user),
    period: Annotated[str, Query(description="Period to summarize: 'day', 'week', 'month', 'year'")] = "month"
):
    """
    Get summary statistics for invoices
    """
    supabase = get_supabase()
    
    # Calculate date ranges based on period
    now = datetime.now(timezone.utc)
    
    if period == "day":
        from_date = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    elif period == "week":
        # Get the start of the current week (Monday)
        from_date = now - timedelta(days=now.weekday())
        from_date = datetime(from_date.year, from_date.month, from_date.day, tzinfo=timezone.utc)
    elif period == "year":
        from_date = datetime(now.year, 1, 1, tzinfo=timezone.utc)
    else:  # Default to month
        from_date = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    
    # Get all invoices for the period
    result = await run_in_threadpool(
        with_retry(lambda: supabase.table("invoices")
        .select("*")
        .eq("user_id", current_user["id"])
        .gte("created_at", from_date.isoformat())
        .execute())
    )
    
    if not result.data:
        return {
            "total_invoices": 0,
            "paid_invoices": 0,
            "pending_invoices": 0,
            "overdue_invoices": 0,
            "total_amount": 0,
            "paid_amount": 0,
            "pending_amount": 0,
            "overdue_amount": 0,
            "period": period
        }
    
    invoices = result.data
    
    # Calculate summary statistics
    total_invoices = len(invoices)
    paid_invoices = sum(1 for inv in invoices if inv["status"] == InvoiceStatus.PAID.value)
    pending_invoices = sum(1 for inv in invoices if inv["status"] == InvoiceStatus.PENDING.value)
    overdue_invoices = sum(1 for inv in invoices if inv["status"] == InvoiceStatus.OVERDUE.value)
    
    total_amount = sum(inv["total_amount"] for inv in invoices)
    paid_amount = sum(inv["total_amount"] for inv in invoices if inv["status"] == InvoiceStatus.PAID.value)
    pending_amount = sum(inv["total_amount"] for inv in invoices if inv["status"] == InvoiceStatus.PENDING.value)
    overdue_amount = sum(inv["total_amount"] for inv in invoices if inv["status"] == InvoiceStatus.OVERDUE.value)
    
    return {
        "total_invoices": total_invoices,
        "paid_invoices": paid_invoices,
        "pending_invoices": pending_invoices,
        "overdue_invoices": overdue_invoices,
        "total_amount": total_amount,
        "paid_amount": paid_amount,
        "pending_amount": pending_amount,
        "overdue_amount": overdue_amount,
        "period": period
    }

@router.get("/{invoice_id}", response_model=InvoiceWithItems, response_class=ORJSONResponse)
async def get_invoice(
    invoice_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """
    Retrieve a specific invoice with its items
    """
    supabase = get_supabase()
    
    # Get the invoice
    invoice_result = await run_in_threadpool(
        with_retry(lambda: supabase.table("invoices")
        .select("*")
        .eq("id", str(invoice_id))
        .eq("user_id", current_user["id"])
        .execute())
    )
    
    if not invoice_result.data or len(invoice_result.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )
    
    invoice = invoice_result.data[0]
    
    # Get the invoice items
    items_result = await run_in_threadpool(
        with_retry(lambda: supabase.table("invoice_items")
        .select("*")
        .eq("invoice_id", str(invoice_id))
        .execute())
    )
    
    items = items_result.data if items_result.data else []
    
    # Combine invoice with items
    return {
        **invoice,
        "items": items
    }

@router.post("/", response_model=InvoiceInDB, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    invoice: InvoiceCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new invoice with items
    """
    supabase = get_supabase()
    
    # Calculate total amount from items
    total_amount = sum(item.quantity * item.unit_price for item in invoice.items)
    
    # Add metadata
    metadata = {
        "created_by": current_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "user_timezone": invoice.timezone if hasattr(invoice, "timezone") else "UTC"
    }
    
    # Create invoice data
    invoice_data = {
        "user_id": current_user["id"],
        "client_id": str(invoice.client_id) if invoice.client_id else None,
        "invoice_number": invoice.invoice_number,
        "status": invoice.status.value,
        "invoice_date": invoice.invoice_date.isoformat(),
        "due_date": invoice.due_date.isoformat(),
        "total_amount": total_amount,
        "currency": invoice.currency,
        "notes": invoice.notes,
        "terms": invoice.terms,
        "metadata": orjson.dumps(metadata)
    }
    
    # Create invoice in database
    invoice_result = await run_in_threadpool(
        with_retry(lambda: supabase.table("invoices")
        .insert(invoice_data)
        .execute())
    )
    
    if not invoice_result.data or len(invoice_result.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create invoice"
        )
    
    created_invoice = invoice_result.data[0]
    
    # Create invoice items
    for item in invoice.items:
        item_data = {
            "invoice_id": created_invoice["id"],
            "description": item.description,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "amount": item.quantity * item.unit_price,
            "tax_rate": item.tax_rate
        }
        
        await run_in_threadpool(
            with_retry(lambda: supabase.table("invoice_items")
            .insert(item_data)
            .execute())
        )
    
    return created_invoice

@router.put("/{invoice_id}", response_model=InvoiceInDB)
async def update_invoice(
    invoice_id: UUID,
    invoice_update: InvoiceUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Update an existing invoice
    """
    supabase = get_supabase()
    
    # Check if invoice exists and belongs to user
    invoice_result = await run_in_threadpool(
        with_retry(lambda: supabase.table("invoices")
        .select("*")
        .eq("id", str(invoice_id))
        .eq("user_id", current_user["id"])
        .execute())
    )
    
    if not invoice_result.data or len(invoice_result.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )
    
    existing_invoice = invoice_result.data[0]
    
    # Prepare update data
    update_data = invoice_update.dict(exclude_unset=True)
    
    # Handle enum conversion
    if "status" in update_data and update_data["status"] is not None:
        update_data["status"] = update_data["status"].value
    
    # Format dates to ISO strings
    if "invoice_date" in update_data and update_data["invoice_date"] is not None:
        update_data["invoice_date"] = update_data["invoice_date"].isoformat()
    
    if "due_date" in update_data and update_data["due_date"] is not None:
        update_data["due_date"] = update_data["due_date"].isoformat()
    
    # Convert UUID to string
    if "client_id" in update_data and update_data["client_id"] is not None:
        update_data["client_id"] = str(update_data["client_id"])
    
    # Update invoice items if provided
    if "items" in update_data and update_data["items"] is not None:
        # Delete existing items
        await run_in_threadpool(
            with_retry(lambda: supabase.table("invoice_items")
            .delete()
            .eq("invoice_id", str(invoice_id))
            .execute())
        )
        
        # Calculate new total amount
        total_amount = sum(item.quantity * item.unit_price for item in update_data["items"])
        update_data["total_amount"] = total_amount
    
        # Create new items
        for item in update_data["items"]:
            item_data = {
                "invoice_id": str(invoice_id),
                "description": item.description,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "amount": item.quantity * item.unit_price,
                "tax_rate": item.tax_rate
            }
            
            await run_in_threadpool(
                with_retry(lambda: supabase.table("invoice_items")
                .insert(item_data)
                .execute())
            )
        
        # Remove items from update_data as they've been processed separately
        del update_data["items"]
    
    # If no fields to update, return existing invoice
    if not update_data:
        return existing_invoice
    
    # Update metadata
    existing_metadata = orjson.loads(existing_invoice.get("metadata", "{}"))
    existing_metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
    existing_metadata["updated_by"] = current_user["id"]
    update_data["metadata"] = orjson.dumps(existing_metadata)
    
    # Update invoice in database
    updated_result = await run_in_threadpool(
        with_retry(lambda: supabase.table("invoices")
        .update(update_data)
        .eq("id", str(invoice_id))
        .execute())
    )
    
    if not updated_result.data or len(updated_result.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update invoice"
        )
    
    return updated_result.data[0]

@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invoice(
    invoice_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete an invoice and its items
    """
    supabase = get_supabase()
    
    # Check if invoice exists and belongs to user
    invoice_result = await run_in_threadpool(
        with_retry(lambda: supabase.table("invoices")
        .select("*")
        .eq("id", str(invoice_id))
        .eq("user_id", current_user["id"])
        .execute())
    )
    
    if not invoice_result.data or len(invoice_result.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )
    
    # Delete invoice items first (foreign key constraint)
    await run_in_threadpool(
        with_retry(lambda: supabase.table("invoice_items")
        .delete()
        .eq("invoice_id", str(invoice_id))
        .execute())
    )
    
    # Delete the invoice
    await run_in_threadpool(
        with_retry(lambda: supabase.table("invoices")
        .delete()
        .eq("id", str(invoice_id))
        .execute())
    )
    
    return None

@router.post("/{invoice_id}/send", response_model=Dict[str, str])
async def send_invoice(
    invoice_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """
    Send an invoice to the client via email
    """
    supabase = get_supabase()
    
    # Check if invoice exists and belongs to user
    invoice_result = await run_in_threadpool(
        with_retry(lambda: supabase.table("invoices")
        .select("*")
        .eq("id", str(invoice_id))
        .eq("user_id", current_user["id"])
        .execute())
    )
    
    if not invoice_result.data or len(invoice_result.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )
    
    invoice = invoice_result.data[0]
    
    # Check if client_id is present
    if not invoice.get("client_id"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot send invoice without a client"
        )
    
    # Get client info
    client_result = await run_in_threadpool(
        with_retry(lambda: supabase.table("clients")
        .select("*")
        .eq("id", invoice["client_id"])
        .execute())
    )
    
    if not client_result.data or len(client_result.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    client = client_result.data[0]
    
    # In a real application, you would:
    # 1. Generate a PDF of the invoice
    # 2. Send an email to the client with the PDF attached
    # 3. Update the invoice status to "sent"
    # 4. Log the email sending in an audit trail
    
    # For this example, we'll just update the status
    await run_in_threadpool(
        with_retry(lambda: supabase.table("invoices")
        .update({"status": InvoiceStatus.SENT.value})
        .eq("id", str(invoice_id))
        .execute())
    )
    
    # Log the action
    log_data = {
        "user_id": current_user["id"],
        "action": "invoice_sent",
        "resource_id": str(invoice_id),
        "metadata": orjson.dumps({
            "client_id": client["id"],
            "client_email": client.get("email"),
            "invoice_number": invoice["invoice_number"],
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    }
    
    await run_in_threadpool(
        with_retry(lambda: supabase.table("audit_logs")
        .insert(log_data)
        .execute())
    )
    
    return {"message": f"Invoice #{invoice['invoice_number']} sent to {client.get('email')}"}

@router.post("/{invoice_id}/mark-as-paid", response_model=InvoiceInDB)
async def mark_invoice_as_paid(
    invoice_id: UUID,
    payment_details: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    """
    Mark an invoice as paid and record payment details
    """
    supabase = get_supabase()
    
    # Check if invoice exists and belongs to user
    invoice_result = await run_in_threadpool(
        with_retry(lambda: supabase.table("invoices")
        .select("*")
        .eq("id", str(invoice_id))
        .eq("user_id", current_user["id"])
        .execute())
    )
    
    if not invoice_result.data or len(invoice_result.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )
    
    invoice = invoice_result.data[0]
    
    # Update invoice status
    update_data = {
        "status": InvoiceStatus.PAID.value,
        "payment_date": datetime.now(timezone.utc).isoformat()
    }
    
    # Update metadata with payment details
    existing_metadata = orjson.loads(invoice.get("metadata", "{}"))
    existing_metadata["payment_details"] = payment_details
    existing_metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
    existing_metadata["updated_by"] = current_user["id"]
    update_data["metadata"] = orjson.dumps(existing_metadata)
    
    # Update the invoice
    updated_result = await run_in_threadpool(
        with_retry(lambda: supabase.table("invoices")
        .update(update_data)
        .eq("id", str(invoice_id))
        .execute())
    )
    
    if not updated_result.data or len(updated_result.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update invoice"
        )
    
    # Record the payment in transactions
    payment_data = {
        "user_id": current_user["id"],
        "amount": invoice["total_amount"],
        "description": f"Payment for Invoice #{invoice['invoice_number']}",
        "date": datetime.now(timezone.utc).isoformat(),
        "transaction_type": "income",
        "category": "invoice_payment",
        "metadata": orjson.dumps({
            "invoice_id": str(invoice_id),
            "payment_method": payment_details.get("payment_method", "unknown"),
            "transaction_id": payment_details.get("transaction_id")
        })
    }
    
    await run_in_threadpool(
        with_retry(lambda: supabase.table("transactions")
        .insert(payment_data)
        .execute())
    )
    
    return updated_result.data[0]

@router.get("/clients/{client_id}", response_model=List[InvoiceInDB])
async def get_client_invoices(
    client_id: UUID,
    current_user: dict = Depends(get_current_user),
    status: Optional[InvoiceStatus] = None
):
    """
    Get all invoices for a specific client
    """
    supabase = get_supabase()
    
    # Build query
    query = supabase.table("invoices").select("*").eq("user_id", current_user["id"]).eq("client_id", str(client_id))
    
    if status:
        query = query.eq("status", status.value)
    
    # Execute query
    result = await run_in_threadpool(with_retry(lambda: query.execute()))
    
    if not result.data:
        return []
    
    return result.data

@router.post("/bulk-delete", status_code=status.HTTP_204_NO_CONTENT)
async def bulk_delete_invoices(
    invoice_ids: List[UUID],
    current_user: dict = Depends(get_current_user)
):
    """
    Delete multiple invoices at once
    """
    if not invoice_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No invoice IDs provided"
        )
    
    supabase = get_supabase()
    
    # Convert UUIDs to strings
    str_invoice_ids = [str(invoice_id) for invoice_id in invoice_ids]
    
    # Check if all invoices belong to the user
    invoices_result = await run_in_threadpool(
        with_retry(lambda: supabase.table("invoices")
        .select("id")
        .eq("user_id", current_user["id"])
        .in_("id", str_invoice_ids)
        .execute())
    )
    
    if not invoices_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No matching invoices found"
        )
    
    # Get IDs of invoices that were found and belong to user
    found_ids = [invoice["id"] for invoice in invoices_result.data]
    
    # Delete invoice items first
    await run_in_threadpool(
        with_retry(lambda: supabase.table("invoice_items")
        .delete()
        .in_("invoice_id", found_ids)
        .execute())
    )
    
    # Delete invoices
    await run_in_threadpool(
        with_retry(lambda: supabase.table("invoices")
        .delete()
        .in_("id", found_ids)
        .execute())
    )
    
    return None

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