from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, date
from uuid import UUID
from enum import Enum

class TaxType(str, Enum):
    GST = "gst"
    INCOME_TAX = "income_tax"
    OTHER = "other"

class TaxRate(BaseModel):
    rate: float = Field(default=18.0)  # Default GST rate in India
    description: str = "GST"

class GSTCalculationRequest(BaseModel):
    amount: float
    tax_included: bool = False
    tax_rate: float = 18.0  # Default GST rate

class GSTCalculationResponse(BaseModel):
    original_amount: float
    tax_rate: float
    tax_amount: float
    total_amount: float
    tax_included: bool
    breakdown: Dict[str, float] = Field(
        default_factory=lambda: {"cgst": 0.0, "sgst": 0.0, "igst": 0.0}
    )

class TaxPeriod(str, Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUALLY = "annually"

class TaxFilingRequest(BaseModel):
    start_date: date
    end_date: date
    tax_type: TaxType = TaxType.GST
    period: TaxPeriod = TaxPeriod.QUARTERLY

class TaxFilingSummary(BaseModel):
    period_start: date
    period_end: date
    tax_type: TaxType
    total_sales: float
    total_tax_collected: float
    total_tax_paid: float
    net_tax_liability: float
    transaction_count: int
    status: str = "draft"

class TaxTransactionDetail(BaseModel):
    transaction_id: UUID
    date: datetime
    description: str
    amount: float
    tax_amount: float
    transaction_type: str
    category: Optional[str] = None

class TaxFilingResponse(BaseModel):
    summary: TaxFilingSummary
    transactions: List[TaxTransactionDetail] = []
    
class TaxSubmissionRequest(BaseModel):
    filing_id: Optional[UUID] = None
    period_start: date
    period_end: date
    tax_type: TaxType
    total_tax_liability: float
    payment_reference: Optional[str] = None
    notes: Optional[str] = None
    
class TaxSubmissionResponse(BaseModel):
    id: UUID
    submission_date: datetime
    period_start: date
    period_end: date
    tax_type: TaxType
    total_tax_liability: float
    payment_reference: Optional[str] = None
    confirmation_number: Optional[str] = None
    status: str
    
class TaxReportRequest(BaseModel):
    year: int
    tax_type: Optional[TaxType] = None
    
class TaxReportSummary(BaseModel):
    id: UUID
    period_start: date
    period_end: date
    tax_type: TaxType
    total_tax_liability: float
    submission_date: Optional[datetime] = None
    status: str
    
class TaxReportResponse(BaseModel):
    year: int
    total_tax_paid: float
    filings: List[TaxReportSummary] = [] 