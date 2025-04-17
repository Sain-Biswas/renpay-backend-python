from pydantic import BaseModel, Field, validator, root_validator, model_validator, ConfigDict
from typing import Optional, List, Dict, Any, Union, ClassVar
from datetime import datetime, timezone
from uuid import UUID, uuid4
from decimal import Decimal
import functools

class OptimizedBaseModel(BaseModel):
    """Base model with optimized settings for better performance"""
    
    model_config = ConfigDict(
        validate_assignment=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        from_attributes=True,
        json_encoders={
            datetime: lambda dt: dt.isoformat(),
            UUID: lambda id: str(id),
            Decimal: lambda d: float(d)
        }
    )

class AccountBase(OptimizedBaseModel):
    """Base model for account with common fields and validation"""
    name: str = Field(..., min_length=1, max_length=100, description="Account name")
    description: Optional[str] = Field(None, max_length=500, description="Account description")
    currency: str = Field("USD", min_length=3, max_length=3, description="ISO currency code")
    is_active: bool = Field(True, description="Whether the account is active")
    
    @validator('name')
    def validate_name(cls, v):
        """Validate and normalize account name"""
        if not v or not v.strip():
            raise ValueError("Account name cannot be empty")
        return v.strip()
    
    @validator('currency')
    def validate_currency(cls, v):
        """Validate currency code format"""
        if not v:
            return "USD"  # Default to USD
        
        v = v.upper()
        # This is a simplified validator. In production, you would check against a list of valid ISO codes
        if len(v) != 3 or not v.isalpha():
            raise ValueError("Currency must be a valid 3-letter ISO code")
        return v

class AccountCreate(AccountBase):
    """Schema for creating a new account with enhanced validation"""
    id: UUID = Field(default_factory=uuid4, description="Unique identifier for the account")
    account_type: str = Field(..., description="Type of account (checking, savings, credit, etc.)")
    balance: Decimal = Field(Decimal("0.00"), ge=Decimal("-1000000"), le=Decimal("1000000"), description="Current balance")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata for the account")
    
    @validator('account_type')
    def validate_account_type(cls, v):
        """Validate account type against allowed values"""
        allowed_types = ["checking", "savings", "credit", "cash", "investment", "loan", "other"]
        if v.lower() not in allowed_types:
            raise ValueError(f"Account type must be one of: {', '.join(allowed_types)}")
        return v.lower()
    
    @validator('balance')
    def validate_balance(cls, v):
        """Ensure balance has correct precision"""
        return v.quantize(Decimal("0.01"))

class AccountUpdate(OptimizedBaseModel):
    """Schema for updating an account with validation"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    is_active: Optional[bool] = None
    account_type: Optional[str] = None
    balance: Optional[Decimal] = None
    metadata: Optional[Dict[str, Any]] = None
    
    @validator('name')
    def validate_name(cls, v):
        if v is not None:
            if not v.strip():
                raise ValueError("Account name cannot be empty")
            return v.strip()
        return v
    
    @validator('currency')
    def validate_currency(cls, v):
        if v is not None:
            v = v.upper()
            if len(v) != 3 or not v.isalpha():
                raise ValueError("Currency must be a valid 3-letter ISO code")
            return v
        return v
    
    @validator('account_type')
    def validate_account_type(cls, v):
        if v is not None:
            allowed_types = ["checking", "savings", "credit", "cash", "investment", "loan", "other"]
            if v.lower() not in allowed_types:
                raise ValueError(f"Account type must be one of: {', '.join(allowed_types)}")
            return v.lower()
        return v
    
    @validator('balance')
    def validate_balance(cls, v):
        if v is not None:
            if v < Decimal("-1000000") or v > Decimal("1000000"):
                raise ValueError("Balance must be between -1,000,000 and 1,000,000")
            return v.quantize(Decimal("0.01"))
        return v
    
    @model_validator(mode='after')
    def check_at_least_one_field(self):
        """Ensure at least one field is being updated"""
        values = self.model_dump(exclude_unset=True)
        if not any(values.values()):
            raise ValueError("At least one field must be updated")
        return self

class Account(AccountBase):
    """Schema for returning account data with all fields"""
    id: UUID
    account_type: str
    balance: Decimal
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Cached properties for performance
    _formatted_balance: Optional[str] = None
    
    # Use model_config directly, no need for inner Config class
    model_config = OptimizedBaseModel.model_config
    
    @functools.lru_cache(maxsize=1)
    def get_formatted_balance(self, locale: str = "en_US") -> str:
        """Return properly formatted balance with currency symbol
        Uses caching for better performance.
        """
        # Simple formatting for demo - in production use locale module or similar
        return f"{self.currency} {self.balance:,.2f}"
    
    def get_account_status(self) -> str:
        """Return the status of the account based on balance and activity"""
        if not self.is_active:
            return "inactive"
        
        if self.balance < Decimal("0"):
            return "overdrawn"
        elif self.balance == Decimal("0"):
            return "zero"
        else:
            return "positive"

class AccountFilter(OptimizedBaseModel):
    """Schema for filtering accounts in queries"""
    account_type: Optional[str] = None
    is_active: Optional[bool] = None
    balance_min: Optional[Decimal] = None
    balance_max: Optional[Decimal] = None
    search_term: Optional[str] = None
    
    @validator('account_type')
    def validate_account_type(cls, v):
        if v is not None:
            allowed_types = ["checking", "savings", "credit", "cash", "investment", "loan", "other"]
            if v.lower() not in allowed_types:
                raise ValueError(f"Account type must be one of: {', '.join(allowed_types)}")
            return v.lower()
        return v
    
    @validator('balance_min', 'balance_max')
    def validate_balance_range(cls, v):
        if v is not None:
            if v < Decimal("-1000000") or v > Decimal("1000000"):
                raise ValueError("Balance must be between -1,000,000 and 1,000,000")
            return v.quantize(Decimal("0.01"))
        return v
    
    @model_validator(mode='after')
    def validate_balance_min_max(self):
        values = self.model_dump()
        min_bal = values.get('balance_min')
        max_bal = values.get('balance_max')
        
        if min_bal is not None and max_bal is not None:
            if min_bal > max_bal:
                raise ValueError("Minimum balance cannot be greater than maximum balance")
        
        return self

class AccountSummary(OptimizedBaseModel):
    """Lightweight account summary for listings and dashboards"""
    id: UUID
    name: str
    account_type: str
    balance: Decimal
    currency: str
    is_active: bool
    
    # Use model_config directly instead of inner Config class
    model_config = OptimizedBaseModel.model_config
    
    @functools.lru_cache(maxsize=1)
    def get_formatted_balance(self) -> str:
        """Return properly formatted balance with currency symbol"""
        return f"{self.currency} {self.balance:,.2f}"
