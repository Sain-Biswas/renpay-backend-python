import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Fetch values from .env file
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

print("Supabase URL:", supabase_url)
print("Supabase Key:", supabase_key[:10] + "********")  # Partially hidden for security
