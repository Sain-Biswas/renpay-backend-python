from fastapi import APIRouter, Depends, HTTPException, status, Query
from app.services.supabase_client import get_supabase
from app.dependencies import get_current_user
from typing import List, Optional
from uuid import UUID
from datetime import datetime

router = APIRouter()

@router.get("/", response_model=List[dict])
async def get_inventory_items(
    current_user: dict = Depends(get_current_user),
    name: Optional[str] = None,
    sku: Optional[str] = None,
    low_stock_only: bool = False
):
    """Get all inventory items with optional filtering"""
    supabase = get_supabase()
    
    # Start query
    query = supabase.table("inventory").select("*").eq("user_id", current_user["id"])
    
    # Apply filters
    if name:
        query = query.ilike("name", f"%{name}%")
    if sku:
        query = query.eq("sku", sku)
    if low_stock_only:
        query = query.lt("stock_level", supabase.table("inventory").select("low_stock_threshold"))
    
    # Execute query
    result = query.execute()
    return result.data if result.data else []

@router.get("/{item_id}", response_model=dict)
async def get_inventory_item(
    item_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Get a specific inventory item by ID"""
    supabase = get_supabase()
    
    result = supabase.table("inventory").select("*").eq("id", str(item_id)).eq("user_id", current_user["id"]).execute()
    
    if not result.data or len(result.data) == 0:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    
    return result.data[0]

@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_inventory_item(
    item: dict,
    current_user: dict = Depends(get_current_user)
):
    """Create a new inventory item"""
    supabase = get_supabase()
    
    # Add user_id
    item["user_id"] = current_user["id"]
    
    # Add creation timestamps
    now = datetime.now().isoformat()
    item["created_at"] = now
    item["updated_at"] = now
    
    result = supabase.table("inventory").insert(item).execute()
    
    if not result.data or len(result.data) == 0:
        raise HTTPException(status_code=400, detail="Failed to create inventory item")
    
    return result.data[0]

@router.put("/{item_id}", response_model=dict)
async def update_inventory_item(
    item_id: UUID,
    item_update: dict,
    current_user: dict = Depends(get_current_user)
):
    """Update an existing inventory item"""
    supabase = get_supabase()
    
    # Check if item exists and belongs to user
    existing = supabase.table("inventory").select("*").eq("id", str(item_id)).eq("user_id", current_user["id"]).execute()
    
    if not existing.data or len(existing.data) == 0:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    
    # Update the item
    result = supabase.table("inventory").update(item_update).eq("id", str(item_id)).execute()
    
    return result.data[0]

@router.patch("/{item_id}/stock", response_model=dict)
async def update_stock_level(
    item_id: UUID,
    adjustment: int = Query(..., description="Amount to adjust stock by (positive to add, negative to subtract)"),
    current_user: dict = Depends(get_current_user)
):
    """Adjust the stock level of an inventory item"""
    supabase = get_supabase()
    
    # Get the current item
    result = supabase.table("inventory").select("*").eq("id", str(item_id)).eq("user_id", current_user["id"]).execute()
    
    if not result.data or len(result.data) == 0:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    
    current_item = result.data[0]
    new_stock_level = current_item["stock_level"] + adjustment
    
    if new_stock_level < 0:
        raise HTTPException(status_code=400, detail="Stock level cannot be negative")
    
    # Update the stock level
    update_result = supabase.table("inventory").update({"stock_level": new_stock_level}).eq("id", str(item_id)).execute()
    
    return update_result.data[0]

@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inventory_item(
    item_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Delete an inventory item"""
    supabase = get_supabase()
    
    # Check if item exists and belongs to user
    existing = supabase.table("inventory").select("*").eq("id", str(item_id)).eq("user_id", current_user["id"]).execute()
    
    if not existing.data or len(existing.data) == 0:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    
    # Delete the item
    supabase.table("inventory").delete().eq("id", str(item_id)).execute()
    
    return None