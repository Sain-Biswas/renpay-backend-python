import requests
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")

try:
    response = requests.get(SUPABASE_URL)
    if response.status_code == 200:
        print("✅ Supabase is reachable!")
    else:
        print(f"❌ Supabase returned status {response.status_code}")
except Exception as e:
    print("❌ Supabase Connection Failed!")
    print("Error:", e)
