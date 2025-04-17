from supabase import create_client, Client
import os
from dotenv import load_dotenv
import time
import asyncio
from functools import lru_cache, wraps
import httpx
from typing import Dict, Any, Callable, TypeVar, Optional, Union, List, Tuple
import concurrent.futures
import random
import logging
from datetime import datetime, timedelta

# Configure logging
logger = logging.getLogger("renpay-api.supabase")

# Load environment variables once at startup
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Enhanced configuration for performance
MAX_RETRIES = int(os.getenv("SUPABASE_MAX_RETRIES", "3"))
RETRY_DELAY = float(os.getenv("SUPABASE_RETRY_DELAY", "0.5"))
MAX_CONNECTIONS = int(os.getenv("SUPABASE_MAX_CONNECTIONS", "10"))
CACHE_TTL = int(os.getenv("SUPABASE_CACHE_TTL", "300"))  # 5 minutes
CACHE_SIZE = int(os.getenv("SUPABASE_CACHE_SIZE", "1000"))

# Thread pool for parallel operations
thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONNECTIONS)

# Result cache with TTL - dictionary of {cache_key: (result, timestamp)}
_result_cache: Dict[str, Tuple[Any, float]] = {}

# Type variable for generic function
T = TypeVar('T')

class SupabaseError(Exception):
    """Custom exception for Supabase related errors"""
    def __init__(self, message: str, status_code: Optional[int] = None, 
                 error_code: Optional[str] = None, details: Any = None):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details
        super().__init__(self.message)

    def __str__(self):
        return f"{self.message} (Status: {self.status_code}, Code: {self.error_code})"

def initialize_supabase() -> Client:
    """Initialize and return a cached Supabase client with connection pooling"""
    logger.info("Initializing Supabase client with connection pooling")
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        error_msg = "Supabase URL and Key must be provided in environment variables"
        logger.error(error_msg)
        raise SupabaseError(error_msg)
    
    try:
        # Configure connection settings
        timeout_config = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=15.0)
        limits_config = httpx.Limits(max_connections=MAX_CONNECTIONS, max_keepalive_connections=MAX_CONNECTIONS//2)
        
        # Create client with modern initialization pattern
        return create_client(
            SUPABASE_URL, 
            SUPABASE_KEY,
        )
    except Exception as e:
        error_msg = f"Failed to initialize Supabase client: {str(e)}"
        logger.error(error_msg)
        raise SupabaseError(error_msg)

# Create Supabase client
try:
    supabase: Client = initialize_supabase()
except Exception as e:
    logger.critical(f"CRITICAL: Could not initialize Supabase client: {str(e)}")
    # We'll raise an exception when get_supabase is called, but allow the app to start

def with_retry(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator for retry mechanism with exponential backoff"""
    @wraps(func)
    def wrapper(*args, **kwargs) -> T:
        last_error = None
        start_time = time.time()
        
        for attempt in range(MAX_RETRIES):
            try:
                result = func(*args, **kwargs)
                if attempt > 0:
                    logger.info(f"Retry succeeded on attempt {attempt+1} after {time.time()-start_time:.2f}s")
                return result
            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    # Exponential backoff with jitter
                    jitter = random.uniform(-0.1, 0.1) * RETRY_DELAY * (2 ** attempt)
                    sleep_time = RETRY_DELAY * (2 ** attempt) + jitter
                    logger.warning(f"Retry attempt {attempt+1}/{MAX_RETRIES} failed: {str(e)}. Retrying in {sleep_time:.2f}s")
                    time.sleep(sleep_time)
                else:
                    logger.error(f"All retry attempts failed. Last error: {str(e)}")
        
        # If all retries fail
        if isinstance(last_error, httpx.HTTPStatusError) and last_error.response.status_code:
            status_code = last_error.response.status_code
            try:
                error_details = last_error.response.json()
                error_code = error_details.get("code", "unknown")
                error_message = error_details.get("message", str(last_error))
            except:
                error_code = "unknown"
                error_message = str(last_error)
                
            raise SupabaseError(
                message=f"Database operation failed: {error_message}",
                status_code=status_code,
                error_code=error_code,
                details=str(last_error)
            )
        
        raise SupabaseError(f"Operation failed after {MAX_RETRIES} retries: {str(last_error)}")
    
    return wrapper

def memoize(ttl: int = CACHE_TTL):
    """Cache result of function call with time-to-live expiration"""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            # Create cache key from function name and arguments
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # Check if result is in cache and not expired
            current_time = time.time()
            if cache_key in _result_cache:
                result, timestamp = _result_cache[cache_key]
                if current_time - timestamp < ttl:
                    return result
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            _result_cache[cache_key] = (result, current_time)
            
            # Clean expired cache entries periodically (1% chance per call)
            if random.random() < 0.01:
                _clean_cache(current_time)
                
            return result
        return wrapper
    return decorator

def invalidate_cache(pattern: Optional[str] = None) -> int:
    """
    Invalidate cache entries matching a pattern or all entries
    Returns count of invalidated entries
    """
    global _result_cache
    count = 0
    
    if pattern:
        # Delete entries matching pattern
        keys_to_delete = [k for k in _result_cache.keys() if pattern in k]
        for key in keys_to_delete:
            del _result_cache[key]
            count += 1
    else:
        # Delete all entries
        count = len(_result_cache)
        _result_cache = {}
    
    return count

def _clean_cache(current_time: float) -> None:
    """Remove expired entries from cache"""
    global _result_cache
    expired_keys = [
        k for k, v in _result_cache.items() 
        if current_time - v[1] > CACHE_TTL
    ]
    
    for key in expired_keys:
        del _result_cache[key]
    
    if expired_keys:
        logger.debug(f"Cleaned {len(expired_keys)} expired cache entries")

def run_in_thread(func: Callable[..., T], *args, **kwargs) -> concurrent.futures.Future[T]:
    """Run function in thread pool"""
    return thread_pool.submit(func, *args, **kwargs)

async def run_in_threadpool(func: Callable[..., T], *args, **kwargs) -> T:
    """Run a CPU-bound or blocking I/O function in a threadpool"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        thread_pool, 
        lambda: func(*args, **kwargs)
    )

def get_supabase() -> Client:
    """Get the Supabase client instance with validation"""
    if 'supabase' not in globals():
        # If the global client failed to initialize, try again now
        try:
            globals()['supabase'] = initialize_supabase()
        except Exception as e:
            raise SupabaseError(f"Supabase client not available: {str(e)}")
    
    return supabase

async def check_database_connection() -> Dict[str, Any]:
    """Check database connection with detailed diagnostics"""
    start_time = time.time()
    success = False
    error_message = ""
    
    try:
        # Run a simple query to test connection
        result = await run_in_threadpool(
            with_retry(lambda: get_supabase().table("users").select("count", count="exact").limit(1).execute())
        )
        success = True
        response_time = time.time() - start_time
        return {
            "status": "connected",
            "response_time_ms": round(response_time * 1000, 2),
            "timestamp": datetime.now().isoformat(),
            "pool_size": MAX_CONNECTIONS,
            "cache_entries": len(_result_cache)
        }
    except Exception as e:
        error_message = str(e)
        return {
            "status": "error",
            "error": error_message,
            "timestamp": datetime.now().isoformat()
        }

# Export optimized utility functions for use in routes
__all__ = [
    'get_supabase', 
    'with_retry', 
    'memoize', 
    'run_in_thread', 
    'run_in_threadpool',
    'check_database_connection',
    'invalidate_cache',
    'SupabaseError'
]   
