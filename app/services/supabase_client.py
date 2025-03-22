from supabase import create_client, Client
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Create Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Check connection
try:
    response = supabase.table("users").select("*").limit(1).execute()
    print("✅ Supabase Connection Successful!")
    print("Sample User Data:", response.data)
except Exception as e:
    print("❌ Supabase Connection Failed!")
    print("Error:", str(e))


def get_supabase():
    return supabase   
