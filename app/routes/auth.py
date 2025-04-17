from fastapi import APIRouter, Depends, HTTPException, status, Response, BackgroundTasks, Body
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from fastapi.responses import ORJSONResponse
from app.services.supabase_client import get_supabase, with_retry, run_in_threadpool
from utils.security import get_password_hash, verify_password, create_access_token, create_refresh_token, decode_token
from app.models.user import User, Token, RefreshToken, UserCreate, UserUpdate, UserInDB, UserLogin, UserBase, TokenResponse, TokenData, PasswordReset, PasswordChange
from app.models.account import AccountCreate
from datetime import datetime, timedelta, timezone
import os
from app.dependencies import get_current_user
from uuid import uuid4
import time
import logging
from functools import lru_cache
import orjson

# Configure logging
logger = logging.getLogger("renpay-api.auth")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")
router = APIRouter()

# Cache to track failed login attempts
failed_login_attempts = {}
LOGIN_ATTEMPT_EXPIRY = 600  # 10 minutes
MAX_FAILED_ATTEMPTS = 5

async def blacklist_token_async(token: str, user_id: str = None):
    """Blacklist a token asynchronously as a background task"""
    try:
        supabase = get_supabase()
        await run_in_threadpool(
            with_retry(lambda: supabase.table("blacklisted_tokens").insert({
                "token": token,
                "user_id": user_id,
                "created_at": datetime.utcnow().isoformat()
            }).execute())
        )
    except Exception as e:
        # Log the error but don't fail - this is a background task
        logger.error(f"Failed to blacklist token: {str(e)}")

@lru_cache(maxsize=100)
def get_user_by_email(email: str):
    """Cached function to get user by email"""
    supabase = get_supabase()
    result = with_retry(lambda: supabase.table("users").select("*").eq("email", email).execute())()
    return result.data[0] if result.data else None

@router.post("/register", response_model=UserInDB, status_code=status.HTTP_201_CREATED, response_class=ORJSONResponse)
async def register_user(user_data: UserCreate):
    """
    Register a new user with email and password
    """
    supabase = get_supabase()
    
    # Check if user already exists
    result = await run_in_threadpool(
        with_retry(lambda: supabase.table("users")
        .select("*")
        .eq("email", user_data.email)
        .execute())
    )
    
    if result.data and len(result.data) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists"
        )
    
    # Hash the password
    hashed_password = get_password_hash(user_data.password)
    
    # Create user data with hashed password
    user_dict = user_data.model_dump(exclude={"password"})
    user_dict["hashed_password"] = hashed_password
    user_dict["is_active"] = True
    
    # Create user in database
    result = await run_in_threadpool(
        with_retry(lambda: supabase.table("users")
        .insert(user_dict)
        .execute())
    )
    
    if not result.data or len(result.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user"
        )
    
    user = result.data[0]
    
    # Create a default account for the user
    account_data = {
        "name": "Default Account",
        "description": "Default account created at registration",
        "currency": "INR",
        "balance": 0.0,
        "user_id": user["id"]
    }
    
    await run_in_threadpool(
        with_retry(lambda: supabase.table("accounts")
        .insert(account_data)
        .execute())
    )
    
    # Create user preferences
    prefs_data = {
        "user_id": user["id"],
        "default_currency": "INR",
        "language": "en",
        "theme": "light"
    }
    
    await run_in_threadpool(
        with_retry(lambda: supabase.table("user_preferences")
        .insert(prefs_data)
        .execute())
    )
    
    return user

@router.post("/login", response_model=TokenResponse, response_class=ORJSONResponse)
async def login_for_access_token(form_data: UserLogin = Body(...)):
    """
    Login and get access token
    """
    supabase = get_supabase()
    
    # Get user by email
    result = await run_in_threadpool(
        with_retry(lambda: supabase.table("users")
        .select("*")
        .eq("email", form_data.email)
        .eq("is_active", True)
        .execute())
    )
    
    if not result.data or len(result.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = result.data[0]
    
    # Verify password
    if not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create access and refresh tokens
    access_token = create_access_token(
        data={"sub": user["id"]}
    )
    
    refresh_token = create_refresh_token(
        data={"sub": user["id"]}
    )
    
    # Update last login timestamp
    await run_in_threadpool(
        with_retry(lambda: supabase.table("users")
        .update({"last_login": datetime.now(timezone.utc).isoformat()})
        .eq("id", user["id"])
        .execute())
    )
    
    # Log the login for security purposes
    login_log = {
        "user_id": user["id"],
        "ip_address": form_data.ip_address if hasattr(form_data, "ip_address") else None,
        "user_agent": form_data.user_agent if hasattr(form_data, "user_agent") else None,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    await run_in_threadpool(
        with_retry(lambda: supabase.table("login_logs")
        .insert(login_log)
        .execute())
    )
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": user
    }

@router.post("/refresh-token", response_model=TokenResponse, response_class=ORJSONResponse)
async def refresh_access_token(refresh_token: RefreshToken):
    """
    Refresh access token using a valid refresh token
    """
    try:
        # Verify the refresh token
        payload = decode_token(refresh_token.refresh_token)
        user_id = payload.get("sub")
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Get user info
        supabase = get_supabase()
        result = await run_in_threadpool(
            with_retry(lambda: supabase.table("users")
            .select("*")
            .eq("id", user_id)
            .eq("is_active", True)
            .execute())
        )
        
        if not result.data or len(result.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        user = result.data[0]
        
        # Create new tokens
        new_access_token = create_access_token(data={"sub": user_id})
        new_refresh_token = create_refresh_token(data={"sub": user_id})
        
        # Blacklist the old refresh token to prevent reuse
        background_tasks = BackgroundTasks()
        background_tasks.add_task(blacklist_token_async, refresh_token.refresh_token, user_id)
        
        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "user": user
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    token: str = Depends(oauth2_scheme),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    Logout and blacklist the token
    """
    try:
        # Decode token to get user_id
        payload = decode_token(token)
        user_id = payload.get("sub")
        
        # Add token to blacklist
        background_tasks.add_task(blacklist_token_async, token, user_id)
        
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as e:
        # Even if there's an error, we still want to return 204
        # The client will clear their tokens anyway
        return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.put("/users/me", response_model=UserInDB, response_class=ORJSONResponse)
async def update_current_user(
    user_update: UserUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Update current user's profile
    """
    supabase = get_supabase()
    
    # Filter out None values and prepare update data
    update_data = {k: v for k, v in user_update.model_dump(exclude_unset=True).items() if v is not None}
    
    # If no fields to update, return current user
    if not update_data:
        return current_user
    
    # Update user in database
    result = await run_in_threadpool(
        with_retry(lambda: supabase.table("users")
        .update(update_data)
        .eq("id", current_user["id"])
        .execute())
    )
    
    if not result.data or len(result.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user"
        )
    
    return result.data[0]

@router.post("/request-password-reset", status_code=status.HTTP_204_NO_CONTENT)
async def request_password_reset(email: str = Body(..., embed=True)):
    """
    Request a password reset
    """
    supabase = get_supabase()
    
    # Find user by email
    result = await run_in_threadpool(
        with_retry(lambda: supabase.table("users")
        .select("*")
        .eq("email", email)
        .eq("is_active", True)
        .execute())
    )
    
    # For security, don't indicate if the email exists
    if not result.data or len(result.data) == 0:
        # We still return 204 even if user doesn't exist to prevent enumeration
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    
    user = result.data[0]
    
    # Generate a password reset token
    reset_token = str(uuid4())
    expiry = datetime.now(timezone.utc) + timedelta(hours=1)  # Token valid for 1 hour
    
    # Store reset token in database
    reset_data = {
        "user_id": user["id"],
        "token": reset_token,
        "expires_at": expiry.isoformat(),
        "used": False
    }
    
    await run_in_threadpool(
        with_retry(lambda: supabase.table("password_reset_tokens")
        .insert(reset_data)
        .execute())
    )
    
    # In a real application, you would send an email with the reset link
    # For now, just log it (in production, use a proper email service)
    logger.info(f"Password reset token for {email}: {reset_token}")
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(reset_data: PasswordReset):
    """
    Reset password using a valid reset token
    """
    supabase = get_supabase()
    
    # Verify token exists and is valid
    result = await run_in_threadpool(
        with_retry(lambda: supabase.table("password_reset_tokens")
        .select("*")
        .eq("token", reset_data.token)
        .eq("used", False)
        .gte("expires_at", datetime.now(timezone.utc).isoformat())
        .execute())
    )
    
    if not result.data or len(result.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    token_data = result.data[0]
    
    # Hash the new password
    hashed_password = get_password_hash(reset_data.new_password)
    
    # Update user's password
    user_result = await run_in_threadpool(
        with_retry(lambda: supabase.table("users")
        .update({"hashed_password": hashed_password})
        .eq("id", token_data["user_id"])
        .execute())
    )
    
    if not user_result.data or len(user_result.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update password"
        )
    
    # Mark token as used
    await run_in_threadpool(
        with_retry(lambda: supabase.table("password_reset_tokens")
        .update({"used": True})
        .eq("id", token_data["id"])
        .execute())
    )
    
    # Optionally, blacklist all existing tokens for this user for security
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    password_change: PasswordChange,
    current_user: dict = Depends(get_current_user)
):
    """
    Change user's password
    """
    supabase = get_supabase()
    
    # Get current password hash
    result = await run_in_threadpool(
        with_retry(lambda: supabase.table("users")
        .select("hashed_password")
        .eq("id", current_user["id"])
        .execute())
    )
    
    if not result.data or len(result.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Verify current password
    if not verify_password(password_change.current_password, result.data[0]["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect password"
        )
    
    # Hash the new password
    hashed_password = get_password_hash(password_change.new_password)
    
    # Update the password
    update_result = await run_in_threadpool(
        with_retry(lambda: supabase.table("users")
        .update({"hashed_password": hashed_password})
        .eq("id", current_user["id"])
        .execute())
    )
    
    if not update_result.data or len(update_result.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update password"
        )
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get("/users/me", response_model=UserInDB, response_class=ORJSONResponse)
async def get_user_me(current_user: dict = Depends(get_current_user)):
    """
    Get current user's profile
    """
    return current_user
