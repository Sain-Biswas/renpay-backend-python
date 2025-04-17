from fastapi import APIRouter, Depends, Query, HTTPException, status
from typing import Optional, List, Dict, Any
from datetime import date, datetime, timezone
from uuid import UUID

from app.models.sales_report import SalesReportCreate, SalesReportModel, SalesReportFilter, ReportType
from app.services.supabase_client import get_supabase, run_in_threadpool, with_retry
from app.dependencies import get_current_user

router = APIRouter()

@router.get("/sales", response_model=List[SalesReportModel])
async def get_sales_reports(
    start_date: Optional[date] = Query(None, description="Start date for filtering reports"),
    end_date: Optional[date] = Query(None, description="End date for filtering reports"),
    report_type: Optional[ReportType] = Query(None, description="Type of report to filter by"),
    is_auto_generated: Optional[bool] = Query(None, description="Filter by auto-generated status"),
    current_user: dict = Depends(get_current_user)
):
    """Get sales reports with optional filters"""
    supabase = get_supabase()
    
    # Build query
    query = supabase.table("sales_reports").select("*").eq("user_id", str(current_user["id"]))
    
    # Apply filters
    if start_date:
        query = query.gte("start_date", start_date.isoformat())
    if end_date:
        query = query.lte("end_date", end_date.isoformat())
    if report_type:
        query = query.eq("report_type", report_type.value)
    if is_auto_generated is not None:
        query = query.eq("is_auto_generated", is_auto_generated)
    
    # Sort by date and execute
    query = query.order("report_date", desc=True)
    
    result = await run_in_threadpool(lambda: query.execute())
    
    return result.data if result.data else []

@router.get("/sales/{report_id}", response_model=Dict[str, Any])
async def get_sales_report(
    report_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Get a specific sales report by ID"""
    supabase = get_supabase()
    
    result = await run_in_threadpool(
        lambda: supabase.table("sales_reports")
            .select("*")
            .eq("id", str(report_id))
            .eq("user_id", str(current_user["id"]))
            .execute()
    )
    
    if not result.data or len(result.data) == 0:
        raise HTTPException(status_code=404, detail="Sales report not found")
    
    return result.data[0]

@router.post("/sales", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def create_sales_report(
    report: SalesReportCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a new sales report"""
    supabase = get_supabase()
    
    # Prepare report data
    report_data = {
        k: (v.value if isinstance(v, ReportType) else
            str(v) if isinstance(v, UUID) else v)
        for k, v in report.dict().items()
    }
    
    # Set user_id
    report_data["user_id"] = str(current_user["id"])
    
    # Add timestamps
    now = datetime.now(timezone.utc).isoformat()
    report_data["created_at"] = now
    
    result = await run_in_threadpool(
        lambda: supabase.table("sales_reports").insert(report_data).execute()
    )
    
    if not result.data or len(result.data) == 0:
        raise HTTPException(status_code=400, detail="Failed to create sales report")
    
    return result.data[0]

@router.get("/summary", response_model=Dict[str, Any])
async def get_sales_summary(
    period: str = Query("month", description="Summary period: 'day', 'week', 'month', 'quarter', 'year'"),
    current_user: dict = Depends(get_current_user)
):
    """Get a summary of sales for the current period"""
    supabase = get_supabase()
    
    # Get current date
    today = datetime.now(timezone.utc).date()
    
    # Calculate date range based on period
    if period == "day":
        start_date = today
        end_date = today
    elif period == "week":
        start_date = today - date.resolution * today.weekday()  # Start of week
        end_date = today
    elif period == "month":
        start_date = date(today.year, today.month, 1)  # Start of month
        end_date = today
    elif period == "quarter":
        quarter_start_month = ((today.month - 1) // 3) * 3 + 1
        start_date = date(today.year, quarter_start_month, 1)
        end_date = today
    elif period == "year":
        start_date = date(today.year, 1, 1)  # Start of year
        end_date = today
    else:
        start_date = date(today.year, today.month, 1)  # Default to month
        end_date = today
    
    # Get total sales for the period
    sales_query = await run_in_threadpool(
        lambda: supabase.table("transactions")
            .select("amount")
            .eq("user_id", str(current_user["id"]))
            .eq("transaction_type", "sale")
            .gte("date", start_date.isoformat())
            .lte("date", end_date.isoformat())
            .execute()
    )
    
    # Get total expenses for the period
    expenses_query = await run_in_threadpool(
        lambda: supabase.table("transactions")
            .select("amount")
            .eq("user_id", str(current_user["id"]))
            .eq("transaction_type", "expense")
            .gte("date", start_date.isoformat())
            .lte("date", end_date.isoformat())
            .execute()
    )
    
    # Get invoice count for the period
    invoices_query = await run_in_threadpool(
        lambda: supabase.table("invoices")
            .select("id", count="exact")
            .eq("user_id", str(current_user["id"]))
            .gte("issue_date", start_date.isoformat())
            .lte("issue_date", end_date.isoformat())
            .execute()
    )
    
    # Calculate totals
    total_sales = sum(transaction["amount"] for transaction in sales_query.data) if sales_query.data else 0.0
    total_expenses = sum(transaction["amount"] for transaction in expenses_query.data) if expenses_query.data else 0.0
    total_invoices = invoices_query.count if invoices_query.count is not None else 0
    net_profit = total_sales - total_expenses
    
    return {
        "period": period,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "total_sales": float(total_sales),
        "total_expenses": float(total_expenses),
        "net_profit": float(net_profit),
        "profit_margin": float(net_profit / total_sales * 100) if total_sales > 0 else 0.0,
        "total_invoices": total_invoices
    }

@router.delete("/sales/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sales_report(
    report_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Delete a sales report"""
    supabase = get_supabase()
    
    # Check if report exists and belongs to user
    existing = await run_in_threadpool(
        lambda: supabase.table("sales_reports")
            .select("id")
            .eq("id", str(report_id))
            .eq("user_id", str(current_user["id"]))
            .execute()
    )
    
    if not existing.data or len(existing.data) == 0:
        raise HTTPException(status_code=404, detail="Sales report not found")
    
    # Delete the report
    await run_in_threadpool(
        lambda: supabase.table("sales_reports")
            .delete()
            .eq("id", str(report_id))
            .execute()
    )
    
    return None