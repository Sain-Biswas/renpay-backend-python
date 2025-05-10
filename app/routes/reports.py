from fastapi import APIRouter, Depends
from app.models.sales_report import SalesReport
from app.services.supabase_client import get_supabase
from supabase import Client

router = APIRouter()

@router.get("/api/report/sales")
def get_sales_report(user_id: str, start_date: str, end_date: str, supabase: Client = Depends(get_supabase)):
    sales_report = SalesReport(supabase)
    return sales_report.get_sales_report(user_id, start_date, end_date)