from supabase import Client
from pydantic import BaseModel, Field, validator, root_validator, model_validator
from typing import Optional, List, Dict, Any
from datetime import datetime, date, timezone, timedelta
from uuid import UUID, uuid4
from decimal import Decimal
import functools
import enum

from app.models.account import OptimizedBaseModel

class ReportType(str, enum.Enum):
    """Type of sales report"""
    DAILY = "daily"
    WEEKLY = "weekly" 
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    CUSTOM = "custom"

class SalesReportBase(OptimizedBaseModel):
    """Base model for sales report with optimized performance"""
    report_type: ReportType = Field(default=ReportType.MONTHLY, description="Type of report")
    start_date: date = Field(..., description="Start date for the report period")
    end_date: date = Field(..., description="End date for the report period")
    
    @validator('end_date')
    def validate_end_date(cls, v, values):
        """Validate that end date is after start date"""
        if 'start_date' in values and v < values['start_date']:
            raise ValueError("End date must be after start date")
        return v
    
    @model_validator(mode='after')
    def validate_report_period(self):
        """Validate that report period matches report type"""
        values = self.model_dump()
        report_type = values.get('report_type')
        start_date = values.get('start_date')
        end_date = values.get('end_date')
        
        if not all([report_type, start_date, end_date]):
            # Skip validation if we don't have all values
            return self
            
        # Calculate period duration in days
        duration = (end_date - start_date).days + 1
        
        # Check that duration matches report type
        if report_type == ReportType.DAILY and duration != 1:
            raise ValueError("Daily reports must cover exactly one day")
        elif report_type == ReportType.WEEKLY and (duration < 1 or duration > 7):
            raise ValueError("Weekly reports must cover 1-7 days")
        elif report_type == ReportType.MONTHLY and (duration < 28 or duration > 31):
            raise ValueError("Monthly reports must cover 28-31 days")
        elif report_type == ReportType.QUARTERLY and (duration < 89 or duration > 92):
            raise ValueError("Quarterly reports must cover approximately 90 days")
        elif report_type == ReportType.YEARLY and (duration < 365 or duration > 366):
            raise ValueError("Annual reports must cover 365-366 days")
        
        return self

class SalesReportCreate(SalesReportBase):
    """Schema for creating a sales report"""
    user_id: UUID = Field(..., description="User ID the report belongs to")
    report_date: date = Field(default_factory=date.today, description="Date when report is generated")
    total_sales: Decimal = Field(default=Decimal("0.00"), ge=0, description="Total sales amount")
    total_tax: Decimal = Field(default=Decimal("0.00"), ge=0, description="Total tax amount")
    total_invoices: int = Field(default=0, ge=0, description="Total number of invoices")
    total_paid: Decimal = Field(default=Decimal("0.00"), ge=0, description="Total amount paid")
    total_outstanding: Decimal = Field(default=Decimal("0.00"), ge=0, description="Total outstanding amount")
    top_customers: Dict[str, Any] = Field(default_factory=dict, description="Top customers data")
    top_products: Dict[str, Any] = Field(default_factory=dict, description="Top products data")
    sales_by_category: Dict[str, Any] = Field(default_factory=dict, description="Sales by category data")
    report_data: Dict[str, Any] = Field(default_factory=dict, description="Additional report data")
    is_auto_generated: bool = Field(default=False, description="Whether report was auto-generated")
    
    @validator('top_customers', 'top_products', 'sales_by_category', 'report_data')
    def validate_report_data(cls, v):
        """Ensure report data is not null"""
        return v or {}

class SalesReportFilter(OptimizedBaseModel):
    """Schema for filtering sales reports"""
    report_type: Optional[ReportType] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_auto_generated: Optional[bool] = None
    
    @model_validator(mode='after')
    def validate_date_range(self):
        """Validate date range if both dates are provided"""
        values = self.model_dump()
        start_date = values.get('start_date')
        end_date = values.get('end_date')
        
        if start_date and end_date and end_date < start_date:
            raise ValueError("End date must be after start date")
            
        return self

class SalesReportModel(OptimizedBaseModel):
    """Schema for returning sales report data with all fields"""
    id: UUID
    user_id: UUID
    report_type: ReportType
    start_date: date
    end_date: date
    report_date: date
    total_sales: Decimal
    total_tax: Decimal
    total_invoices: int
    total_paid: Decimal
    total_outstanding: Decimal
    top_customers: Dict[str, Any] = Field(default_factory=dict)
    top_products: Dict[str, Any] = Field(default_factory=dict)
    sales_by_category: Dict[str, Any] = Field(default_factory=dict)
    report_data: Dict[str, Any] = Field(default_factory=dict)
    is_auto_generated: bool
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    @property
    def duration_days(self) -> int:
        """Calculate the report duration in days"""
        return (self.end_date - self.start_date).days + 1
    
    @property
    def average_daily_sales(self) -> Decimal:
        """Calculate average daily sales"""
        days = self.duration_days
        if days <= 0:
            return Decimal("0.00")
        return (self.total_sales / Decimal(days)).quantize(Decimal("0.01"))
    
    @property
    def payment_rate(self) -> Decimal:
        """Calculate payment rate (paid/total)"""
        if self.total_sales == 0:
            return Decimal("0.00")
        return (self.total_paid / self.total_sales * 100).quantize(Decimal("0.01"))
    
    model_config = {
        "from_attributes": True
    }

# Service class for database operations
class SalesReportService:
    """Service class to handle sales report database operations"""
    def __init__(self, supabase: Client):
        self.supabase = supabase

    def get_sales_report(self, user_id: str, start_date: str, end_date: str):
        """Get sales reports within a date range"""
        return self.supabase.table('sales_reports').select('*')\
            .eq('user_id', user_id)\
            .gte('report_date', start_date)\
            .lte('report_date', end_date)\
            .execute()
    
    def get_report_by_id(self, report_id: UUID):
        """Get a specific sales report by ID"""
        return self.supabase.table('sales_reports').select('*')\
            .eq('id', str(report_id))\
            .execute()\
            .data[0] if self.supabase.table('sales_reports').select('*')\
            .eq('id', str(report_id))\
            .execute().data else None
            
    def create_report(self, report_data: SalesReportCreate):
        """Create a new sales report"""
        return self.supabase.table('sales_reports')\
            .insert(report_data.dict())\
            .execute()