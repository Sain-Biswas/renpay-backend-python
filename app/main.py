from fastapi import FastAPI
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

# Importing routes
from app.routes import (
    auth, transactions, accounts, invoices, tax, 
    inventory, notifications, preferences, reports
)
load_dotenv()
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (update for production)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(transactions.router, prefix="/api/transactions", tags=["transactions"])
app.include_router(accounts.router, prefix="/api/accounts", tags=["accounts"])
app.include_router(invoices.router, prefix="/api/invoices", tags=["invoices"])
app.include_router(tax.router, prefix="/api/tax", tags=["tax"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["inventory"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])
app.include_router(preferences.router, prefix="/api/preferences", tags=["preferences"])
app.include_router(reports.router, prefix="/api/report", tags=["reports"])
# Root endpoint
@app.get("/")
def read_root():
    return {"message": "Welcome to the Renpay Backend API"}

