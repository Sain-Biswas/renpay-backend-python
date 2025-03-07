from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.utils.security import decode_token
from app.services.supabase_client import get_supabase

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Decode the token
    payload = decode_token(token)
    if payload is None:
        raise credentials_exception
    
    # Check if the token is blacklisted
    supabase = get_supabase()
    blacklisted_token = supabase.table("blacklisted_tokens").select("*").eq("token", token).execute()
    if blacklisted_token.data:
        raise credentials_exception
    
    email = payload.get("sub")
    if email is None:
        raise credentials_exception
    
    # Fetch the user from the database
    user = supabase.table("users").select("*").eq("email", email).execute()
    if not user.data:
        raise credentials_exception
    return user.data[0]