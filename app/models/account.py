from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID, uuid4

class AccountBase(BaseModel):
    """Base model for an account."""
    name: str
    balance: float = Field(default=0.0)

class AccountCreate(AccountBase):
    """Schema for creating an account."""
    id: UUID = Field(default_factory=uuid4)  # Generates a unique ID
    user_id: UUID  # Required: Every account must be linked to a user

class AccountUpdate(BaseModel):
    """Schema for updating an account."""
    name: Optional[str] = None
    balance: Optional[float] = None

class Account(AccountBase):
    """Schema for returning account data."""
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True  # Allows compatibility with ORM models
