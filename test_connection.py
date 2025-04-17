import requests
import os
import time
import sys
import asyncio
import concurrent.futures
from typing import Dict, Any, Optional, Tuple
from dotenv import load_dotenv

# Load environment variables only once
load_dotenv()

# Get configuration from environment
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
MAX_RETRIES = int(os.getenv("CONNECTION_MAX_RETRIES", "3"))
RETRY_DELAY = float(os.getenv("CONNECTION_RETRY_DELAY", "0.5"))
TIMEOUT = float(os.getenv("CONNECTION_TIMEOUT", "5.0"))  # Shorter timeout for faster failure

# Prepare HTTP headers once
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Content-Type": "application/json",
    "User-Agent": "Renpay-Backend/1.0",
}

# Use a session for connection pooling
session = requests.Session()
session.headers.update(HEADERS)

def get_health_endpoint(base_url: str) -> str:
    """Determine the health endpoint URL"""
    if not base_url:
        return ""
        
    if "/rest/v1" in base_url:
        return base_url.replace("/rest/v1", "/rest/v1/health")
    else:
        return f"{base_url}/health"
        
    return health_url

async def check_endpoint_async(url: str) -> Tuple[bool, str]:
    """Check a single endpoint with a timeout"""
    with concurrent.futures.ThreadPoolExecutor() as executor:
        try:
            loop = asyncio.get_event_loop()
            future = loop.run_in_executor(
                executor,
                lambda: session.get(url, timeout=TIMEOUT)
            )
            
            # Wait for the result with timeout
            response = await asyncio.wait_for(future, timeout=TIMEOUT)
            
            if response.status_code == 200:
                return True, ""
            else:
                return False, f"Status: {response.status_code}, Body: {response.text[:100]}..."
        except asyncio.TimeoutError:
            return False, "Request timed out"
        except requests.exceptions.ConnectionError:
            return False, "Connection error"
        except Exception as e:
            return False, str(e)

def check_supabase_connection() -> bool:
    """Test connection to Supabase with optimized retry mechanism"""
    
    # Validate configuration
    if not SUPABASE_URL:
        print("❌ Error: SUPABASE_URL is not set in environment variables")
        return False
    
    if not SUPABASE_KEY:
        print("❌ Error: SUPABASE_KEY is not set in environment variables")
        return False
    
    # Get health endpoint URL
    health_url = get_health_endpoint(SUPABASE_URL)
    if not health_url:
        print("❌ Error: Could not determine health endpoint URL")
        return False
        
    # Create event loop for async operations
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Try connecting with retries
    success = False
    last_error = ""
    
    for attempt in range(1, MAX_RETRIES + 1):
        # Show attempt number if retrying
        if attempt > 1:
            print(f"Attempt {attempt}/{MAX_RETRIES}...")
        
        # Check connection asynchronously
        result, error = loop.run_until_complete(check_endpoint_async(health_url))
        
        if result:
            success = True
            break
        else:
            last_error = error
            
            # Only sleep if we're going to retry
            if attempt < MAX_RETRIES:
                # Use exponential backoff with jitter
                jitter = 0.1 * (2 * (0.5 - attempt/MAX_RETRIES))
                sleep_time = RETRY_DELAY * (2 ** (attempt - 1)) + jitter
                print(f"❌ Connection failed. Retrying in {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
    
    # Close the event loop
    loop.close()
    
    # Report result
    if success:
        print("✅ Supabase is reachable!")
        return True
    else:
        print(f"❌ Supabase Connection Failed: {last_error}")
        return False

if __name__ == "__main__":
    # Add timing info
    start_time = time.time()
    result = check_supabase_connection()
    duration = time.time() - start_time
    
    print(f"Connection check completed in {duration:.2f} seconds")
    
    # Exit with appropriate code
    if not result:
        sys.exit(1)  # Exit with error code
