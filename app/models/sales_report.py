from supabase import Client
class SalesReport:
    def __init__(self, supabase: Client):
        self.supabase = supabase

    def get_sales_report(self, user_id: str, start_date: str, end_date: str):
        return self.supabase.table('sales_reports').select('*').eq('user_id', user_id).gte('report_date', start_date).lte('report_date', end_date).execute()