from supabase import Client
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