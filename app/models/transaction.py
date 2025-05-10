from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID
from enum import Enum

class TransactionType(str, Enum):
    SALE = "sale"
    EXPENSE = "expense"
    TRANSFER = "transfer"
    OTHER = "other"

class Transaction(BaseModel):
    amount: float
    description: str
    transaction_type: TransactionType
    category: Optional[str] = None
    date: datetime = Field(default_factory=datetime.now)
    user_id: Optional[UUID] = None
    account_id: Optional[UUID] = None
    
class TransactionCreate(Transaction):
    pass

class TransactionUpdate(BaseModel):
    amount: Optional[float] = None
    description: Optional[str] = None
    transaction_type: Optional[TransactionType] = None
    category: Optional[str] = None
    date: Optional[datetime] = None
    account_id: Optional[UUID] = None

class TransactionInDB(Transaction):
    id: UUID
    created_at: datetime
    updated_at: datetime 