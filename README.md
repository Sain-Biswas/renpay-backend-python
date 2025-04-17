# Renpay Tech

A comprehensive financial management API built with FastAPI and Supabase, providing persistent authentication, transaction management, account tracking, and invoicing capabilities with GST compliance. Optimized for high performance and reliability.

## Table of Contents

- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Environment Variables](#environment-variables)
  - [Running the Application](#running-the-application)
- [Key Features](#key-features)
  - [Persistent Authentication](#persistent-authentication)
  - [Performance Optimizations](#performance-optimizations)
  - [Database Schema Improvements](#database-schema-improvements)
- [API Documentation](#api-documentation)
  - [Authentication](#authentication)
  - [Transactions](#transactions)
  - [Accounts](#accounts)
  - [Invoices](#invoices)
  - [Tax Calculation & Compliance](#tax-calculation--compliance)
- [Database Schema](#database-schema)
- [Component Integration](#component-integration)

## Getting Started

### Prerequisites

- Python 3.8+
- Supabase account
- PostgreSQL database (provided by Supabase)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/renpay-backend-python.git
cd renpay-backend-python
```

2. Create a virtual environment:
```bash
python -m venv .venv
```

3. Activate the virtual environment:
```bash
# On Windows
.venv\Scripts\activate
# On macOS/Linux
source .venv/bin/activate
```

4. Install dependencies:
```bash
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file in the root directory with the following variables:

```
# Supabase Configuration
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key

# Security Configuration
SECRET_KEY=your_secret_key_for_jwt
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=52560000   # 100 years in minutes
REFRESH_TOKEN_EXPIRE_DAYS=36500        # 100 years in days
DISABLE_TOKEN_EXPIRY=true              # Disable token expiration checks
PASSWORD_MIN_LENGTH=8
FAILED_LOGIN_LIMIT=5
FAILED_LOGIN_WINDOW=15

# Connection Settings
CONNECTION_MAX_RETRIES=3
CONNECTION_RETRY_DELAY=0.5
CONNECTION_TIMEOUT=5.0

# Application Defaults
DEFAULT_TAX_RATE=18.0
DEFAULT_CURRENCY=INR
DEFAULT_LANGUAGE=en
DEFAULT_TIMEZONE=Asia/Kolkata

# Performance Settings
TOKEN_CACHE_TTL=300
USER_CACHE_TTL=300
USER_CACHE_MAX_SIZE=1000

# Logging Configuration
LOG_LEVEL=INFO
LOG_FORMAT=%(asctime)s - %(name)s - %(levelname)s - %(message)s

# Rate Limiting
RATE_LIMIT_DEFAULT=1000000
RATE_LIMIT_WINDOW=60000

# Blacklist Configuration
BLACKLIST_CACHE_TTL=300
BLACKLIST_CACHE_MAX_SIZE=1000
```

### Running the Application

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`.

You can access the interactive API documentation at `http://localhost:8000/docs` which provides a Swagger UI to test all endpoints directly from your browser.

## Key Features

### Persistent Authentication

Renpay implements a persistent authentication system that never logs users out automatically:

- Token expiration is configured for 100 years by default
- The `DISABLE_TOKEN_EXPIRY` flag ensures token validation never checks expiration
- Blacklisted token management ensures security while maintaining persistent sessions
- The database schema includes enhanced token management tables for tracking sessions

### Performance Optimizations

The application incorporates numerous performance optimizations:

- **Caching**: 
  - LRU token cache with configurable TTL
  - User data caching to minimize database lookups
  - Periodic cache cleanup to prevent memory leaks

- **Model Optimizations**:
  - Immutable Pydantic models with `frozen=True` for better caching
  - Optimized JSON serializers for common types
  - Custom validators to ensure data integrity at model level

- **Database Operations**:
  - Specialized indexes for common query patterns
  - Optimized views for financial reporting
  - Threadpool execution for database operations
  - Query builder optimization for efficient filters

### Database Schema Improvements

- Enhanced security tables for token management
- Centralized security configuration table 
- Optimized indexes for high-volume transaction processing
- Efficient SQL views for financial snapshots and reporting

## API Documentation

### Authentication

#### Register a new user

```
POST /api/auth/register
```

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword"
}
```

**Response (200 OK):**
```json
{
  "message": "User registered successfully",
  "data": {
    "id": "uuid",
    "email": "user@example.com",
    "created_at": "2023-01-01T00:00:00Z",
    "updated_at": "2023-01-01T00:00:00Z"
  }
}
```

#### Login

```
POST /api/auth/login
```

**Request Body (form-data : x-www-form-urlencoded):**
```
username: user@example.com
password: securepassword
```

**Note:** This endpoint expects form data, not JSON. The email should be sent as the `username` field.

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

#### Logout

```
POST /api/auth/logout
```

**Headers:**
```
Authorization: Bearer your_access_token
```

**Response (200 OK):**
```json
{
  "message": "Logged out successfully"
}
```

#### Get current user

```
GET /api/auth/me
```

**Headers:**
```
Authorization: Bearer your_access_token
```

**Response (200 OK):**
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "created_at": "2023-01-01T00:00:00Z",
  "updated_at": "2023-01-01T00:00:00Z"
}
```

### Transactions

#### Get all transactions

```
GET /api/transactions
```

**Headers:**
```
Authorization: Bearer your_access_token
```

**Query Parameters:**
- `start_date` (optional): Filter by start date (ISO format)
- `end_date` (optional): Filter by end date (ISO format)
- `transaction_type` (optional): Filter by type (sale, expense, transfer, other)
- `category` (optional): Filter by category
- `account_id` (optional): Filter by account UUID

**Response (200 OK):**
```json
[
  {
    "id": "uuid",
    "amount": 100.50,
    "description": "Product sale",
    "transaction_type": "sale",
    "category": "Sales",
    "date": "2023-01-01T00:00:00Z",
    "user_id": "uuid",
    "account_id": "uuid",
    "created_at": "2023-01-01T00:00:00Z",
    "updated_at": "2023-01-01T00:00:00Z"
  }
]
```

#### Create a transaction

```
POST /api/transactions
```

**Headers:**
```
Authorization: Bearer your_access_token
```

**Request Body:**
```json
{
  "amount": 100.50,
  "description": "Product sale",
  "transaction_type": "sale",  // Allowed values: "sale", "expense", "transfer", "other"
  "category": "Sales",
  "date": "2023-01-01T00:00:00Z",
  "account_id": "uuid" // Optional, will use default account if not provided
}
```

**Response (201 Created):**
```json
{
  "id": "uuid",
  "amount": 100.50,
  "description": "Product sale",
  "transaction_type": "sale",
  "category": "Sales",
  "date": "2023-01-01T00:00:00Z",
  "user_id": "uuid",
  "account_id": "uuid",
  "created_at": "2023-01-01T00:00:00Z",
  "updated_at": "2023-01-01T00:00:00Z"
}
```

**Note:** When creating a transaction with `transaction_type: "sale"`, an invoice will be automatically generated.

#### Get a specific transaction

```
GET /api/transactions/{transaction_id}
```

**Headers:**
```
Authorization: Bearer your_access_token
```

**Response (200 OK):**
```json
{
  "id": "uuid",
  "amount": 100.50,
  "description": "Product sale",
  "transaction_type": "sale",
  "category": "Sales",
  "date": "2023-01-01T00:00:00Z",
  "user_id": "uuid",
  "account_id": "uuid",
  "created_at": "2023-01-01T00:00:00Z",
  "updated_at": "2023-01-01T00:00:00Z"
}
```

#### Update a transaction

```
PUT /api/transactions/{transaction_id}
```

**Headers:**
```
Authorization: Bearer your_access_token
```

**Request Body:**
```json
{
  "amount": 150.75,
  "description": "Updated product sale",
  "transaction_type": "sale",
  "category": "Sales",
  "date": "2023-01-01T00:00:00Z",
  "account_id": "uuid"
}
```

**Response (200 OK):**
```json
{
  "id": "uuid",
  "amount": 150.75,
  "description": "Updated product sale",
  "transaction_type": "sale",
  "category": "Sales",
  "date": "2023-01-01T00:00:00Z",
  "user_id": "uuid",
  "account_id": "uuid",
  "created_at": "2023-01-01T00:00:00Z",
  "updated_at": "2023-01-01T00:00:00Z"
}
```

#### Delete a transaction

```
DELETE /api/transactions/{transaction_id}
```

**Headers:**
```
Authorization: Bearer your_access_token
```

**Response (204 No Content)**

### Accounts

#### Get all accounts

```
GET /api/accounts
```

**Headers:**
```
Authorization: Bearer your_access_token
```

**Response (200 OK):**
```json
[
  {
    "id": "uuid",
    "name": "Main Account",
    "balance": 1500.25,
    "user_id": "uuid",
    "created_at": "2023-01-01T00:00:00Z",
    "updated_at": "2023-01-01T00:00:00Z"
  }
]
```

#### Create an account

```
POST /api/accounts
```

**Headers:**
```
Authorization: Bearer your_access_token
```

**Request Body:**
```json
{
  "name": "Business Account",
  "balance": 0.0
}
```

**Response (201 Created):**
```json
{
  "id": "uuid",
  "name": "Business Account",
  "balance": 0.0,
  "user_id": "uuid",
  "created_at": "2023-01-01T00:00:00Z",
  "updated_at": "2023-01-01T00:00:00Z"
}
```

#### Get a specific account

```
GET /api/accounts/{account_id}
```

**Headers:**
```
Authorization: Bearer your_access_token
```

**Response (200 OK):**
```json
{
  "id": "uuid",
  "name": "Business Account",
  "balance": 1500.25,
  "user_id": "uuid",
  "created_at": "2023-01-01T00:00:00Z",
  "updated_at": "2023-01-01T00:00:00Z"
}
```

#### Get transactions for a specific account

```
GET /api/accounts/{account_id}/transactions
```

**Headers:**
```
Authorization: Bearer your_access_token
```

**Query Parameters:**
- `start_date` (optional): Filter by start date (ISO format)
- `end_date` (optional): Filter by end date (ISO format)
- `transaction_type` (optional): Filter by type (sale, expense, transfer, other)

**Response (200 OK):**
```json
[
  {
    "id": "uuid",
    "amount": 100.50,
    "description": "Product sale",
    "transaction_type": "sale",
    "category": "Sales",
    "date": "2023-01-01T00:00:00Z",
    "user_id": "uuid",
    "account_id": "uuid",
    "created_at": "2023-01-01T00:00:00Z",
    "updated_at": "2023-01-01T00:00:00Z"
  }
]
```

#### Update an account

```
PUT /api/accounts/{account_id}
```

**Headers:**
```
Authorization: Bearer your_access_token
```

**Request Body:**
```json
{
  "name": "Updated Business Account",
  "balance": 1500.25
}
```

**Response (200 OK):**
```json
{
  "id": "uuid",
  "name": "Updated Business Account",
  "balance": 1500.25,
  "user_id": "uuid",
  "created_at": "2023-01-01T00:00:00Z",
  "updated_at": "2023-01-01T00:00:00Z"
}
```

#### Delete an account

```
DELETE /api/accounts/{account_id}
```

**Headers:**
```
Authorization: Bearer your_access_token
```

**Query Parameters:**
- `transfer_to_account_id` (optional): UUID of account to transfer transactions and balance to

**Response (204 No Content)**

#### Get total balance

```
GET /api/accounts/balance
```

**Headers:**
```
Authorization: Bearer your_access_token
```

**Response (200 OK):**
```json
{
  "balance": 1500.25
}
```

#### Get account summary

```
GET /api/accounts/summary
```

**Headers:**
```
Authorization: Bearer your_access_token
```

**Query Parameters:**
- `period` (optional): Time period for summary (week, month, quarter, year). Default: month

**Response (200 OK):**
```json
{
  "total_balance": 1500.25,
  "income": 2000.00,
  "expenses": 500.00,
  "net_change": 1500.00,
  "accounts": [
    {
      "id": "uuid",
      "name": "Business Account",
      "balance": 1500.25,
      "income": 2000.00,
      "expenses": 500.00,
      "transaction_count": 10
    }
  ],
  "invoices_count": 5,
  "paid_invoices_count": 3,
  "period": "month"
}
```

### Invoices

#### Get all invoices

```
GET /api/invoices
```

**Headers:**
```
Authorization: Bearer your_access_token
```

**Query Parameters:**
- `status` (optional): Filter by status (draft, sent, paid, cancelled, overdue)
- `start_date` (optional): Filter by start date (ISO format)
- `end_date` (optional): Filter by end date (ISO format)
- `customer_name` (optional): Filter by customer name

**Response (200 OK):**
```json
[
  {
    "id": "uuid",
    "invoice_number": "INV-2023-01-1234",
    "customer_name": "John Doe",
    "customer_email": "john@example.com",
    "customer_address": "123 Main St, City",
    "issue_date": "2023-01-01T00:00:00Z",
    "due_date": "2023-01-31T00:00:00Z",
    "subtotal": 100.00,
    "tax_rate": 18.0,
    "tax_amount": 18.00,
    "total_amount": 118.00,
    "status": "paid",
    "notes": "Thank you for your business",
    "template": "default",
    "user_id": "uuid",
    "created_at": "2023-01-01T00:00:00Z",
    "updated_at": "2023-01-01T00:00:00Z",
    "items": [
      {
        "id": "uuid",
        "invoice_id": "uuid",
        "description": "Product A",
        "quantity": 2,
        "unit_price": 50.00,
        "amount": 100.00,
        "tax_included": true,
        "created_at": "2023-01-01T00:00:00Z",
        "updated_at": "2023-01-01T00:00:00Z"
      }
    ]
  }
]
```

#### Create an invoice

```
POST /api/invoices
```

**Headers:**
```
Authorization: Bearer your_access_token
```

**Query Parameters:**
- `create_transaction` (optional): Boolean to create a transaction for this invoice. Default: false

**Request Body:**
```json
{
  "invoice_number": "INV-2023-01-1234", // Optional, will be auto-generated if not provided
  "customer_name": "John Doe",
  "customer_email": "john@example.com",
  "customer_address": "123 Main St, City",
  "issue_date": "2023-01-01T00:00:00Z", // Optional, defaults to current date
  "due_date": "2023-01-31T00:00:00Z", // Optional, defaults to 30 days after issue date
  "tax_rate": 18.0, // Optional, defaults to 18.0 (GST)
  "status": "draft", // Optional, values: "draft", "sent", "paid", "cancelled", "overdue"
  "notes": "Thank you for your business",
  "template": "default", // Optional, values: "default", "professional", "simple", "detailed"
  "items": [
    {
      "description": "Product A",
      "quantity": 2,
      "unit_price": 50.00,
      "tax_included": true
    }
  ]
}
```

**Response (201 Created):**
```json
{
  "id": "uuid",
  "invoice_number": "INV-2023-01-1234",
  "customer_name": "John Doe",
  "customer_email": "john@example.com",
  "customer_address": "123 Main St, City",
  "issue_date": "2023-01-01T00:00:00Z",
  "due_date": "2023-01-31T00:00:00Z",
  "subtotal": 100.00,
  "tax_rate": 18.0,
  "tax_amount": 18.00,
  "total_amount": 118.00,
  "status": "draft",
  "notes": "Thank you for your business",
  "template": "default",
  "user_id": "uuid",
  "created_at": "2023-01-01T00:00:00Z",
  "updated_at": "2023-01-01T00:00:00Z",
  "items": [
    {
      "id": "uuid",
      "invoice_id": "uuid",
      "description": "Product A",
      "quantity": 2,
      "unit_price": 50.00,
      "amount": 100.00,
      "tax_included": true,
      "created_at": "2023-01-01T00:00:00Z",
      "updated_at": "2023-01-01T00:00:00Z"
    }
  ]
}
```

#### Get a specific invoice

```
GET /api/invoices/{invoice_id}
```

**Headers:**
```
Authorization: Bearer your_access_token
```

**Response (200 OK):**
```json
{
  "id": "uuid",
  "invoice_number": "INV-2023-01-1234",
  "customer_name": "John Doe",
  "customer_email": "john@example.com",
  "customer_address": "123 Main St, City",
  "issue_date": "2023-01-01T00:00:00Z",
  "due_date": "2023-01-31T00:00:00Z",
  "subtotal": 100.00,
  "tax_rate": 18.0,
  "tax_amount": 18.00,
  "total_amount": 118.00,
  "status": "draft",
  "notes": "Thank you for your business",
  "template": "default",
  "user_id": "uuid",
  "created_at": "2023-01-01T00:00:00Z",
  "updated_at": "2023-01-01T00:00:00Z",
  "items": [
    {
      "id": "uuid",
      "invoice_id": "uuid",
      "description": "Product A",
      "quantity": 2,
      "unit_price": 50.00,
      "amount": 100.00,
      "tax_included": true,
      "created_at": "2023-01-01T00:00:00Z",
      "updated_at": "2023-01-01T00:00:00Z"
    }
  ]
}
```

#### Update an invoice

```
PUT /api/invoices/{invoice_id}
```

**Headers:**
```
Authorization: Bearer your_access_token
```

**Request Body:**
```json
{
  "customer_name": "Updated Customer",
  "customer_email": "updated@example.com",
  "customer_address": "456 New St, City",
  "issue_date": "2023-01-02T00:00:00Z",
  "due_date": "2023-02-01T00:00:00Z",
  "tax_rate": 18.0,
  "status": "sent",
  "notes": "Updated notes",
  "template": "professional"
}
```

**Response (200 OK):**
```json
{
  "id": "uuid",
  "invoice_number": "INV-2023-01-1234",
  "customer_name": "Updated Customer",
  "customer_email": "updated@example.com",
  "customer_address": "456 New St, City",
  "issue_date": "2023-01-02T00:00:00Z",
  "due_date": "2023-02-01T00:00:00Z",
  "subtotal": 100.00,
  "tax_rate": 18.0,
  "tax_amount": 18.00,
  "total_amount": 118.00,
  "status": "sent",
  "notes": "Updated notes",
  "template": "professional",
  "user_id": "uuid",
  "created_at": "2023-01-01T00:00:00Z",
  "updated_at": "2023-01-02T00:00:00Z",
  "items": [
    {
      "id": "uuid",
      "invoice_id": "uuid",
      "description": "Product A",
      "quantity": 2,
      "unit_price": 50.00,
      "amount": 100.00,
      "tax_included": true,
      "created_at": "2023-01-01T00:00:00Z",
      "updated_at": "2023-01-01T00:00:00Z"
    }
  ]
}
```

#### Mark an invoice as paid

```
POST /api/invoices/{invoice_id}/mark-as-paid
```

**Headers:**
```
Authorization: Bearer your_access_token
```

**Response (200 OK):**
```json
{
  "id": "uuid",
  "invoice_number": "INV-2023-01-1234",
  "customer_name": "John Doe",
  "customer_email": "john@example.com",
  "customer_address": "123 Main St, City",
  "issue_date": "2023-01-01T00:00:00Z",
  "due_date": "2023-01-31T00:00:00Z",
  "subtotal": 100.00,
  "tax_rate": 18.0,
  "tax_amount": 18.00,
  "total_amount": 118.00,
  "status": "paid",
  "notes": "Thank you for your business",
  "template": "default",
  "user_id": "uuid",
  "created_at": "2023-01-01T00:00:00Z",
  "updated_at": "2023-01-02T00:00:00Z",
  "items": [
    {
      "id": "uuid",
      "invoice_id": "uuid",
      "description": "Product A",
      "quantity": 2,
      "unit_price": 50.00,
      "amount": 100.00,
      "tax_included": true,
      "created_at": "2023-01-01T00:00:00Z",
      "updated_at": "2023-01-01T00:00:00Z"
    }
  ]
}
```

#### Delete an invoice

```
DELETE /api/invoices/{invoice_id}
```

**Headers:**
```
Authorization: Bearer your_access_token
```

**Response (204 No Content)**

## Database Schema

The application uses the following database tables:

- **users**: Stores user information
- **blacklisted_tokens**: Stores invalidated JWT tokens
- **accounts**: Stores financial accounts
- **transactions**: Stores financial transactions
- **invoices**: Stores invoice information
- **invoice_items**: Stores line items for invoices

For detailed schema information, refer to the `database.sql` file.

## Component Integration

The API features automatic synchronization between different components:

### Transactions and Accounts
- When a transaction is created, the associated account balance is automatically updated
- If no account is specified when creating a transaction, a default account is used or created
- When a transaction is updated or deleted, the account balance is adjusted accordingly
- Transactions of type "sale" increase the account balance, while "expense" transactions decrease it

### Transactions and Invoices
- When a transaction with type "sale" is created, an invoice is automatically generated
- The invoice includes the transaction details and appropriate GST calculations

### Invoices and Accounts
- When an invoice is marked as paid, a corresponding transaction is created
- The account balance is updated based on the invoice amount
- The "mark-as-paid" endpoint provides a convenient way to handle payments

### Security and Authentication
- Token expiry has been configured for extremely long-lived sessions (100 years)
- Users are never automatically logged out of the application
- The `DISABLE_TOKEN_EXPIRY` flag ensures tokens remain valid permanently
- Blacklisted tokens are stored in both database and in-memory cache for fast validation

### Performance and Caching
- User data is cached with configurable TTL to minimize database lookups
- Token validation results are cached for faster API responses
- LRU cache strategy prevents memory leaks with high-volume usage
- Background processes periodically clean up expired cache entries

## Tax Calculation & Compliance

The API includes features for tax calculation and compliance, including:

- GST calculation for invoices
- Tax reporting for financial statements
- Compliance with tax laws and regulations

This ensures accurate tax reporting and compliance for all financial transactions.

### Calculate GST

```
GET /api/tax/gst
```

**Headers:**
```
Authorization: Bearer your_access_token
```

**Query Parameters:**
- `amount` (required): Amount for GST calculation
- `tax_included` (optional): Whether the amount already includes tax. Default: false
- `tax_rate` (optional): GST rate. Default: 18.0

**Response (200 OK):**
```json
{
  "original_amount": 100.00,
  "tax_rate": 18.0,
  "tax_amount": 18.00,
  "total_amount": 118.00,
  "tax_included": false,
  "breakdown": {
    "cgst": 9.00,
    "sgst": 9.00,
    "igst": 0.00
  }
}
```

#### Get Tax Filing Data

```
GET /api/tax/filing
```

**Headers:**
```
Authorization: Bearer your_access_token
```

**Query Parameters:**
- `start_date` (required): Start date for the filing period (YYYY-MM-DD)
- `end_date` (required): End date for the filing period (YYYY-MM-DD)
- `tax_type` (optional): Type of tax filing (gst, income_tax, other). Default: gst
- `period` (optional): Filing period type (monthly, quarterly, annually). Default: quarterly

**Response (200 OK):**
```json
{
  "summary": {
    "period_start": "2023-01-01",
    "period_end": "2023-03-31",
    "tax_type": "gst",
    "total_sales": 5000.00,
    "total_tax_collected": 900.00,
    "total_tax_paid": 300.00,
    "net_tax_liability": 600.00,
    "transaction_count": 25,
    "status": "draft"
  },
  "transactions": [
    {
      "transaction_id": "uuid",
      "date": "2023-01-15T10:30:00Z",
      "description": "Product sale",
      "amount": 1000.00,
      "tax_amount": 180.00,
      "transaction_type": "sale",
      "category": "Sales"
    }
  ]
}
```

#### Submit Tax Filing

```
POST /api/tax/submit
```

**Headers:**
```
Authorization: Bearer your_access_token
```

**Request Body:**
```json
{
  "filing_id": "uuid", // Optional, if not provided a new filing will be created
  "period_start": "2023-01-01",
  "period_end": "2023-03-31",
  "tax_type": "gst",
  "total_tax_liability": 600.00,
  "payment_reference": "UTR12345678", // Optional
  "notes": "Q1 2023 GST filing" // Optional
}
```

**Response (200 OK):**
```json
{
  "id": "uuid",
  "submission_date": "2023-04-15T14:30:00Z",
  "period_start": "2023-01-01",
  "period_end": "2023-03-31",
  "tax_type": "gst",
  "total_tax_liability": 600.00,
  "payment_reference": "UTR12345678",
  "confirmation_number": "GST7A9B2C3D4",
  "status": "submitted"
}
```

#### Get Tax Report

```
GET /api/tax/report
```

**Headers:**
```
Authorization: Bearer your_access_token
```

**Query Parameters:**
- `year` (required): Year for the tax report
- `tax_type` (optional): Type of tax to filter by (gst, income_tax, other)

**Response (200 OK):**
```json
{
  "year": 2023,
  "total_tax_paid": 2400.00,
  "filings": [
    {
      "id": "uuid",
      "period_start": "2023-01-01",
      "period_end": "2023-03-31",
      "tax_type": "gst",
      "total_tax_liability": 600.00,
      "submission_date": "2023-04-15T14:30:00Z",
      "status": "submitted"
    },
    {
      "id": "uuid",
      "period_start": "2023-04-01",
      "period_end": "2023-06-30",
      "tax_type": "gst",
      "total_tax_liability": 800.00,
      "submission_date": "2023-07-15T11:45:00Z",
      "status": "accepted"
    }
  ]
}
```

#### Calculate GST for a specific invoice

```
GET /api/tax/calculate-for-invoice/{invoice_id}
```

**Headers:**
```
Authorization: Bearer your_access_token
```

**Response (200 OK):**
```json
{
  "original_amount": 100.00,
  "tax_rate": 18.0,
  "tax_amount": 18.00,
  "total_amount": 118.00,
  "tax_included": false,
  "breakdown": {
    "cgst": 9.00,
    "sgst": 9.00,
    "igst": 0.00
  }
}
```

#### Auto-generate Tax Filing

```
GET /api/tax/filing/auto-generate
```

**Headers:**
```
Authorization: Bearer your_access_token
```

**Query Parameters:**
- `period` (optional): Filing period type (monthly, quarterly, annually). Default: quarterly
- `tax_type` (optional): Type of tax filing (gst, income_tax, other). Default: gst

**Response (200 OK):**
```json
{
  "summary": {
    "period_start": "2023-01-01",
    "period_end": "2023-03-31",
    "tax_type": "gst",
    "total_sales": 5000.00,
    "total_tax_collected": 900.00,
    "total_tax_paid": 300.00,
    "net_tax_liability": 600.00,
    "transaction_count": 25,
    "status": "draft"
  },
  "transactions": [
    {
      "transaction_id": "uuid",
      "date": "2023-01-15T10:30:00Z",
      "description": "Product sale",
      "amount": 1000.00,
      "tax_amount": 180.00,
      "transaction_type": "sale",
      "category": "Sales"
    }
  ]
}
```

#### Recalculate Invoice Taxes

```
POST /api/invoices/{invoice_id}/recalculate-taxes
```

**Headers:**
```
Authorization: Bearer your_access_token
```

**Query Parameters:**
- `tax_rate` (optional): New tax rate to apply. If not provided, uses the existing rate.

**Response (200 OK):**
```json
{
  "id": "uuid",
  "invoice_number": "INV-2023-01-1234",
  "customer_name": "John Doe",
  "customer_email": "john@example.com",
  "customer_address": "123 Main St, City",
  "issue_date": "2023-01-01T00:00:00Z",
  "due_date": "2023-01-31T00:00:00Z",
  "subtotal": 100.00,
  "tax_rate": 18.0,
  "tax_amount": 18.00,
  "total_amount": 118.00,
  "status": "draft",
  "notes": "Thank you for your business",
  "template": "default",
  "user_id": "uuid",
  "created_at": "2023-01-01T00:00:00Z",
  "updated_at": "2023-01-02T00:00:00Z",
  "items": [
    {
      "id": "uuid",
      "invoice_id": "uuid",
      "description": "Product A",
      "quantity": 2,
      "unit_price": 50.00,
      "amount": 100.00,
      "tax_included": true,
      "created_at": "2023-01-01T00:00:00Z",
      "updated_at": "2023-01-01T00:00:00Z"
    }
  ]
}
```