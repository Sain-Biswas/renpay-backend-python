from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import datetime, timedelta
from uuid import UUID
from enum import Enum

class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    PAID = "paid"
    CANCELLED = "cancelled"
    OVERDUE = "overdue"

class InvoiceTemplate(str, Enum):
    DEFAULT = "default"
    PROFESSIONAL = "professional"
    SIMPLE = "simple"
    DETAILED = "detailed"

class InvoiceItem(BaseModel):
    description: str
    quantity: float = Field(default=1.0, ge=0.01)
    unit_price: float = Field(ge=0)
    amount: Optional[float] = None
    tax_included: bool = True
    
    @validator('amount', pre=True, always=True)
    def calculate_amount(cls, v, values):
        if v is not None:
            return v
        if 'quantity' in values and 'unit_price' in values:
            return round(values['quantity'] * values['unit_price'], 2)
        return None

class InvoiceItemCreate(InvoiceItem):
    pass

class InvoiceItemUpdate(BaseModel):
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None
    tax_included: Optional[bool] = None

class InvoiceItemInDB(InvoiceItem):
    id: UUID
    invoice_id: UUID
    created_at: datetime
    updated_at: datetime

class Invoice(BaseModel):
    invoice_number: str
    customer_name: str
    customer_email: Optional[str] = None
    customer_address: Optional[str] = None
    issue_date: datetime = Field(default_factory=datetime.now)
    due_date: Optional[datetime] = None
    subtotal: float
    tax_rate: float = Field(default=18.0)  # Default GST rate
    tax_amount: float
    total_amount: float
    status: InvoiceStatus = Field(default=InvoiceStatus.DRAFT)
    notes: Optional[str] = None
    template: InvoiceTemplate = Field(default=InvoiceTemplate.DEFAULT)
    items: List[InvoiceItem] = []
    user_id: Optional[UUID] = None
    
    @validator('due_date', pre=True, always=True)
    def set_due_date(cls, v, values):
        if v is not None:
            return v
        if 'issue_date' in values:
            # Default due date is 30 days after issue date
            return values['issue_date'] + timedelta(days=30)
        return datetime.now() + timedelta(days=30)
    
    @validator('tax_amount', pre=True, always=True)
    def calculate_tax_amount(cls, v, values):
        if v is not None:
            return v
        if 'subtotal' in values and 'tax_rate' in values:
            return round(values['subtotal'] * values['tax_rate'] / 100, 2)
        return 0
    
    @validator('total_amount', pre=True, always=True)
    def calculate_total_amount(cls, v, values):
        if v is not None:
            return v
        if 'subtotal' in values and 'tax_amount' in values:
            return round(values['subtotal'] + values['tax_amount'], 2)
        return 0

class InvoiceCreate(BaseModel):
    invoice_number: Optional[str] = None  # Can be auto-generated
    customer_name: str
    customer_email: Optional[str] = None
    customer_address: Optional[str] = None
    issue_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    tax_rate: float = 18.0  # Default GST rate
    status: InvoiceStatus = InvoiceStatus.DRAFT
    notes: Optional[str] = None
    template: InvoiceTemplate = InvoiceTemplate.DEFAULT
    items: List[InvoiceItemCreate] = []

class InvoiceUpdate(BaseModel):
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    customer_address: Optional[str] = None
    issue_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    tax_rate: Optional[float] = None
    status: Optional[InvoiceStatus] = None
    notes: Optional[str] = None
    template: Optional[InvoiceTemplate] = None

class InvoiceInDB(Invoice):
    id: UUID
    created_at: datetime
    updated_at: datetime 