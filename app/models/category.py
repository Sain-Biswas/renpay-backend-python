from pydantic import BaseModel, Field, validator, root_validator
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timezone
from uuid import UUID, uuid4
from decimal import Decimal

from app.models.account import OptimizedBaseModel

class CategoryBase(OptimizedBaseModel):
    """Base model for category with optimized performance."""
    name: str = Field(..., min_length=1, max_length=100, description="Category name")
    description: Optional[str] = Field(None, max_length=500, description="Category description")
    color: Optional[str] = Field(
        None, 
        regex=r'^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$',
        description="Hex color code for the category"
    )
    icon: Optional[str] = Field(None, max_length=50, description="Icon identifier for the category")
    
    @validator('name')
    def validate_name(cls, v):
        """Ensure name is properly formatted."""
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()
    
    @validator('color')
    def validate_color(cls, v):
        """Validate and normalize hex color code."""
        if v is not None:
            # Convert to uppercase for consistency
            v = v.upper()
            # Normalize 3-digit hex to 6-digit
            if len(v) == 4:  # Including the # symbol
                v = '#' + ''.join([c+c for c in v[1:]])
        return v

class CategoryCreate(CategoryBase):
    """Schema for creating a category with enhanced validation."""
    id: UUID = Field(default_factory=uuid4, description="Unique identifier for the category")
    parent_id: Optional[UUID] = Field(None, description="Parent category ID for hierarchical categories")
    is_system: bool = Field(default=False, description="Whether this is a system category")
    is_income: bool = Field(default=False, description="Whether this category is for income transactions")
    is_expense: bool = Field(default=True, description="Whether this category is for expense transactions")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata for the category")
    
    @root_validator
    def validate_category_type(cls, values):
        """Ensure category has valid type configuration."""
        is_income = values.get('is_income', False)
        is_expense = values.get('is_expense', True)
        
        # A category should be either for income, expense, or both
        if not is_income and not is_expense:
            raise ValueError("Category must be either for income, expense, or both")
            
        return values

class CategoryUpdate(OptimizedBaseModel):
    """Schema for updating a category with field validations."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    color: Optional[str] = Field(
        None, 
        regex=r'^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$'
    )
    icon: Optional[str] = Field(None, max_length=50)
    parent_id: Optional[UUID] = None
    is_income: Optional[bool] = None
    is_expense: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None
    
    @validator('name')
    def validate_name(cls, v):
        if v is not None:
            if not v.strip():
                raise ValueError("Name cannot be empty")
            return v.strip()
        return v
    
    @validator('color')
    def validate_color(cls, v):
        if v is not None:
            v = v.upper()
            if len(v) == 4:
                v = '#' + ''.join([c+c for c in v[1:]])
        return v
    
    @root_validator
    def check_at_least_one_field(cls, values):
        """Ensure at least one field is being updated."""
        if not any(v is not None for v in values.values()):
            raise ValueError("At least one field must be updated")
        return values
    
    @root_validator
    def validate_category_type(cls, values):
        """Validate income/expense settings if either is being updated."""
        is_income = values.get('is_income')
        is_expense = values.get('is_expense')
        
        if is_income is not None and is_expense is not None:
            if not is_income and not is_expense:
                raise ValueError("Category must be either for income, expense, or both")
                
        return values

class Category(CategoryBase):
    """Schema for returning category data with all fields."""
    id: UUID
    parent_id: Optional[UUID] = None
    is_system: bool
    is_income: bool
    is_expense: bool
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    class Config(OptimizedBaseModel.Config):
        from_attributes = True

class CategoryWithChildren(Category):
    """Category model that includes child categories for hierarchical display."""
    children: List["CategoryWithChildren"] = Field(default_factory=list)
    transaction_count: int = Field(default=0, description="Number of transactions using this category")
    
    def get_full_path(self, separator=" > ") -> str:
        """Return the full category path including parent names (cached for performance)."""
        # This would require database access, so it's just a placeholder
        # In a real implementation, this would be calculated when the model is created
        return self.name 