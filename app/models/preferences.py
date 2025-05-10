from supabase import Client
class UserPreferences:
    def __init__(self, supabase: Client):
        self.supabase = supabase

    def get_preferences(self, user_id: str):
        return self.supabase.table('user_preferences').select('*').eq('user_id', user_id).execute()

    def update_preferences(self, user_id: str, **kwargs):
        return self.supabase.table('user_preferences').update(kwargs).eq('user_id', user_id).execute()