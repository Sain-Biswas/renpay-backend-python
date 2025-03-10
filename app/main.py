from fastapi import FastAPI
from app.routes import auth, transactions, accounts, invoices, tax
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI()

# Include routes
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(transactions.router, prefix="/api/transactions", tags=["transactions"])
app.include_router(accounts.router, prefix="/api/accounts", tags=["accounts"])
app.include_router(invoices.router, prefix="/api/invoices", tags=["invoices"])
app.include_router(tax.router, prefix="/api/tax", tags=["tax"])

# Root endpoint
@app.get("/")
def read_root():
    return {"message": "Welcome to the Supabase FastAPI App"}