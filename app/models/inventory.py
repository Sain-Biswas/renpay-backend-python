from supabase import create_client, Client
from datetime import datetime
from pydantic import BaseModel, Field, validator, root_validator, model_validator
from typing import Optional, List, Dict, Any, Union
from uuid import UUID, uuid4
from decimal import Decimal
import functools

from app.models.account import OptimizedBaseModel

class InventoryItemBase(OptimizedBaseModel):
    """Base model for inventory item with optimized performance."""
    name: str = Field(..., min_length=1, max_length=200, description="Item name")
    description: Optional[str] = Field(None, max_length=1000, description="Item description")
    sku: Optional[str] = Field(None, max_length=50, description="Stock keeping unit (SKU)")
    barcode: Optional[str] = Field(None, max_length=50, description="Item barcode")
    price: Decimal = Field(..., ge=0, description="Item selling price")
    cost_price: Optional[Decimal] = Field(None, ge=0, description="Item cost price")
    tax_rate: Decimal = Field(default=Decimal("18.0"), ge=0, description="Tax rate percentage")
    stock_level: int = Field(default=0, ge=0, description="Current stock level")
    unit: str = Field(default="item", description="Unit of measurement")
    
    @validator('name')
    def validate_name(cls, v):
        """Ensure item name is valid."""
        if not v or not v.strip():
            raise ValueError("Item name cannot be empty")
        return v.strip()
    
    @validator('price', 'cost_price')
    def validate_price(cls, v, values, **kwargs):
        """Ensure price has correct precision."""
        if v is not None:
            return Decimal(str(v)).quantize(Decimal("0.01"))
        return v
    
    @validator('tax_rate')
    def validate_tax_rate(cls, v):
        """Ensure tax rate has valid range."""
        if v is not None:
            if v < 0 or v > 100:
                raise ValueError("Tax rate must be between 0 and 100")
            return Decimal(str(v)).quantize(Decimal("0.01"))
        return v

class InventoryItemCreate(InventoryItemBase):
    """Schema for creating an inventory item with enhanced validation."""
    id: Optional[UUID] = Field(default_factory=uuid4, description="Unique identifier")
    category: Optional[str] = None
    supplier_id: Optional[UUID] = None
    supplier_name: Optional[str] = None
    reorder_level: Optional[int] = Field(None, ge=0, description="Level at which to reorder")
    reorder_quantity: Optional[int] = Field(None, ge=0, description="Quantity to reorder")
    min_stock_level: Optional[int] = Field(None, ge=0, description="Minimum stock level")
    max_stock_level: Optional[int] = Field(None, ge=0, description="Maximum stock level")
    is_active: bool = Field(default=True, description="Whether item is active in inventory")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    
    @model_validator(mode='after')
    def validate_stock_levels(self):
        """Validate stock level logic."""
        values = self.model_dump()
        min_stock = values.get('min_stock_level')
        max_stock = values.get('max_stock_level')
        reorder_level = values.get('reorder_level')
        
        if min_stock is not None and max_stock is not None:
            if min_stock > max_stock:
                raise ValueError("Minimum stock level cannot be greater than maximum stock level")
        
        if reorder_level is not None and min_stock is not None:
            if reorder_level < min_stock:
                raise ValueError("Reorder level should not be less than minimum stock level")
                
        return self

class InventoryItemUpdate(OptimizedBaseModel):
    """Schema for updating an inventory item with field validations."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    sku: Optional[str] = Field(None, max_length=50)
    barcode: Optional[str] = Field(None, max_length=50)
    price: Optional[Decimal] = Field(None, ge=0)
    cost_price: Optional[Decimal] = Field(None, ge=0)
    tax_rate: Optional[Decimal] = Field(None, ge=0, le=100)
    stock_level: Optional[int] = Field(None, ge=0)
    unit: Optional[str] = None
    category: Optional[str] = None
    supplier_id: Optional[UUID] = None
    supplier_name: Optional[str] = None
    reorder_level: Optional[int] = Field(None, ge=0)
    reorder_quantity: Optional[int] = Field(None, ge=0)
    min_stock_level: Optional[int] = Field(None, ge=0)
    max_stock_level: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None
    
    @validator('name')
    def validate_name(cls, v):
        if v is not None:
            if not v.strip():
                raise ValueError("Item name cannot be empty")
            return v.strip()
        return v
    
    @validator('price', 'cost_price')
    def validate_price(cls, v):
        if v is not None:
            return Decimal(str(v)).quantize(Decimal("0.01"))
        return v
    
    @validator('tax_rate')
    def validate_tax_rate(cls, v):
        if v is not None:
            if v < 0 or v > 100:
                raise ValueError("Tax rate must be between 0 and 100")
            return Decimal(str(v)).quantize(Decimal("0.01"))
        return v
    
    @model_validator(mode='after')
    def check_at_least_one_field(self):
        """Ensure at least one field is being updated"""
        values = self.model_dump(exclude_unset=True)
        if not any(values.values()):
            raise ValueError("At least one field must be updated")
        return self
    
    @model_validator(mode='after')
    def validate_stock_levels(self):
        """Validate stock levels"""
        values = self.model_dump(exclude_unset=True)
        
        if 'current_stock' in values and values['current_stock'] is not None:
            if values['current_stock'] < 0:
                raise ValueError("Current stock cannot be negative")
                
        if 'reorder_point' in values and values['reorder_point'] is not None:
            if values['reorder_point'] < 0:
                raise ValueError("Reorder point cannot be negative")
                
        if ('current_stock' in values and values['current_stock'] is not None and
            'reorder_point' in values and values['reorder_point'] is not None):
            if values['current_stock'] < values['reorder_point']:
                self.status = "Low Stock"
                
        return self

class InventoryItem(InventoryItemBase):
    """Schema for returning inventory item data with all fields."""
    id: UUID
    category: Optional[str] = None
    supplier_id: Optional[UUID] = None
    supplier_name: Optional[str] = None
    reorder_level: Optional[int] = None
    reorder_quantity: Optional[int] = None
    min_stock_level: Optional[int] = None
    max_stock_level: Optional[int] = None
    is_active: bool = True
    last_restock_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    @property
    def stock_value(self) -> Decimal:
        """Calculate the current stock value (cost_price * stock_level)."""
        cost = self.cost_price if self.cost_price is not None else self.price
        return (cost * Decimal(str(self.stock_level))).quantize(Decimal("0.01"))
    
    @property
    def retail_value(self) -> Decimal:
        """Calculate the retail value (price * stock_level)."""
        return (self.price * Decimal(str(self.stock_level))).quantize(Decimal("0.01"))
    
    @property
    def is_low_stock(self) -> bool:
        """Check if item is below reorder level."""
        if self.reorder_level is None:
            return False
        return self.stock_level <= self.reorder_level
    
    class Config(OptimizedBaseModel.Config):
        from_attributes = True

class InventoryStockAdjustment(OptimizedBaseModel):
    """Model for inventory stock adjustments."""
    inventory_id: UUID = Field(..., description="ID of the inventory item")
    adjustment_quantity: int = Field(..., description="Quantity to adjust (positive or negative)")
    reason: str = Field(..., min_length=1, max_length=200, description="Reason for adjustment")
    reference: Optional[str] = Field(None, description="Reference number or document")
    notes: Optional[str] = Field(None, max_length=1000, description="Additional notes")
    
    @validator('adjustment_quantity')
    def validate_quantity(cls, v):
        """Ensure quantity is not zero."""
        if v == 0:
            raise ValueError("Adjustment quantity cannot be zero")
        return v

class InventoryFilter(OptimizedBaseModel):
    """Schema for filtering inventory items."""
    search_term: Optional[str] = None
    category: Optional[str] = None
    min_price: Optional[Decimal] = Field(None, ge=0)
    max_price: Optional[Decimal] = Field(None, ge=0)
    is_active: Optional[bool] = None
    low_stock_only: Optional[bool] = Field(default=False, description="Only show items below reorder level")
    out_of_stock_only: Optional[bool] = Field(default=False, description="Only show out of stock items")
    
    @model_validator(mode='after')
    def validate_price_range(self):
        """Ensure min_price is not greater than max_price if both are provided."""
        values = self.model_dump()
        min_price = values.get('min_price')
        max_price = values.get('max_price')
        
        if min_price is not None and max_price is not None:
            if min_price > max_price:
                raise ValueError("Minimum price cannot be greater than maximum price")
        
        return self

class Inventory:
    def __init__(self, supabase: Client):
        self.supabase = supabase

    def get_all_inventory(self):
        return self.supabase.table('inventory').select('*').execute()

    def get_inventory_item(self, item_id: str):
        return self.supabase.table('inventory').select('*').eq('id', item_id).execute()

    def add_inventory_item(self, name: str, description: str, stock_level: int, price: float):
        return self.supabase.table('inventory').insert({
            "name": name,
            "description": description,
            "stock_level": stock_level,
            "price": price
        }).execute()

    def update_inventory_item(self, item_id: str, **kwargs):
        return self.supabase.table('inventory').update(kwargs).eq('id', item_id).execute()

    def delete_inventory_item(self, item_id: str):
        return self.supabase.table('inventory').delete().eq('id', item_id).execute()