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