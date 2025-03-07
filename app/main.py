from fastapi import FastAPI
from app.routes import auth
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI()

# Include routes
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])

# Root endpoint
@app.get("/")
def read_root():
    return {"message": "Welcome to the Supabase FastAPI App"}