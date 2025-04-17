from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta
import os
import time
from typing import Optional, Dict, Any, Tuple, Set, List, TypeVar, cast, Callable, Union
from functools import lru_cache, wraps
import random
import logging
import hashlib
import secrets
import re
from collections import OrderedDict
import base64

# Configure logging
logger = logging.getLogger("renpay-api.security")

# Type definitions
T = TypeVar('T')
TokenData = Dict[str, Any]
UserID = str
IPAddress = str
RateLimitKey = Union[str, int]

# Optimize password hashing configuration
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,  # Balanced security/performance
)

# Use faster variants when available
try:
    # Try to import the faster pyjwt library
    import jwt as pyjwt
    USE_PYJWT = True
    logger.info("Using PyJWT for token processing (faster)")
except ImportError:
    USE_PYJWT = False
    logger.info("Using python-jose for token processing")

# Security configuration from environment variables with defaults
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "52560000"))  # 100 years in minutes
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "36500"))  # 100 years in days
PASSWORD_MIN_LENGTH = int(os.getenv("PASSWORD_MIN_LENGTH", "8"))
FAILED_LOGIN_LIMIT = int(os.getenv("FAILED_LOGIN_LIMIT", "5"))
FAILED_LOGIN_WINDOW = int(os.getenv("FAILED_LOGIN_WINDOW", "15"))  # minutes
TOKEN_BLACKLIST: Set[str] = set()  # Store hashed tokens that have been explicitly revoked
DISABLE_TOKEN_EXPIRY = True  # Flag to disable token expiration checks

# More efficient token cache using OrderedDict for LRU behavior
class LRUCache(OrderedDict):
    """Limit size, evicting the least recently used items on insertion."""
    
    def __init__(self, maxsize: int = 128):
        self.maxsize = maxsize
        super().__init__()
        
    def __getitem__(self, key: str) -> Any:
        value = super().__getitem__(key)
        self.move_to_end(key)
        return value
        
    def __setitem__(self, key: str, value: Any) -> None:
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        if len(self) > self.maxsize:
            oldest = next(iter(self))
            del self[oldest]

# Token cache for frequent decode operations (user auth)
TOKEN_CACHE_TTL = 60  # 60 seconds cache for decoded tokens
TOKEN_CACHE_SIZE = 1000  # Maximum number of tokens to cache
token_cache = LRUCache(TOKEN_CACHE_SIZE)
last_token_cache_cleanup = time.time()

# Failed login tracking
failed_login_attempts: Dict[str, Dict[str, Any]] = {}
ip_blacklist: Set[IPAddress] = set()

# Rate limiting caches
rate_limit_caches: Dict[str, Dict[RateLimitKey, Dict[str, Any]]] = {}

# Validate environment variables
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is not set")
elif len(SECRET_KEY) < 32:
    logger.warning("SECRET_KEY is shorter than recommended (32+ characters)")

def check_password_strength(password: str) -> Tuple[bool, str]:
    """
    Check if a password meets security requirements
    Returns (valid, message) tuple
    """
    if not password:
        return False, "Password cannot be empty"
        
    if len(password) < PASSWORD_MIN_LENGTH:
        return False, f"Password must be at least {PASSWORD_MIN_LENGTH} characters"
    
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"
    
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"
    
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number"
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain at least one special character"
    
    # Check for common password patterns
    if re.match(r'^[a-zA-Z]+\d{1,4}$', password):  # Simple word followed by numbers
        return False, "Password follows a common pattern (word + numbers)"
    
    # Check for keyboard sequences
    keyboard_rows = [
        "qwertyuiop", "asdfghjkl", "zxcvbnm"
    ]
    for row in keyboard_rows:
        for i in range(len(row) - 2):
            if row[i:i+3].lower() in password.lower():
                return False, "Password contains a keyboard sequence"
    
    return True, "Password is strong"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password with optimized hashing"""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        logger.error(f"Password verification error: {str(e)}")
        return False

def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt with optimal settings"""
    return pwd_context.hash(password)

def create_token_id() -> str:
    """Create a cryptographically secure token ID"""
    # Using URL-safe base64 for shorter IDs that are still secure
    return base64.urlsafe_b64encode(secrets.token_bytes(12)).decode().rstrip('=')

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token with optimized encoding"""
    to_encode = data.copy()
    
    # Use provided expiration or default (100 years)
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),  # Issued at time
        "jti": create_token_id(),  # Unique token ID to prevent replay attacks
        "token_type": "access"
    })
    
    # Use the faster library if available
    if USE_PYJWT:
        return pyjwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    else:
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(data: Dict[str, Any]) -> str:
    """Create a refresh token with longer expiration (7 days)"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({
        "exp": expire, 
        "iat": datetime.utcnow(),  # Issued at time
        "jti": create_token_id(),  # Unique ID for refresh tokens 
        "token_type": "refresh"
    })
    
    # Use the faster library if available
    if USE_PYJWT:
        return pyjwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    else:
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def hash_token(token: str) -> str:
    """Create a hash of a token for storage and comparison"""
    return hashlib.sha256(token.encode()).hexdigest()

def clean_token_cache() -> None:
    """Remove expired entries from token cache"""
    global token_cache, last_token_cache_cleanup
    current_time = time.time()
    
    # Only clean if it's been at least 60 seconds since last cleanup
    if current_time - last_token_cache_cleanup < 60:
        return
        
    # The LRUCache handles size management, but we still need to check TTL
    expired_keys = []
    for token, (payload, timestamp) in token_cache.items():
        if current_time - timestamp > TOKEN_CACHE_TTL:
            expired_keys.append(token)
    
    for key in expired_keys:
        try:
            del token_cache[key]
        except KeyError:
            pass  # Already removed somehow
    
    last_token_cache_cleanup = current_time
    
    # Log statistics for monitoring
    logger.debug(f"Token cache cleanup: {len(token_cache)} entries remaining")

def decode_token(token: str, verify_exp: bool = True) -> Optional[Dict[str, Any]]:
    """
    Decode and validate a JWT token with caching for performance
    """
    # Check if token has been blacklisted
    if hash_token(token) in TOKEN_BLACKLIST:
        return None
    
    # Check cache first for faster lookup
    if token in token_cache:
        try:
            payload, timestamp = token_cache[token]
            if time.time() - timestamp < TOKEN_CACHE_TTL:
                # Return cached result and skip expiration check when DISABLE_TOKEN_EXPIRY is True
                if DISABLE_TOKEN_EXPIRY or not verify_exp or (verify_exp and not is_payload_expired(payload)):
                    return payload
        except (KeyError, ValueError, TypeError):
            # Handle any unexpected cache format issues
            pass
    
    try:
        # Use the faster library if available
        if USE_PYJWT:
            payload = pyjwt.decode(
                token, 
                SECRET_KEY, 
                algorithms=[ALGORITHM], 
                options={"verify_exp": verify_exp and not DISABLE_TOKEN_EXPIRY}
            )
        else:
            payload = jwt.decode(
                token, 
                SECRET_KEY, 
                algorithms=[ALGORITHM], 
                options={"verify_exp": verify_exp and not DISABLE_TOKEN_EXPIRY}
            )
        
        # Validate required token fields
        if "sub" not in payload:
            logger.warning("Token missing 'sub' field")
            return None
            
        if verify_exp and not DISABLE_TOKEN_EXPIRY and "exp" not in payload:
            logger.warning("Token missing 'exp' field")
            return None
        
        # Cache successful decode
        token_cache[token] = (payload, time.time())
        
        # Clean cache occasionally (1% chance per call)
        if random.random() < 0.01:
            clean_token_cache()
            
        return payload
    except (JWTError, pyjwt.PyJWTError) if USE_PYJWT else JWTError as e:
        logger.warning(f"Token decode failed: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error decoding token: {str(e)}")
        return None

def is_payload_expired(payload: Optional[Dict[str, Any]]) -> bool:
    """Check if a token payload is expired (faster than full decode)"""
    # If token expiry is disabled, always return False (not expired)
    if DISABLE_TOKEN_EXPIRY:
        return False
        
    if not payload or "exp" not in payload:
        return True
        
    exp = payload["exp"]
    now = datetime.utcnow().timestamp()
    return exp < now

@lru_cache(maxsize=100)
def is_token_expired(token: str) -> bool:
    """
    Check if a token is expired (with caching for frequent checks)
    """
    # If token expiry is disabled, always return False (not expired)
    if DISABLE_TOKEN_EXPIRY:
        return False
        
    payload = decode_token(token, verify_exp=False)
    return is_payload_expired(payload) if payload else True

def revoke_token(token: str) -> None:
    """
    Explicitly revoke a token
    """
    token_hash = hash_token(token)
    TOKEN_BLACKLIST.add(token_hash)
    
    # Remove from cache if present
    if token in token_cache:
        try:
            del token_cache[token]
        except KeyError:
            pass

def record_failed_login(identifier: str, ip_address: IPAddress) -> Tuple[bool, int]:
    """
    Record a failed login attempt and check if account should be temporarily locked
    Returns (should_lock, attempts_remaining) tuple
    """
    current_time = time.time()
    cutoff_time = current_time - (FAILED_LOGIN_WINDOW * 60)
    
    # Create entry if it doesn't exist
    if identifier not in failed_login_attempts:
        failed_login_attempts[identifier] = {
            "attempts": 1,
            "first_attempt": current_time,
            "last_attempt": current_time,
            "ip_addresses": {ip_address}
        }
        return False, FAILED_LOGIN_LIMIT - 1
    
    # Get existing entry and update
    entry = failed_login_attempts[identifier]
    
    # Reset if outside window
    if entry["last_attempt"] < cutoff_time:
        entry["attempts"] = 1
        entry["first_attempt"] = current_time
        entry["ip_addresses"] = {ip_address}
    else:
        entry["attempts"] += 1
        entry["ip_addresses"].add(ip_address)
    
    entry["last_attempt"] = current_time
    
    # Check if should lock
    if entry["attempts"] >= FAILED_LOGIN_LIMIT:
        # Track the IP address if multiple failures
        if len(entry["ip_addresses"]) < 3:  # If concentrated from few IPs
            for ip in entry["ip_addresses"]:
                ip_blacklist.add(ip)
        logger.warning(f"Account {identifier} locked due to failed login attempts")
        return True, 0
    
    return False, FAILED_LOGIN_LIMIT - entry["attempts"]

def reset_failed_logins(identifier: str) -> None:
    """Reset failed login counter after successful login"""
    if identifier in failed_login_attempts:
        del failed_login_attempts[identifier]

def is_ip_blacklisted(ip_address: IPAddress) -> bool:
    """Check if an IP address is blacklisted due to suspicious activity"""
    return ip_address in ip_blacklist

def clean_security_caches() -> None:
    """Periodic cleanup of security caches to prevent memory leaks"""
    global failed_login_attempts, ip_blacklist
    
    current_time = time.time()
    cutoff_time = current_time - (FAILED_LOGIN_WINDOW * 2 * 60)  # Double the window for cleanup
    
    # Clean failed login attempts
    failed_login_attempts = {
        k: v for k, v in failed_login_attempts.items()
        if v["last_attempt"] > cutoff_time
    }
    
    # Clean token cache
    clean_token_cache()
    
    # Limit blacklist size (keep most recent entries)
    if len(ip_blacklist) > 1000:
        logger.info(f"Resetting IP blacklist (size exceeded 1000 entries)")
        ip_blacklist = set()
    
    # Limit TOKEN_BLACKLIST size (this grows over time as tokens are revoked)
    if len(TOKEN_BLACKLIST) > 10000:
        logger.info(f"Resetting token blacklist (size exceeded 10000 entries)")
        TOKEN_BLACKLIST.clear()
        
    logger.debug(f"Security cache cleanup: {len(failed_login_attempts)} failed logins, {len(ip_blacklist)} blacklisted IPs, {len(TOKEN_BLACKLIST)} blacklisted tokens")

# Rate limiting with improved performance
def rate_limit(limit: int, window: int = 60, key_func: Optional[Callable] = None):
    """
    Decorator for rate limiting functions
    
    Args:
        limit: max number of calls
        window: time window in seconds
        key_func: optional function to extract key from args/kwargs. 
                 If None, uses first argument as key
    """
    def decorator(func):
        # Create a unique cache for each decorated function
        cache_id = f"{func.__module__}.{func.__name__}"
        if cache_id not in rate_limit_caches:
            rate_limit_caches[cache_id] = {}
        
        func_cache = rate_limit_caches[cache_id]
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Determine the rate limit key
            if key_func:
                key = key_func(*args, **kwargs)
            else:
                # Default: use first argument as key (often user_id or similar)
                key = str(args[0]) if args else "default"
                
            now = time.time()
            
            # Initialize or reset counter if needed
            if key not in func_cache:
                func_cache[key] = {"count": 0, "reset_at": now + window, "first_call": now}
            
            # Reset counter if window expired
            if now > func_cache[key]["reset_at"]:
                func_cache[key] = {"count": 0, "reset_at": now + window, "first_call": now}
            
            # Check limit
            if func_cache[key]["count"] >= limit:
                time_remaining = func_cache[key]["reset_at"] - now
                raise ValueError(f"Rate limit exceeded: {limit} calls per {window} seconds. Try again in {time_remaining:.1f} seconds")
            
            # Increment and call
            func_cache[key]["count"] += 1
            return func(*args, **kwargs)
        
        return wrapper
    return decorator

def get_rate_limit_status(func_name: str, key: RateLimitKey) -> Dict[str, Any]:
    """Get the current rate limit status for a function/key combination"""
    cache_id = func_name
    if cache_id not in rate_limit_caches:
        return {"limit": "unknown", "remaining": "unknown", "reset_at": 0}
    
    func_cache = rate_limit_caches[cache_id]
    key_str = str(key)
    
    if key_str not in func_cache:
        return {"limit": "unknown", "remaining": "unknown", "reset_at": 0}
    
    entry = func_cache[key_str]
    return {
        "limit": limit,  # From the decorator
        "remaining": limit - entry["count"],
        "reset_at": entry["reset_at"],
        "reset_in_seconds": max(0, entry["reset_at"] - time.time())
    }

def generate_csrf_token() -> str:
    """Generate a secure CSRF token"""
    return secrets.token_hex(32)
    
def verify_csrf_token(stored_token: str, request_token: str) -> bool:
    """Verify that the CSRF token in the request matches the stored token"""
    if not stored_token or not request_token:
        return False
    return secrets.compare_digest(stored_token, request_token)

# Export functions
__all__ = [
    'verify_password',
    'get_password_hash',
    'create_access_token',
    'create_refresh_token',
    'decode_token',
    'is_token_expired',
    'hash_token',
    'check_password_strength',
    'record_failed_login',
    'reset_failed_logins',
    'is_ip_blacklisted',
    'clean_security_caches',
    'rate_limit',
    'revoke_token',
    'generate_csrf_token',
    'verify_csrf_token',
    'get_rate_limit_status'
]