from fastapi import APIRouter, Depends
from app.models.notifications import Notifications
from app.services.supabase_client import get_supabase
from supabase import Client

router = APIRouter()

@router.get("/api/notifications")
def get_notifications(user_id: str, supabase: Client = Depends(get_supabase)):
    notifications = Notifications(supabase)
    return notifications.get_all_notifications(user_id)

# Add other endpoints (POST, PUT, DELETE) similarly