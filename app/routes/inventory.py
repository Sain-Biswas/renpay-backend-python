from fastapi import APIRouter, Depends
from app.models.inventory import Inventory
from app.services.supabase_client import get_supabase
from supabase import Client
router = APIRouter()
@router.get("/api/inventory")
def get_inventory(supabase: Client = Depends(get_supabase)):
    inventory = Inventory(supabase)
    return inventory.get_all_inventory()
# Add other endpoints (POST, PUT, DELETE) similarly