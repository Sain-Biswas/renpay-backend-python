from pydantic import BaseModel, Field, validator, model_validator, EmailStr
from typing import Optional, Dict, Any, List
from datetime import datetime, date
from uuid import UUID, uuid4
import re

class OptimizedBaseModel(BaseModel):
    """Base model with optimized configuration for better performance"""
    class Config:
        model_immutable = True  # Renamed from frozen in Pydantic v2
        validate_assignment = False  # Skip validation on assignment for performance
        extra = "forbid"  # Prevent accidental field additions
        json_encoders = {  # Custom encoders for better serialization
            datetime: lambda dt: dt.isoformat(),
            date: lambda d: d.isoformat(),
            UUID: str
        }

class UserBase(OptimizedBaseModel):
    """Base user model with common fields and validations"""
    email: EmailStr = Field(..., description="User's email address")
    name: str = Field(..., min_length=2, max_length=100, description="User's full name")
    
    @validator('name')
    def name_must_be_valid(cls, v):
        """Validate user name format"""
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()

class UserCreate(UserBase):
    """Model for user creation with password validation"""
    password: str = Field(..., min_length=8, description="User's password")
    
    @validator('password')
    def password_strength(cls, v):
        """Validate password strength"""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError("Password must contain at least one special character")
        return v

class UserUpdate(OptimizedBaseModel):
    """Model for user updates with optional fields"""
    email: Optional[EmailStr] = None
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    password: Optional[str] = Field(None, min_length=8)
    
    @model_validator(mode='after')
    def check_at_least_one_field(self):
        """Ensure at least one field is being updated"""
        values = self.model_dump(exclude_unset=True)
        if not any(values.values()):
            raise ValueError("At least one field must be updated")
        return self
    
    @validator('password', check_fields=False)
    def validate_password(cls, v):
        """Validate password if provided"""
        if v is None:
            return v
        
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError("Password must contain at least one special character")
        return v

class User(UserBase):
    """Complete user model with all fields"""
    id: UUID = Field(default_factory=uuid4)
    is_active: bool = True
    is_verified: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    last_login: Optional[datetime] = None
    
    class Config(OptimizedBaseModel.Config):
        from_attributes = True  # Enable ORM mode for database integration

class UserInDB(User):
    hashed_password: str     

class Token(BaseModel):
    access_token: str
    token_type: str
    user: Dict[str, Any]

class TokenData(BaseModel):
    email: Optional[str] = None

class TokenResponse(BaseModel):
    """Model for the response returned after successful authentication."""
    access_token: str = Field(..., description="The access token for the user")
    token_type: str = Field(default="bearer", description="The type of the token")
    user: User = Field(..., description="The user associated with the token")

class RefreshToken(BaseModel):
    refresh_token: str = Field(..., description="The refresh token used to get a new access token")

class UserLogin(BaseModel):
    email: EmailStr
    password: str


class PasswordReset(BaseModel):
    """Model for password reset requests."""
    email: EmailStr = Field(..., description="The email address of the user requesting the password reset")
    new_password: str = Field(..., min_length=8, description="The new password for the user")
    confirm_password: str = Field(..., min_length=8, description="Confirmation of the new password")

    @validator('confirm_password')
    def passwords_match(cls, v, values):
        """Ensure that the new password and confirmation match."""
        if 'new_password' in values and v != values['new_password']:
            raise ValueError("Passwords do not match")
        return v

class PasswordChange(BaseModel):
    """Model for changing user passwords."""
    email: EmailStr = Field(..., description="The email address of the user changing the password")
    old_password: str = Field(..., min_length=8, description="The current password of the user")
    new_password: str = Field(..., min_length=8, description="The new password for the user")
    confirm_password: str = Field(..., min_length=8, description="Confirmation of the new password")

    @validator('confirm_password')
    def passwords_match(cls, v, values):
        """Ensure that the new password and confirmation match."""
        if 'new_password' in values and v != values['new_password']:
            raise ValueError("Passwords do not match")
        return v

