from fastapi import APIRouter, Depends
from app.models.preferences import UserPreferences
from app.services.supabase_client import get_supabase
from supabase import Client

router = APIRouter()

@router.get("/api/preferences")
def get_preferences(user_id: str, supabase: Client = Depends(get_supabase)):
    preferences = UserPreferences(supabase)
    return preferences.get_preferences(user_id)

@router.put("/api/preferences")
def update_preferences(user_id: str, supabase: Client = Depends(get_supabase)):
    preferences = UserPreferences(supabase)
    return preferences.update_preferences(user_id)