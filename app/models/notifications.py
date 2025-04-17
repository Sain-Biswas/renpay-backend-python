from supabase import Client
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime, timezone
from uuid import UUID, uuid4
from enum import Enum

from app.models.account import OptimizedBaseModel

class NotificationType(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    SYSTEM = "system"

class NotificationStatus(str, Enum):
    READ = "read"
    UNREAD = "unread"
    DISMISSED = "dismissed"

class NotificationBase(OptimizedBaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    message: str = Field(..., min_length=1, max_length=1000)
    notification_type: NotificationType = Field(default=NotificationType.INFO)
    is_important: bool = Field(default=False)

    @field_validator('title', 'message')
    @classmethod
    def validate_text_fields(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()

class NotificationCreate(NotificationBase):
    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    link: Optional[str] = Field(None, max_length=500)
    status: NotificationStatus = Field(default=NotificationStatus.UNREAD)
    scheduled_time: Optional[datetime] = None
    expiry_time: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator('scheduled_time', 'expiry_time')
    @classmethod
    def ensure_utc(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v

    @model_validator(mode='before')
    @classmethod
    def validate_scheduling(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        scheduled = values.get('scheduled_time')
        expiry = values.get('expiry_time')

        if scheduled and expiry and scheduled > expiry:
            raise ValueError("Scheduled time cannot be after expiry time")

        if scheduled and scheduled > datetime.now(timezone.utc):
            values['status'] = NotificationStatus.UNREAD

        return values

class NotificationUpdate(OptimizedBaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=100)
    message: Optional[str] = Field(None, min_length=1, max_length=1000)
    notification_type: Optional[NotificationType] = None
    status: Optional[NotificationStatus] = None
    is_important: Optional[bool] = None
    link: Optional[str] = Field(None, max_length=500)
    scheduled_time: Optional[datetime] = None
    expiry_time: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None

    @field_validator('title', 'message')
    @classmethod
    def validate_text_fields(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("Text fields cannot be empty")
        return v.strip() if v else v

    @field_validator('scheduled_time', 'expiry_time')
    @classmethod
    def ensure_utc(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v

    @model_validator(mode='before')
    @classmethod
    def check_at_least_one_field(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if not any(v is not None for v in values.values()):
            raise ValueError("At least one field must be updated")
        return values

    @model_validator(mode='before')
    @classmethod
    def validate_scheduling(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        scheduled = values.get('scheduled_time')
        expiry = values.get('expiry_time')

        if scheduled and expiry and scheduled > expiry:
            raise ValueError("Scheduled time cannot be after expiry time")

        if scheduled and scheduled > datetime.now(timezone.utc):
            values['status'] = NotificationStatus.UNREAD

        return values

class Notification(NotificationBase):
    id: UUID
    user_id: UUID
    status: NotificationStatus
    link: Optional[str] = None
    scheduled_time: Optional[datetime] = None
    expiry_time: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        return self.expiry_time is not None and datetime.now(timezone.utc) > self.expiry_time

    @property
    def is_scheduled(self) -> bool:
        return self.scheduled_time is not None and datetime.now(timezone.utc) < self.scheduled_time

    model_config = {
        "from_attributes": True
    }


class NotificationBulkUpdate(OptimizedBaseModel):
    notification_ids: List[UUID] = Field(..., min_items=1)
    status: NotificationStatus

    @field_validator('notification_ids')
    @classmethod
    def validate_ids(cls, v: List[UUID]) -> List[UUID]:
        if not v:
            raise ValueError("At least one notification ID is required")
        return v

class NotificationFilter(OptimizedBaseModel):
    status: Optional[NotificationStatus] = None
    notification_type: Optional[NotificationType] = None
    is_important: Optional[bool] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    search_term: Optional[str] = None

    @model_validator(mode='before')
    @classmethod
    def validate_date_range(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        start = values.get('start_date')
        end = values.get('end_date')

        if start and end and start > end:
            raise ValueError("Start date must be before end date")
        return values

class Notifications:
    def __init__(self, supabase: Client):
        self.supabase = supabase

    def get_all_notifications(self, user_id: str):
        return self.supabase.table('notifications').select('*').eq('user_id', user_id).execute()

    def create_notification(self, user_id: str, message: str):
        return self.supabase.table('notifications').insert({
            "user_id": user_id,
            "message": message
        }).execute()

    def update_notification(self, notification_id: str, status: str):
        return self.supabase.table('notifications').update({"status": status}).eq('id', notification_id).execute()

    def delete_notification(self, notification_id: str):
        return self.supabase.table('notifications').delete().eq('id', notification_id).execute()
