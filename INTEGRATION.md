# Renpay Component Integration

This document describes how the different components of the Renpay backend API work together to provide a seamless financial management experience.

## Transactions and Accounts

- When a transaction is created, the associated account balance is automatically updated
- If no account is specified when creating a transaction, a default account is used or created
- When a transaction is updated or deleted, the account balance is adjusted accordingly
- Transactions of type "sale" increase the account balance, while "expense" transactions decrease it

## Transactions and Invoices

- When a transaction with type "sale" is created, an invoice is automatically generated
- The invoice includes the transaction details and appropriate GST calculations

## Invoices and Accounts

- When an invoice is marked as paid, a corresponding transaction is created
- The account balance is updated based on the invoice amount
- The "mark-as-paid" endpoint provides a convenient way to handle payments

## Tax Calculation and Compliance

- GST calculations are automatically performed for all invoices
- When marking an invoice as paid, it can be automatically included in a tax filing
- Tax submissions create expense transactions to track tax payments
- Tax reports aggregate data from transactions and invoices for accurate reporting

## New Integration Points

### Invoice to Tax Integration

- The `POST /api/invoices/{invoice_id}/mark-as-paid` endpoint now accepts a `create_tax_filing` parameter
- When set to `true`, the invoice will be automatically included in the current quarter's tax filing
- If no tax filing exists for the current quarter, one will be created

### Tax to Transaction Integration

- The `POST /api/tax/submit` endpoint now creates a transaction for the tax payment
- This transaction is recorded as an expense with the category "Tax Payment"
- The account balance is updated to reflect the tax payment

### Additional Tax Calculation Endpoints

- `GET /api/tax/calculate-for-invoice/{invoice_id}` - Calculate GST for a specific invoice
- `GET /api/tax/filing/auto-generate` - Automatically generate a tax filing for the most recent period
- `POST /api/invoices/{invoice_id}/recalculate-taxes` - Recalculate taxes for an existing invoice

## Account Management

- When deleting an account, you can optionally transfer all transactions to another account
- The balance is also transferred to maintain accurate financial records
- The system prevents deleting the only account to ensure data integrity

## Security and Authentication

### Persistent Sessions

- Token expiry has been configured for extremely long-lived sessions (100 years)
- Users are never automatically logged out of the application
- The `DISABLE_TOKEN_EXPIRY` flag in the security configuration ensures tokens remain valid permanently
- Refresh tokens are also configured for the same duration

### Token Management

- Blacklisted tokens are stored in both the database and in-memory cache for fast validation
- The system maintains a central security configuration in the database
- Token revocation is explicitly managed through the `/api/auth/logout` endpoint
- Rate limiting has been significantly increased to support high volume API usage

## Performance Optimizations

### Caching Strategies

- User data is cached with configurable TTL (default: 5 minutes)
- Token validation results are cached to minimize database lookups
- A least-recently-used (LRU) cache strategy prevents memory leaks
- Background processes periodically clean up expired cache entries

### Database Optimization

- Specialized indexes for common query patterns
- Optimized SQL views for financial summaries and reporting
- Efficient schema design with appropriate constraints and relationships
- Support for high-volume transaction processing with minimal locking

### Model Optimizations

- Immutable Pydantic models with frozen=True for better caching
- Optimized JSON serialization for datetime and UUID objects
- Validators and root validators to ensure data integrity
- Pre-calculated fields to minimize computational overhead during request processing 