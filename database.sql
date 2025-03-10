CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE blacklisted_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token TEXT UNIQUE NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    balance DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

CREATE TABLE IF NOT EXISTS inventory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    stock_level INTEGER NOT NULL,
    price NUMERIC(10, 2) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    amount DECIMAL(15, 2) NOT NULL,
    description TEXT NOT NULL,
    transaction_type TEXT NOT NULL,
    category TEXT,
    date TIMESTAMPTZ DEFAULT NOW(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id UUID REFERENCES accounts(id) ON DELETE SET NULL,
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    message TEXT NOT NULL,
    status TEXT DEFAULT 'unread',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_number TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    customer_email TEXT,
    customer_address TEXT,
    issue_date TIMESTAMPTZ DEFAULT NOW(),
    due_date TIMESTAMPTZ,
    subtotal DECIMAL(15, 2) NOT NULL,
    tax_rate DECIMAL(5, 2) DEFAULT 18.00, -- Default GST rate
    tax_amount DECIMAL(15, 2) NOT NULL,
    total_amount DECIMAL(15, 2) NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft', -- draft, sent, paid, cancelled, overdue
    notes TEXT,
    template TEXT DEFAULT 'default',
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

CREATE TABLE IF NOT EXISTS user_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    language TEXT DEFAULT 'en',
    theme TEXT DEFAULT 'light',
    alert_preferences JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS invoice_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id UUID NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    quantity DECIMAL(10, 2) NOT NULL DEFAULT 1.00,
    unit_price DECIMAL(15, 2) NOT NULL,
    amount DECIMAL(15, 2) NOT NULL,
    tax_included BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tax_filings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    tax_type TEXT NOT NULL DEFAULT 'gst',
    period_type TEXT NOT NULL DEFAULT 'quarterly',
    total_sales DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    total_tax_collected DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    total_tax_paid DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    net_tax_liability DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    transaction_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'draft', -- draft, submitted, accepted, rejected
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tax_submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filing_id UUID NOT NULL REFERENCES tax_filings(id) ON DELETE CASCADE,
    submission_date TIMESTAMPTZ DEFAULT NOW(),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    tax_type TEXT NOT NULL DEFAULT 'gst',
    total_tax_liability DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    payment_reference TEXT,
    confirmation_number TEXT,
    status TEXT NOT NULL DEFAULT 'pending', -- pending, submitted, accepted, rejected
    notes TEXT,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create an index on user_id for faster queries
CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);

-- Create an index on transaction_type for faster filtering
CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(transaction_type);

-- Create an index on date for faster date range queries
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);

-- Create an index on account_id for faster queries
CREATE INDEX IF NOT EXISTS idx_transactions_account_id ON transactions(account_id);

-- Create an index on user_id for accounts table
CREATE INDEX IF NOT EXISTS idx_accounts_user_id ON accounts(user_id);

-- Create an index on user_id for invoices table
CREATE INDEX IF NOT EXISTS idx_invoices_user_id ON invoices(user_id);

-- Create an index on invoice_number for faster lookups
CREATE INDEX IF NOT EXISTS idx_invoices_number ON invoices(invoice_number);

-- Create an index on status for filtering
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);

-- Create an index on invoice_id for invoice_items
CREATE INDEX IF NOT EXISTS idx_invoice_items_invoice_id ON invoice_items(invoice_id);

-- Create an index on user_id for tax_filings
CREATE INDEX IF NOT EXISTS idx_tax_filings_user_id ON tax_filings(user_id);

-- Create an index on period_start and period_end for tax_filings
CREATE INDEX IF NOT EXISTS idx_tax_filings_period ON tax_filings(period_start, period_end);

-- Create an index on status for tax_filings
CREATE INDEX IF NOT EXISTS idx_tax_filings_status ON tax_filings(status);

-- Create an index on user_id for tax_submissions
CREATE INDEX IF NOT EXISTS idx_tax_submissions_user_id ON tax_submissions(user_id);

-- Create an index on filing_id for tax_submissions
CREATE INDEX IF NOT EXISTS idx_tax_submissions_filing_id ON tax_submissions(filing_id);


CREATE TABLE IF NOT EXISTS sales_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    report_date DATE NOT NULL,
    total_sales NUMERIC(10, 2) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);



