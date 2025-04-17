from fastapi import APIRouter, Depends, HTTPException, status
from app.models.preferences import UserPreferences, UserPreferencesCreate, UserPreferencesUpdate
from app.services.supabase_client import get_supabase, run_in_threadpool
from app.dependencies import get_current_user
from typing import Dict, Any
from uuid import UUID

router = APIRouter()

@router.get("/", response_model=Dict[str, Any])
async def get_preferences(current_user: dict = Depends(get_current_user)):
    """
    Get the current user's preferences.
    """
    supabase = get_supabase()
    
    result = await run_in_threadpool(
        lambda: supabase.table("user_preferences")
            .select("*")
            .eq("user_id", str(current_user["id"]))
            .execute()
    )
    
    if not result.data or len(result.data) == 0:
        # Create default preferences if none exist
        default_prefs = {
            "user_id": str(current_user["id"]),
            "language": "en",
            "theme": "light",
            "notification_email": True,
            "notification_app": True,
            "default_currency": "INR",
            "default_tax_rate": 18.0,
            "date_format": "yyyy-MM-dd",
            "time_format": "HH:mm",
            "timezone": "Asia/Kolkata"
        }
        
        result = await run_in_threadpool(
            lambda: supabase.table("user_preferences")
                .insert(default_prefs)
                .execute()
        )
        
        if not result.data or len(result.data) == 0:
            raise HTTPException(status_code=500, detail="Failed to create default preferences")
    
    return result.data[0]

@router.put("/", response_model=Dict[str, Any])
async def update_preferences(
    preferences: UserPreferencesUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Update the current user's preferences.
    """
    supabase = get_supabase()
    
    # Check if preferences exist
    existing = await run_in_threadpool(
        lambda: supabase.table("user_preferences")
            .select("id")
            .eq("user_id", str(current_user["id"]))
            .execute()
    )
    
    # Filter out None values
    update_data = {
        k: (str(v) if isinstance(v, (UUID, type)) else v)
        for k, v in preferences.dict().items()
        if v is not None
    }
    
    if not existing.data or len(existing.data) == 0:
        # Create new preferences
        update_data["user_id"] = str(current_user["id"])
        
        result = await run_in_threadpool(
            lambda: supabase.table("user_preferences")
                .insert(update_data)
                .execute()
        )
    else:
        # Update existing preferences
        result = await run_in_threadpool(
            lambda: supabase.table("user_preferences")
                .update(update_data)
                .eq("user_id", str(current_user["id"]))
                .execute()
        )
    
    if not result.data or len(result.data) == 0:
        raise HTTPException(status_code=500, detail="Failed to update preferences")
    
    return result.data[0]

@router.get("/reset", response_model=Dict[str, Any])
async def reset_preferences(current_user: dict = Depends(get_current_user)):
    """
    Reset user preferences to default values.
    """
    supabase = get_supabase()
    
    default_prefs = {
        "language": "en",
        "theme": "light",
        "notification_email": True,
        "notification_app": True,
        "default_currency": "INR",
        "default_tax_rate": 18.0,
        "date_format": "yyyy-MM-dd",
        "time_format": "HH:mm",
        "timezone": "Asia/Kolkata",
        "sidebar_collapsed": False,
        "show_help_tips": True,
        "default_view_mode": "list",
        "default_dashboard": "overview"
    }
    
    # Check if preferences exist
    existing = await run_in_threadpool(
        lambda: supabase.table("user_preferences")
            .select("id")
            .eq("user_id", str(current_user["id"]))
            .execute()
    )
    
    if not existing.data or len(existing.data) == 0:
        # Create new preferences
        default_prefs["user_id"] = str(current_user["id"])
        
        result = await run_in_threadpool(
            lambda: supabase.table("user_preferences")
                .insert(default_prefs)
                .execute()
        )
    else:
        # Update existing preferences
        result = await run_in_threadpool(
            lambda: supabase.table("user_preferences")
                .update(default_prefs)
                .eq("user_id", str(current_user["id"]))
                .execute()
        )
    
    if not result.data or len(result.data) == 0:
        raise HTTPException(status_code=500, detail="Failed to reset preferences")
    
    return result.data[0]