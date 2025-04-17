from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Dict, Union
from datetime import datetime, date
from uuid import UUID
from enum import Enum
import functools
from decimal import Decimal


# Cache for frequently used tax calculations
@functools.lru_cache(maxsize=100)
def calculate_tax(amount: float, rate: float, tax_included: bool = False) -> Dict[str, float]:
    """Calculate tax with caching for better performance"""
    if tax_included:
        divisor = 1 + (rate / 100)
        base_amount = amount / divisor
        tax_amount = amount - base_amount
    else:
        base_amount = amount
        tax_amount = amount * rate / 100

    total = base_amount + tax_amount

    if rate == 18.0:  # Standard GST rate
        cgst = sgst = round(tax_amount / 2, 2)
        igst = 0.0
    else:
        cgst = sgst = 0.0
        igst = tax_amount

    return {
        "original_amount": round(base_amount, 2),
        "tax_amount": round(tax_amount, 2),
        "total_amount": round(total, 2),
        "cgst": round(cgst, 2),
        "sgst": round(sgst, 2),
        "igst": round(igst, 2)
    }


class BaseTaxModel(BaseModel):
    model_config = {
        "frozen": True,
        "validate_assignment": False,
        "extra": "forbid",
        "json_encoders": {
            date: lambda d: d.isoformat(),
            datetime: lambda dt: dt.isoformat(),
            UUID: str,
            Decimal: float,
        },
    }


class TaxType(str, Enum):
    GST = "gst"
    INCOME_TAX = "income_tax"
    OTHER = "other"


class TaxPeriod(str, Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUALLY = "annually"


class TaxRate(BaseTaxModel):
    rate: float = Field(default=18.0, ge=0.0, le=100.0)
    description: str = "GST"

    @field_validator("description")
    def validate_description(cls, v):
        return v.strip() or "GST"


class GSTCalculationRequest(BaseTaxModel):
    amount: float = Field(..., gt=0.0)
    tax_included: bool = False
    tax_rate: float = Field(default=18.0, ge=0.0, le=100.0)


class GSTCalculationResponse(BaseTaxModel):
    original_amount: float
    tax_rate: float
    tax_amount: float
    total_amount: float
    tax_included: bool
    breakdown: Dict[str, float] = Field(default_factory=lambda: {"cgst": 0.0, "sgst": 0.0, "igst": 0.0})

    @classmethod
    def from_calculation(cls, request: GSTCalculationRequest) -> "GSTCalculationResponse":
        result = calculate_tax(
            request.amount,
            request.tax_rate,
            request.tax_included,
        )
        return cls(
            original_amount=result["original_amount"],
            tax_rate=request.tax_rate,
            tax_amount=result["tax_amount"],
            total_amount=result["total_amount"],
            tax_included=request.tax_included,
            breakdown={
                "cgst": result["cgst"],
                "sgst": result["sgst"],
                "igst": result["igst"]
            }
        )


class TaxFilingRequest(BaseTaxModel):
    start_date: date
    end_date: date
    tax_type: TaxType = TaxType.GST
    period: TaxPeriod = TaxPeriod.QUARTERLY

    @field_validator("end_date")
    def validate_dates(cls, v, info):
        start_date = info.data.get("start_date")
        if start_date and v < start_date:
            raise ValueError("End date must be after start date")
        return v


class TaxFilingSummary(BaseTaxModel):
    period_start: date
    period_end: date
    tax_type: TaxType
    total_sales: float = Field(default=0.0, ge=0.0)
    total_tax_collected: float = Field(default=0.0, ge=0.0)
    total_tax_paid: float = Field(default=0.0, ge=0.0)
    net_tax_liability: float = Field(default=0.0)
    transaction_count: int = Field(default=0, ge=0)
    status: str = "draft"

    @model_validator(mode="after")
    def calculate_liability(cls, values):
        if values.net_tax_liability == 0:
            values.net_tax_liability = round(
                values.total_tax_collected - values.total_tax_paid, 2
            )
        return values


class TaxTransactionDetail(BaseTaxModel):
    transaction_id: UUID
    date: datetime
    description: str
    amount: float
    tax_amount: float
    transaction_type: str
    category: Optional[str] = None


class TaxFilingResponse(BaseTaxModel):
    summary: TaxFilingSummary
    transactions: List[TaxTransactionDetail] = []


class TaxSubmissionRequest(BaseTaxModel):
    filing_id: Optional[UUID] = None
    period_start: date
    period_end: date
    tax_type: TaxType
    total_tax_liability: float
    payment_reference: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("total_tax_liability")
    def validate_liability(cls, v):
        if v < 0:
            raise ValueError("Tax liability cannot be negative")
        return v


class TaxSubmissionResponse(BaseTaxModel):
    id: UUID
    submission_date: datetime
    period_start: date
    period_end: date
    tax_type: TaxType
    total_tax_liability: float
    payment_reference: Optional[str] = None
    confirmation_number: Optional[str] = None
    status: str


class TaxReportRequest(BaseTaxModel):
    year: int = Field(..., ge=2000, le=2100)
    tax_type: Optional[TaxType] = None


class TaxReportSummary(BaseTaxModel):
    id: UUID
    period_start: date
    period_end: date
    tax_type: TaxType
    total_tax_liability: float
    submission_date: Optional[datetime] = None
    status: str


class TaxReportResponse(BaseTaxModel):
    year: int
    total_tax_paid: float = Field(default=0.0)
    filings: List[TaxReportSummary] = []

    @model_validator(mode="after")
    def calculate_totals(cls, values):
        if values.total_tax_paid == 0 and values.filings:
            values.total_tax_paid = sum(
                f.total_tax_liability for f in values.filings
                if f.status in ("submitted", "accepted")
            )
        return values
