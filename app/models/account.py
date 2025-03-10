from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID

class Account(BaseModel):
    name: str
    balance: float = Field(default=0.0)
    user_id: Optional[UUID] = None

class AccountCreate(Account):
    pass

class AccountUpdate(BaseModel):
    name: Optional[str] = None
    balance: Optional[float] = None

class AccountInDB(Account):
    id: UUID
    created_at: datetime
    updated_at: datetime 