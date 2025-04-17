from pydantic import BaseModel, Field, validator, model_validator, ConfigDict
from typing import Optional, List, Union, Literal, Dict, Any, ClassVar
from datetime import datetime, timezone, date
from uuid import UUID, uuid4
from decimal import Decimal
import functools
from enum import Enum

# ---------------------------------------------
# Enum
# ---------------------------------------------
class TransactionType(str, Enum):
    """Transaction types with efficient string representation"""
    SALE = "sale"
    EXPENSE = "expense"
    TRANSFER = "transfer"
    OTHER = "other"

# ---------------------------------------------
# Optimized Base Model
# ---------------------------------------------
class OptimizedBaseModel(BaseModel):
    """Base model with optimization settings."""
    model_config = ConfigDict(
        validate_assignment=True,
        populate_by_name=True,
        from_attributes=True,
        validate_default=True,
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={"example": {}}
    )

# ---------------------------------------------
# Base Transaction
# ---------------------------------------------
class TransactionBase(OptimizedBaseModel):
    amount: Decimal = Field(..., gt=0, description="Transaction amount (must be positive)")
    description: str = Field(..., min_length=1, max_length=500, description="Transaction description")
    transaction_type: TransactionType = Field(..., description="Type of transaction (SALE, EXPENSE, TRANSFER, or OTHER)")

    @validator('amount')
    def quantize_amount(cls, v):
        return Decimal(str(v)).quantize(Decimal('0.01'))

    @validator('description')
    def strip_description(cls, v):
        return v.strip()

# ---------------------------------------------
# Create Schema
# ---------------------------------------------
class TransactionCreate(TransactionBase):
    id: UUID = Field(default_factory=uuid4)
    date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    from_account_id: UUID
    to_account_id: Optional[UUID] = None
    category_id: Optional[UUID] = None
    payment_method: Optional[str] = None
    reference_number: Optional[str] = None
    notes: Optional[str] = None
    is_reconciled: bool = False
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode='after')
    def validate_accounts(self):
        if self.transaction_type == TransactionType.TRANSFER:
            if not self.to_account_id:
                raise ValueError("to_account_id is required for TRANSFER transactions")
            if self.from_account_id == self.to_account_id:
                raise ValueError("from_account_id and to_account_id cannot be the same for TRANSFER transactions")
        else:
            self.to_account_id = None
        return self

# ---------------------------------------------
# Update Schema
# ---------------------------------------------
class TransactionUpdate(OptimizedBaseModel):
    amount: Optional[Decimal] = Field(None, gt=0)
    description: Optional[str] = Field(None, min_length=1, max_length=500)
    date: Optional[datetime] = None
    transaction_type: Optional[TransactionType] = None
    from_account_id: Optional[UUID] = None
    to_account_id: Optional[UUID] = None
    category_id: Optional[UUID] = None
    payment_method: Optional[str] = None
    reference_number: Optional[str] = None
    notes: Optional[str] = None
    is_reconciled: Optional[bool] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None

    @validator('amount')
    def quantize_amount(cls, v):
        return Decimal(str(v)).quantize(Decimal('0.01')) if v is not None else v

    @validator('description')
    def strip_description(cls, v):
        return v.strip() if v is not None else v

    @model_validator(mode='after')
    def check_at_least_one_field(self):
        if not self.model_dump(exclude_unset=True):
            raise ValueError("At least one field must be updated")
        return self

    @model_validator(mode='after')
    def validate_transaction_type_and_accounts(self):
        if self.transaction_type == TransactionType.TRANSFER:
            if self.to_account_id is None and 'to_account_id' in self.__fields_set__:
                raise ValueError("to_account_id cannot be None for TRANSFER transactions")
            if self.from_account_id and self.to_account_id and self.from_account_id == self.to_account_id:
                raise ValueError("from_account_id and to_account_id cannot be the same for TRANSFER transactions")
        elif self.to_account_id:
            self.to_account_id = None
        return self

# ---------------------------------------------
# Full Transaction Schema
# ---------------------------------------------
class Transaction(TransactionBase):
    id: UUID
    date: datetime
    from_account_id: UUID
    to_account_id: Optional[UUID] = None
    category_id: Optional[UUID] = None
    payment_method: Optional[str] = None
    reference_number: Optional[str] = None
    notes: Optional[str] = None
    is_reconciled: bool = False
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    user_id: UUID
    related_invoice_id: Optional[UUID] = None
    related_tax_filing_id: Optional[UUID] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    _cached_properties: ClassVar[List[str]] = ["formatted_amount"]

    @functools.lru_cache(maxsize=128)
    def get_formatted_amount(self, currency_symbol="₹"):
        return f"{currency_symbol} {self.amount:,.2f}"

# ---------------------------------------------
# Transaction DB Schema
# ---------------------------------------------
class TransactionInDB(Transaction):
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")

# ---------------------------------------------
# Filtering Schema
# ---------------------------------------------
class TransactionFilter(OptimizedBaseModel):
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None
    transaction_type: Optional[TransactionType] = None
    account_id: Optional[UUID] = None
    category_id: Optional[UUID] = None
    payment_method: Optional[str] = None
    is_reconciled: Optional[bool] = None
    reference_number: Optional[str] = None
    tags: Optional[List[str]] = None
    user_id: Optional[UUID] = None

    @validator('min_amount', 'max_amount')
    def quantize_amount(cls, v):
        return Decimal(str(v)).quantize(Decimal('0.01')) if v is not None else v

    @model_validator(mode='after')
    def validate_date_range(self):
        if self.from_date and self.to_date and self.from_date > self.to_date:
            raise ValueError("from_date must be before to_date")
        return self

# ---------------------------------------------
# Summary Schema
# ---------------------------------------------
class TransactionSummary(OptimizedBaseModel):
    total_income: float
    total_expense: float
    net_amount: float
    count: int
    categories: Dict[str, Dict[str, float]]
    period: Literal["day", "week", "month", "year", "all_time"]
    start_date: date
    end_date: date

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_income": 5000.0,
                "total_expense": 2500.0,
                "net_amount": 2500.0,
                "count": 15,
                "categories": {
                    "income": {
                        "Salary": 4500.0,
                        "Investments": 500.0
                    },
                    "expense": {
                        "Food": 800.0,
                        "Rent": 1200.0,
                        "Utilities": 500.0
                    }
                },
                "period": "month",
                "start_date": "2023-05-01",
                "end_date": "2023-05-31"
            }
        }
    )
