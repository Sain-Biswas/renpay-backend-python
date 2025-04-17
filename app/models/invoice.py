from pydantic import BaseModel, Field, model_validator
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from uuid import UUID
from enum import Enum
import functools
from decimal import Decimal

# Define enums for better performance
class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    PAID = "paid"
    CANCELLED = "cancelled"
    OVERDUE = "overdue"
    PARTIALLY_PAID = "partially_paid"

class InvoiceTemplate(str, Enum):
    DEFAULT = "default"
    PROFESSIONAL = "professional"
    SIMPLE = "simple"
    DETAILED = "detailed"

# Shared configuration for performance
class FastBaseModel(BaseModel):
    class Config:
        frozen = True
        validate_assignment = False
        use_enum_values = True
        extra = 'forbid'
        json_encoders = {
            datetime: lambda dt: dt.isoformat(),
            UUID: str,
            Decimal: float
        }

@functools.lru_cache(maxsize=1024)
def calculate_amount(quantity: float, unit_price: float) -> float:
    return round(quantity * unit_price, 2)

class InvoiceItem(FastBaseModel):
    description: str
    quantity: float = Field(default=1.0, ge=0.01)
    unit_price: float = Field(ge=0)
    amount: Optional[float] = None
    tax_included: bool = True
    item_name: Optional[str] = None

    @model_validator(mode="after")
    def calculate_values(cls, model: 'InvoiceItem') -> 'InvoiceItem':
        update_data = {}
        if model.amount is None and model.quantity and model.unit_price:
            update_data['amount'] = calculate_amount(model.quantity, model.unit_price)
        if not model.item_name and model.description:
            update_data['item_name'] = model.description.split('\n')[0][:50]
        return model.model_copy(update=update_data) if update_data else model

class InvoiceItemCreate(InvoiceItem):
    discount_amount: float = Field(default=0.0, ge=0.0)
    tax_rate: float = Field(default=18.0, ge=0.0)
    tax_amount: Optional[float] = None
    unit: str = "item"

    @model_validator(mode="after")
    def calculate_tax(cls, model: 'InvoiceItemCreate') -> 'InvoiceItemCreate':
        if model.tax_amount is None and model.amount is not None:
            if model.tax_included:
                divisor = 1 + (model.tax_rate / 100)
                pre_tax = model.amount / divisor
                tax_amt = round(model.amount - pre_tax, 2)
            else:
                tax_amt = round(model.amount * model.tax_rate / 100, 2)
            return model.model_copy(update={"tax_amount": tax_amt})
        return model

class InvoiceItemUpdate(FastBaseModel):
    description: Optional[str] = None
    quantity: Optional[float] = Field(None, ge=0.01)
    unit_price: Optional[float] = Field(None, ge=0)
    amount: Optional[float] = None
    tax_included: Optional[bool] = None
    item_name: Optional[str] = None
    discount_amount: Optional[float] = Field(None, ge=0.0)
    unit: Optional[str] = None

class InvoiceItemInDB(InvoiceItem):
    id: UUID
    invoice_id: UUID
    tax_rate: float = 18.0
    tax_amount: float = 0.0
    discount_amount: float = 0.0
    created_at: datetime
    updated_at: datetime

    class Config(FastBaseModel.Config):
        from_attributes = True

class Invoice(FastBaseModel):
    invoice_number: str
    customer_name: str
    customer_email: Optional[str] = None
    customer_address: Optional[str] = None
    issue_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    due_date: Optional[datetime] = None
    subtotal: float
    tax_rate: float = Field(default=18.0)
    tax_amount: float
    total_amount: float
    status: InvoiceStatus = Field(default=InvoiceStatus.DRAFT)
    notes: Optional[str] = None
    template: InvoiceTemplate = Field(default=InvoiceTemplate.DEFAULT)
    items: List[InvoiceItem] = []
    user_id: Optional[UUID] = None

    @model_validator(mode="before")
    def set_default_values(cls, values):
        if 'due_date' not in values or values['due_date'] is None:
            issue_date = values.get('issue_date', datetime.now(timezone.utc))
            values['due_date'] = issue_date + timedelta(days=30)

        subtotal = values.get('subtotal')
        if subtotal is not None:
            if 'tax_amount' not in values or values['tax_amount'] is None:
                tax_rate = values.get('tax_rate', 18.0)
                values['tax_amount'] = round(subtotal * tax_rate / 100, 2)
            if 'total_amount' not in values or values['total_amount'] is None:
                tax_amount = values.get('tax_amount', 0.0)
                values['total_amount'] = round(subtotal + tax_amount, 2)
        return values

class InvoiceCreate(FastBaseModel):
    invoice_number: Optional[str] = None
    customer_name: str
    customer_email: Optional[str] = None
    customer_address: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_tax_id: Optional[str] = None
    issue_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    tax_rate: float = 18.0
    status: InvoiceStatus = InvoiceStatus.DRAFT
    notes: Optional[str] = None
    template: InvoiceTemplate = InvoiceTemplate.DEFAULT
    currency: str = "INR"
    items: List[InvoiceItemCreate] = []

    @model_validator(mode="after")
    def validate_invoice(cls, model: 'InvoiceCreate') -> 'InvoiceCreate':
        if not model.items:
            raise ValueError("Invoice must have at least one item")

        update_data = {}
        if not model.issue_date:
            update_data['issue_date'] = datetime.now(timezone.utc)

        if not model.due_date:
            update_data['due_date'] = (update_data.get('issue_date') or model.issue_date) + timedelta(days=30)

        return model.model_copy(update=update_data) if update_data else model

class InvoiceUpdate(FastBaseModel):
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    customer_address: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_tax_id: Optional[str] = None
    issue_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    tax_rate: Optional[float] = None
    status: Optional[InvoiceStatus] = None
    notes: Optional[str] = None
    template: Optional[InvoiceTemplate] = None
    currency: Optional[str] = None
    discount_amount: Optional[float] = None
    payment_date: Optional[datetime] = None
    payment_reference: Optional[str] = None
    payment_method: Optional[str] = None

class InvoiceInDB(Invoice):
    id: UUID
    customer_phone: Optional[str] = None
    customer_tax_id: Optional[str] = None
    payment_date: Optional[datetime] = None
    payment_reference: Optional[str] = None
    payment_method: Optional[str] = None
    amount_paid: float = 0.0
    balance_due: float
    currency: str = "INR"
    created_at: datetime
    updated_at: datetime

    class Config(FastBaseModel.Config):
        from_attributes = True

class InvoiceSummary(BaseModel):
    total_invoices: int
    total_amount: float
    total_tax: float
    total_paid: float
    total_outstanding: float


class InvoiceWithItems(Invoice):
    items: List[InvoiceItemInDB]  # Assuming InvoiceItemInDB is the model for invoice items

