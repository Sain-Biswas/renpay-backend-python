from fastapi import Depends, HTTPException, status, Request, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer
from utils.security import decode_token, is_token_expired
from app.services.supabase_client import get_supabase, with_retry, memoize, run_in_threadpool, SupabaseError
from functools import lru_cache
import time
import asyncio
from typing import Dict, Any, Optional, List, Tuple, Set
import logging
from datetime import datetime

# Configure logging
logger = logging.getLogger("renpay-api.auth")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=True)

# Enhanced caching mechanisms
user_cache: Dict[str, Dict[str, Any]] = {}
USER_CACHE_TTL = 300  # 5 minutes in seconds
MAX_CACHE_SIZE = 1000  # Maximum number of users to cache

# Cache statistics for monitoring
cache_stats = {
    "hits": 0,
    "misses": 0,
    "cleanups": 0,
    "evictions": 0,
    "last_cleanup": time.time()
}

# Blacklist cache with set for faster lookups
blacklist_cache: Set[str] = set()
BLACKLIST_CACHE_TTL = 600  # 10 minutes in seconds
last_blacklist_refresh = time.time()

# Last cache cleanup timestamp
last_cleanup = time.time()
CLEANUP_INTERVAL = 60  # Clean cache every 60 seconds

def get_cached_user(user_id: str) -> Optional[Dict[str, Any]]:
    """Get a user from cache or return None if expired or not found"""
    global cache_stats
    
    if user_id in user_cache:
        cached_data = user_cache[user_id]
        if time.time() - cached_data["timestamp"] < USER_CACHE_TTL:
            # Update access timestamp for LRU tracking
            cached_data["last_accessed"] = time.time()
            cache_stats["hits"] += 1
            return cached_data["user"]
    
    cache_stats["misses"] += 1
    return None

def cache_user(user_id: str, user_data: Dict[str, Any]) -> None:
    """Store user data in cache with current timestamp"""
    global last_cleanup, user_cache
    
    # Clean cache if it's too large or cleanup interval passed
    current_time = time.time()
    if (len(user_cache) > MAX_CACHE_SIZE or 
            current_time - last_cleanup > CLEANUP_INTERVAL):
        cleanup_cache()
        last_cleanup = current_time
    
    user_cache[user_id] = {
        "user": user_data,
        "timestamp": current_time,
        "last_accessed": current_time
    }

def cleanup_cache() -> None:
    """Remove expired or least recently used items from cache"""
    global user_cache, cache_stats
    current_time = time.time()
    cache_size_before = len(user_cache)
    
    # First remove expired items
    expired_keys = [
        k for k, v in user_cache.items() 
        if current_time - v["timestamp"] > USER_CACHE_TTL
    ]
    
    for key in expired_keys:
        del user_cache[key]
    
    # If still too large, remove least recently accessed items
    if len(user_cache) > MAX_CACHE_SIZE:
        sorted_cache = sorted(
            user_cache.items(), 
            key=lambda x: x[1]["last_accessed"]
        )
        
        # Calculate how many items to remove
        to_remove = len(user_cache) - MAX_CACHE_SIZE
        
        # Keep only the most recently used items
        user_cache = dict(sorted_cache[to_remove:])
        
        cache_stats["evictions"] += to_remove
    
    cache_stats["cleanups"] += 1
    logger.debug(f"Cache cleanup: removed {cache_size_before - len(user_cache)} items")

async def refresh_blacklist_cache() -> None:
    """Refresh the blacklist cache from database"""
    global blacklist_cache, last_blacklist_refresh
    
    current_time = time.time()
    # Only refresh if the TTL has expired
    if current_time - last_blacklist_refresh < BLACKLIST_CACHE_TTL:
        return
    
    try:
        supabase = get_supabase()
        # Execute the query in a thread pool to not block
        result = await run_in_threadpool(
            lambda: with_retry(
                lambda: supabase.table("blacklisted_tokens")
                .select("token")
                .execute()
            )()
        )
        
        # Update the cache
        blacklist_cache = set(item["token"] for item in result.data) if result.data else set()
        last_blacklist_refresh = current_time
        
        logger.debug(f"Refreshed blacklist cache with {len(blacklist_cache)} tokens")
    except Exception as e:
        logger.error(f"Failed to refresh blacklist cache: {str(e)}")

async def is_token_blacklisted(token: str, force_refresh: bool = False) -> bool:
    """Check if a token is blacklisted with efficient caching"""
    # Refresh cache if needed
    if force_refresh or time.time() - last_blacklist_refresh >= BLACKLIST_CACHE_TTL:
        await refresh_blacklist_cache()
    
    # Fast check in local cache
    if token in blacklist_cache:
        return True
    
    # If not in cache, check database as fallback (might be a new blacklisted token)
    try:
        supabase = get_supabase()
        result = await run_in_threadpool(
            lambda: with_retry(
                lambda: supabase.table("blacklisted_tokens")
                .select("token")
                .eq("token", token)
                .execute()
            )()
        )
        
        # If found in DB but not in cache, add to cache
        if result.data and len(result.data) > 0:
            blacklist_cache.add(token)
            return True
        
        return False
    except Exception as e:
        logger.warning(f"Error checking blacklisted token: {str(e)}")
        # Default to not blacklisted if check fails to prevent lockouts
        return False

async def get_current_user(
    background_tasks: BackgroundTasks,
    request: Request,
    token: str = Depends(oauth2_scheme)
) -> Dict[str, Any]:
    """Get the current authenticated user with optimized performance"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Track authentication timing
    auth_start = time.time()
    
    try:
        # Decode the token (fast operation, no need to cache)
        payload = decode_token(token)
        if payload is None or is_token_expired(token):
            logger.warning(f"Invalid or expired token: {token[:10]}...")
            raise credentials_exception
        
        # Check if the token is blacklisted (with caching)
        if await is_token_blacklisted(token):
            logger.warning(f"Blacklisted token used: {token[:10]}...")
            raise credentials_exception
        
        email = payload.get("sub")
        if email is None:
            logger.warning("Token missing subject claim")
            raise credentials_exception
        
        # Check cache first (fast in-memory operation)
        cached_user = get_cached_user(email)
        if cached_user:
            # Background refresh user data if it's getting old (75% of TTL)
            cache_age = time.time() - user_cache[email]["timestamp"]
            if cache_age > (USER_CACHE_TTL * 0.75):
                background_tasks.add_task(refresh_user_data, email, token)
                
            auth_time = time.time() - auth_start
            request.state.auth_time = auth_time
            logger.debug(f"Auth from cache in {auth_time*1000:.2f}ms: {email}")
            return cached_user
        
        # Fetch the user from the database
        try:
            supabase = get_supabase()
            # Execute the database query in a threadpool to not block
            user_result = await run_in_threadpool(
                lambda: with_retry(
                    lambda: supabase.table("users").select("*").eq("email", email).execute()
                )()
            )
            
            if not user_result.data:
                logger.warning(f"User not found for email: {email}")
                raise credentials_exception
                
            # Cache the user data
            user_data = user_result.data[0]
            cache_user(email, user_data)
            
            auth_time = time.time() - auth_start
            request.state.auth_time = auth_time
            logger.debug(f"Auth from DB in {auth_time*1000:.2f}ms: {email}")
            return user_data
            
        except SupabaseError as e:
            logger.error(f"Supabase error during authentication: {str(e)}")
            raise credentials_exception
        except Exception as e:
            logger.error(f"Database error during authentication: {str(e)}")
            raise credentials_exception
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during authentication: {str(e)}")
        raise credentials_exception

async def refresh_user_data(email: str, token: str) -> None:
    """Background task to refresh user data in cache"""
    try:
        supabase = get_supabase()
        user_result = await run_in_threadpool(
            lambda: with_retry(
                lambda: supabase.table("users").select("*").eq("email", email).execute()
            )()
        )
        
        if user_result.data and len(user_result.data) > 0:
            user_data = user_result.data[0]
            cache_user(email, user_data)
            logger.debug(f"Refreshed cache for user: {email}")
    except Exception as e:
        logger.warning(f"Failed to refresh user data for {email}: {str(e)}")

def get_cache_stats() -> Dict[str, Any]:
    """Get statistics about the auth cache for monitoring"""
    global cache_stats, user_cache, blacklist_cache
    
    return {
        "user_cache_size": len(user_cache),
        "blacklist_cache_size": len(blacklist_cache),
        "hits": cache_stats["hits"],
        "misses": cache_stats["misses"],
        "hit_ratio": cache_stats["hits"] / (cache_stats["hits"] + cache_stats["misses"]) if (cache_stats["hits"] + cache_stats["misses"]) > 0 else 0,
        "cleanups": cache_stats["cleanups"],
        "evictions": cache_stats["evictions"],
        "last_cleanup": datetime.fromtimestamp(last_cleanup).isoformat(),
        "last_blacklist_refresh": datetime.fromtimestamp(last_blacklist_refresh).isoformat()
    }