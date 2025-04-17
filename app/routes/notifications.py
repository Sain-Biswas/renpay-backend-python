from fastapi import APIRouter, Depends, HTTPException, status, Query
from app.services.supabase_client import get_supabase, run_in_threadpool
from app.dependencies import get_current_user
from app.models.notifications import NotificationCreate, NotificationStatus, NotificationType, NotificationBulkUpdate
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from uuid import UUID

router = APIRouter()

@router.get("/", response_model=List[Dict[str, Any]])
async def get_notifications(
    current_user: dict = Depends(get_current_user),
    status: Optional[NotificationStatus] = None,
    is_important: Optional[bool] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    Get all notifications for the current user with optional filtering.
    """
    supabase = get_supabase()
    
    # Start query
    query = supabase.table("notifications").select("*").eq("user_id", str(current_user["id"]))
    
    # Apply filters
    if status:
        query = query.eq("status", status.value)
    
    if is_important is not None:
        query = query.eq("is_important", is_important)
    
    # Add sorting and pagination
    query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
    
    # Execute query
    result = await run_in_threadpool(lambda: query.execute())
    
    return result.data if result.data else []

@router.get("/count", response_model=Dict[str, int])
async def get_notification_count(
    current_user: dict = Depends(get_current_user)
):
    """
    Get a count of unread and important notifications.
    """
    supabase = get_supabase()
    
    # Get unread count
    unread_result = await run_in_threadpool(
        lambda: supabase.table("notifications")
            .select("id", count="exact")
            .eq("user_id", str(current_user["id"]))
            .eq("status", NotificationStatus.UNREAD.value)
            .execute()
    )
    
    # Get important count
    important_result = await run_in_threadpool(
        lambda: supabase.table("notifications")
            .select("id", count="exact")
            .eq("user_id", str(current_user["id"]))
            .eq("is_important", True)
            .eq("status", NotificationStatus.UNREAD.value)
            .execute()
    )
    
    return {
        "unread": unread_result.count if unread_result.count is not None else 0,
        "important": important_result.count if important_result.count is not None else 0
    }

@router.post("/", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def create_notification(
    notification: NotificationCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new notification for the current user.
    """
    supabase = get_supabase()
    
    # Convert the notification data to a dict
    notification_data = {
        k: (v.value if isinstance(v, (NotificationStatus, NotificationType)) else
            str(v) if isinstance(v, UUID) else v)
        for k, v in notification.dict().items()
    }
    
    # Set user_id if not already set
    if "user_id" not in notification_data:
        notification_data["user_id"] = str(current_user["id"])
    
    result = await run_in_threadpool(
        lambda: supabase.table("notifications").insert(notification_data).execute()
    )
    
    if not result.data or len(result.data) == 0:
        raise HTTPException(status_code=400, detail="Failed to create notification")
    
    return result.data[0]

@router.put("/{notification_id}", response_model=Dict[str, Any])
async def update_notification_status(
    notification_id: UUID,
    status: NotificationStatus,
    current_user: dict = Depends(get_current_user)
):
    """
    Update the status of a notification.
    """
    supabase = get_supabase()
    
    # Check if notification exists and belongs to user
    existing = await run_in_threadpool(
        lambda: supabase.table("notifications")
            .select("*")
            .eq("id", str(notification_id))
            .eq("user_id", str(current_user["id"]))
            .execute()
    )
    
    if not existing.data or len(existing.data) == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    # Update the status
    result = await run_in_threadpool(
        lambda: supabase.table("notifications")
            .update({"status": status.value})
            .eq("id", str(notification_id))
            .execute()
    )
    
    return result.data[0]

@router.post("/bulk-update", response_model=Dict[str, Any])
async def bulk_update_notifications(
    update: NotificationBulkUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Update the status of multiple notifications at once.
    """
    supabase = get_supabase()
    
    # Convert UUIDs to strings and prepare status value
    notification_ids = [str(nid) for nid in update.notification_ids]
    status_value = update.status.value
    
    # Update notifications
    result = await run_in_threadpool(
        lambda: supabase.table("notifications")
            .update({"status": status_value})
            .in_("id", notification_ids)
            .eq("user_id", str(current_user["id"]))
            .execute()
    )
    
    return {"updated": len(result.data) if result.data else 0}

@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    notification_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a notification.
    """
    supabase = get_supabase()
    
    # Check if notification exists and belongs to user
    existing = await run_in_threadpool(
        lambda: supabase.table("notifications")
            .select("*")
            .eq("id", str(notification_id))
            .eq("user_id", str(current_user["id"]))
            .execute()
    )
    
    if not existing.data or len(existing.data) == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    # Delete the notification
    await run_in_threadpool(
        lambda: supabase.table("notifications")
            .delete()
            .eq("id", str(notification_id))
            .execute()
    )
    
    return None

@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_notifications(
    current_user: dict = Depends(get_current_user),
    status: Optional[NotificationStatus] = None
):
    """
    Delete all notifications for the current user with optional status filtering.
    """
    supabase = get_supabase()
    
    # Start delete query
    query = supabase.table("notifications").delete().eq("user_id", str(current_user["id"]))
    
    # Add status filter if provided
    if status:
        query = query.eq("status", status.value)
    
    # Execute delete
    await run_in_threadpool(lambda: query.execute())
    
    return None