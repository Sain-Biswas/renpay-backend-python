from supabase import create_client, Client
from datetime import datetime

class Inventory:
    def __init__(self, supabase: Client):
        self.supabase = supabase

    def get_all_inventory(self):
        return self.supabase.table('inventory').select('*').execute()

    def get_inventory_item(self, item_id: str):
        return self.supabase.table('inventory').select('*').eq('id', item_id).execute()

    def add_inventory_item(self, name: str, description: str, stock_level: int, price: float):
        return self.supabase.table('inventory').insert({
            "name": name,
            "description": description,
            "stock_level": stock_level,
            "price": price
        }).execute()

    def update_inventory_item(self, item_id: str, **kwargs):
        return self.supabase.table('inventory').update(kwargs).eq('id', item_id).execute()

    def delete_inventory_item(self, item_id: str):
        return self.supabase.table('inventory').delete().eq('id', item_id).execute()