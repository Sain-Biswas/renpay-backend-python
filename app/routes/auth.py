from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from app.services.supabase_client import get_supabase
from utils.security import get_password_hash, verify_password, create_access_token, decode_token
from app.models.user import User, Token
from app.models.account import AccountCreate
from datetime import datetime, timedelta
import os
from app.dependencies import get_current_user
from uuid import uuid4

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")
router = APIRouter()

@router.post("/register")
async def register(user: User):
    supabase = get_supabase()
    hashed_password = get_password_hash(user.password)
    
    try:
        # Insert new user with name
        user_result = supabase.table("users").insert({
            "email": user.email,
            "hashed_password": hashed_password,
            "name": user.name  # 👈 Added name field
        }).execute()

        if not user_result.data:
            raise HTTPException(status_code=400, detail="Failed to register user")

        user_id = user_result.data[0]["id"]
        
        # Create a default account for the user
        account_data = {
            "id": str(uuid4()),
            "user_id": user_id,
            "name": "Default Account",
            "balance": 0.0
        }

        account_result = supabase.table("accounts").insert(account_data).execute()

        if not account_result.data:
            raise HTTPException(status_code=400, detail="User registered but failed to create default account")
        
        return {
            "message": "User registered successfully, and default account created",
            "user": "Default Account",
            "account": account_result.data[0]
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    supabase = get_supabase()
    user = supabase.table("users").select("*").eq("email", form_data.username).execute()
    
    if not user.data or not verify_password(form_data.password, user.data[0]["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={"sub": user.data[0]["email"]},
        expires_delta=None  # Set to None for no expiration
    )

    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "user": {
            "id": user.data[0]["id"],
            "email": user.data[0]["email"]
        }
    }

@router.post("/logout")
async def logout(token: str = Depends(oauth2_scheme)):
    supabase = get_supabase()
    
    # Decode the token to get its expiration time
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    
    # expires_at = datetime.fromtimestamp(payload["exp"])
    
    # Add the token to the blacklist
    # try:
    #     supabase.table("blacklisted_tokens").insert({
    #         "token": token,
    #         "expires_at": expires_at.isoformat()
    #     }).execute()
    #     return {"message": "Logged out successfully"}
    # except Exception as e:
    #     raise HTTPException(
    #         status_code=status.HTTP_400_BAD_REQUEST,
    #         detail=str(e),
    #     )

@router.get("/me")
async def read_users_me(current_user: dict = Depends(get_current_user)):
    return current_user
