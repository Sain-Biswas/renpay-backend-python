from pydantic import BaseModel, Field, validator, root_validator, model_validator
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from uuid import UUID
from enum import Enum

from app.models.account import OptimizedBaseModel

class Theme(str, Enum):
    """Available UI themes"""
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"
    
class Currency(str, Enum):
    """Common currencies"""
    INR = "INR"  # Indian Rupee
    USD = "USD"  # US Dollar
    EUR = "EUR"  # Euro
    GBP = "GBP"  # British Pound
    JPY = "JPY"  # Japanese Yen
    AUD = "AUD"  # Australian Dollar
    CAD = "CAD"  # Canadian Dollar
    
class DateFormat(str, Enum):
    """Date format options"""
    ISO = "YYYY-MM-DD"        # 2023-01-31
    US = "MM/DD/YYYY"         # 01/31/2023
    EU = "DD/MM/YYYY"         # 31/01/2023
    FULL = "MMMM D, YYYY"     # January 31, 2023
    SHORT = "MMM D, YYYY"     # Jan 31, 2023

class UserPreferencesBase(OptimizedBaseModel):
    """Base model for user preferences with performance optimizations"""
    theme: Theme = Field(default=Theme.SYSTEM, description="UI theme preference")
    currency: Currency = Field(default=Currency.INR, description="Preferred currency")
    date_format: DateFormat = Field(default=DateFormat.ISO, description="Preferred date format")
    language: str = Field(default="en", description="Preferred language code")
    timezone: str = Field(default="Asia/Kolkata", description="Preferred timezone")
    notifications_enabled: bool = Field(default=True, description="Whether notifications are enabled")
    email_notifications: bool = Field(default=True, description="Whether email notifications are enabled")
    
    @validator('language')
    def validate_language(cls, v):
        """Validate language code"""
        valid_languages = ["en", "hi", "mr", "gu", "te", "ta", "kn", "bn"]
        if v not in valid_languages:
            # Default to English if invalid
            return "en"
        return v
    
    @validator('timezone')
    def validate_timezone(cls, v):
        """Validate timezone - this is a simplified check"""
        # In a real implementation, we would check against pytz.all_timezones
        common_timezones = [
            "Asia/Kolkata", "UTC", "America/New_York", "Europe/London", 
            "Australia/Sydney", "Asia/Tokyo", "Europe/Berlin"
        ]
        if v not in common_timezones:
            # Default to Asia/Kolkata if invalid
            return "Asia/Kolkata"
        return v

class UserPreferencesCreate(UserPreferencesBase):
    """Schema for creating user preferences"""
    user_id: UUID = Field(..., description="User ID the preferences belong to")
    sidebar_collapsed: bool = Field(default=False, description="Whether sidebar is collapsed")
    show_help_tips: bool = Field(default=True, description="Whether to show help tips")
    default_view_mode: str = Field(default="list", description="Default view mode")
    default_account_id: Optional[UUID] = Field(default=None, description="Default account ID")
    default_dashboard: str = Field(default="overview", description="Default dashboard view")
    custom_fields: Dict[str, Any] = Field(default_factory=dict, description="Custom preference fields")
    
    @validator('default_view_mode')
    def validate_view_mode(cls, v):
        """Validate view mode"""
        valid_modes = ["list", "grid", "compact", "detailed"]
        if v not in valid_modes:
            return "list"  # Default to list view
        return v
    
    @validator('default_dashboard')
    def validate_dashboard(cls, v):
        """Validate dashboard view"""
        valid_dashboards = ["overview", "transactions", "invoices", "reports", "custom"]
        if v not in valid_dashboards:
            return "overview"  # Default to overview
        return v

class UserPreferencesUpdate(OptimizedBaseModel):
    """Schema for updating user preferences"""
    theme: Optional[Theme] = None
    currency: Optional[Currency] = None
    date_format: Optional[DateFormat] = None
    language: Optional[str] = None
    timezone: Optional[str] = None
    notifications_enabled: Optional[bool] = None
    email_notifications: Optional[bool] = None
    sidebar_collapsed: Optional[bool] = None
    show_help_tips: Optional[bool] = None
    default_view_mode: Optional[str] = None
    default_account_id: Optional[UUID] = None
    default_dashboard: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None
    
    @validator('language')
    def validate_language(cls, v):
        if v is not None:
            valid_languages = ["en", "hi", "mr", "gu", "te", "ta", "kn", "bn"]
            if v not in valid_languages:
                return "en"
        return v
    
    @validator('timezone')
    def validate_timezone(cls, v):
        if v is not None:
            common_timezones = [
                "Asia/Kolkata", "UTC", "America/New_York", "Europe/London", 
                "Australia/Sydney", "Asia/Tokyo", "Europe/Berlin"
            ]
            if v not in common_timezones:
                return "Asia/Kolkata"
        return v
    
    @validator('default_view_mode')
    def validate_view_mode(cls, v):
        if v is not None:
            valid_modes = ["list", "grid", "compact", "detailed"]
            if v not in valid_modes:
                return "list"
        return v
    
    @validator('default_dashboard')
    def validate_dashboard(cls, v):
        if v is not None:
            valid_dashboards = ["overview", "transactions", "invoices", "reports", "custom"]
            if v not in valid_dashboards:
                return "overview"
        return v
    
    @model_validator(mode='after')
    def check_at_least_one_field(self):
        """Ensure at least one field is being updated"""
        values = self.model_dump(exclude_unset=True)
        if not any(values.values()):
            raise ValueError("At least one field must be updated")
        return self

class UserPreferences(UserPreferencesBase):
    """Schema for returning user preferences with all fields"""
    id: UUID
    user_id: UUID
    sidebar_collapsed: bool
    show_help_tips: bool
    default_view_mode: str
    default_account_id: Optional[UUID] = None
    default_dashboard: str
    custom_fields: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    model_config = {
        "from_attributes": True
    }