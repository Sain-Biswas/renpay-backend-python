from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from app.services.supabase_client import get_supabase
from app.utils.security import get_password_hash, verify_password, create_access_token
from app.models.user import User, Token
from datetime import timedelta
import os
from app.dependencies import get_current_user

router = APIRouter()

@router.post("/register")
async def register(user: User):
    supabase = get_supabase()
    hashed_password = get_password_hash(user.password)
    try:
        result = supabase.table("users").insert({
            "email": user.email,
            "hashed_password": hashed_password
        }).execute()
        return {"message": "User registered successfully", "data": result.data}
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
    access_token_expires = timedelta(minutes=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")))
    access_token = create_access_token(
        data={"sub": user.data[0]["email"]}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    # Invalidate token logic (if needed)
    return {"message": "Logged out successfully"}

@router.get("/me")
async def read_users_me(current_user: dict = Depends(get_current_user)):
    return current_user