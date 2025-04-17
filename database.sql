-- database.sql - Complete Schema for Renpay Backend

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Users Table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL, 
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    verification_token TEXT,
    last_login TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add updated_at trigger for users
CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_modtime
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION update_modified_column();

-- Blacklisted Tokens Table (for JWT token invalidation)
CREATE TABLE IF NOT EXISTS blacklisted_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token TEXT UNIQUE NOT NULL,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    token_type TEXT DEFAULT 'access',  -- 'access' or 'refresh'
    reason TEXT,
    device_info TEXT,
    ip_address TEXT
);

-- Create index on token for quick lookups during auth
CREATE INDEX IF NOT EXISTS idx_blacklisted_tokens_token ON blacklisted_tokens(token);
-- Create index on expires_at for cleanup jobs
CREATE INDEX IF NOT EXISTS idx_blacklisted_tokens_expires ON blacklisted_tokens(expires_at);
-- Create index on user_id for user-specific token queries
CREATE INDEX IF NOT EXISTS idx_blacklisted_tokens_user_id ON blacklisted_tokens(user_id);

-- Refresh Tokens Table (for long-lived sessions)
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token TEXT UNIQUE NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,
    device_info TEXT,
    ip_address TEXT,
    is_disabled BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires ON refresh_tokens(expires_at);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token ON refresh_tokens(token);

-- Security Configuration Table
CREATE TABLE IF NOT EXISTS security_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    access_token_expire_minutes INTEGER NOT NULL DEFAULT 52560000,
    refresh_token_expire_days INTEGER NOT NULL DEFAULT 36500,
    disable_token_expiry BOOLEAN DEFAULT TRUE,
    password_min_length INTEGER NOT NULL DEFAULT 8,
    failed_login_limit INTEGER NOT NULL DEFAULT 5,
    failed_login_window INTEGER NOT NULL DEFAULT 15,
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    updated_by UUID REFERENCES users(id) ON DELETE SET NULL
);

-- Accounts Table (Linked to Users)
CREATE TABLE IF NOT EXISTS accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL DEFAULT 'Default Account',
    description TEXT,
    account_type TEXT DEFAULT 'standard',
    balance DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    currency TEXT DEFAULT 'INR',
    is_default BOOLEAN DEFAULT TRUE,
    is_active BOOLEAN DEFAULT TRUE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add updated_at trigger for accounts
CREATE TRIGGER update_accounts_modtime
BEFORE UPDATE ON accounts
FOR EACH ROW EXECUTE FUNCTION update_modified_column();

-- Automatically Create Account When a User Registers
CREATE OR REPLACE FUNCTION create_user_account()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO accounts (user_id, balance, name, is_default) 
    VALUES (NEW.id, 0.00, 'Default Account', TRUE);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER create_account_after_user
AFTER INSERT ON users
FOR EACH ROW EXECUTE FUNCTION create_user_account();

-- Inventory Table
CREATE TABLE IF NOT EXISTS inventory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    sku TEXT,
    stock_level INTEGER NOT NULL DEFAULT 0,
    low_stock_threshold INTEGER DEFAULT 10,
    price NUMERIC(15, 2) NOT NULL,
    cost NUMERIC(15, 2),
    tax_rate DECIMAL(5, 2) DEFAULT 18.00,
    tax_included BOOLEAN DEFAULT TRUE,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add updated_at trigger for inventory
CREATE TRIGGER update_inventory_modtime
BEFORE UPDATE ON inventory
FOR EACH ROW EXECUTE FUNCTION update_modified_column();

-- Transactions Table
CREATE TABLE IF NOT EXISTS transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    amount DECIMAL(15, 2) NOT NULL,
    description TEXT NOT NULL,
    transaction_type TEXT NOT NULL CHECK (transaction_type IN ('sale', 'expense', 'transfer', 'other')),
    category TEXT,
    reference_number TEXT,
    payment_method TEXT,
    date TIMESTAMPTZ DEFAULT NOW(),
    notes TEXT,
    metadata JSONB,
    is_reconciled BOOLEAN DEFAULT FALSE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id UUID REFERENCES accounts(id) ON DELETE SET NULL,
    related_invoice_id UUID,
    related_tax_filing_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add updated_at trigger for transactions
CREATE TRIGGER update_transactions_modtime
BEFORE UPDATE ON transactions
FOR EACH ROW EXECUTE FUNCTION update_modified_column();

-- Notifications Table
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    notification_type TEXT DEFAULT 'info',
    status TEXT DEFAULT 'unread' CHECK (status IN ('read', 'unread', 'dismissed')),
    link TEXT,
    is_important BOOLEAN DEFAULT FALSE,
    scheduled_time TIMESTAMPTZ,
    expiry_time TIMESTAMPTZ,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add updated_at trigger for notifications
CREATE TRIGGER update_notifications_modtime
BEFORE UPDATE ON notifications
FOR EACH ROW EXECUTE FUNCTION update_modified_column();

-- Invoices Table
CREATE TABLE IF NOT EXISTS invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_number TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    customer_email TEXT,
    customer_address TEXT,
    customer_phone TEXT,
    customer_tax_id TEXT,
    issue_date TIMESTAMPTZ DEFAULT NOW(),
    due_date TIMESTAMPTZ,
    payment_date TIMESTAMPTZ,
    payment_reference TEXT,
    payment_method TEXT,
    subtotal DECIMAL(15, 2) NOT NULL,
    discount_amount DECIMAL(15, 2) DEFAULT 0.00,
    discount_type TEXT DEFAULT 'fixed', -- 'fixed' or 'percentage'
    tax_rate DECIMAL(5, 2) DEFAULT 18.00, -- Default GST rate
    tax_amount DECIMAL(15, 2) NOT NULL,
    total_amount DECIMAL(15, 2) NOT NULL,
    amount_paid DECIMAL(15, 2) DEFAULT 0.00,
    balance_due DECIMAL(15, 2), -- Calculated: total_amount - amount_paid
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'sent', 'paid', 'cancelled', 'overdue', 'partially_paid')),
    notes TEXT,
    terms TEXT,
    footer TEXT,
    currency TEXT DEFAULT 'INR',
    template TEXT DEFAULT 'default',
    is_recurring BOOLEAN DEFAULT FALSE,
    recurring_interval TEXT,
    next_invoice_date TIMESTAMPTZ,
    metadata JSONB,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add updated_at trigger for invoices
CREATE TRIGGER update_invoices_modtime
BEFORE UPDATE ON invoices
FOR EACH ROW EXECUTE FUNCTION update_modified_column();

-- Invoice Items Table
CREATE TABLE IF NOT EXISTS invoice_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id UUID NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    item_name TEXT NOT NULL,
    description TEXT NOT NULL,
    quantity DECIMAL(10, 2) NOT NULL DEFAULT 1.00,
    unit TEXT DEFAULT 'item',
    unit_price DECIMAL(15, 2) NOT NULL,
    amount DECIMAL(15, 2) NOT NULL,
    discount_amount DECIMAL(15, 2) DEFAULT 0.00,
    tax_rate DECIMAL(5, 2) DEFAULT 18.00,
    tax_amount DECIMAL(15, 2) DEFAULT 0.00,
    tax_included BOOLEAN DEFAULT TRUE,
    inventory_item_id UUID REFERENCES inventory(id) ON DELETE SET NULL,
    sort_order INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add updated_at trigger for invoice_items
CREATE TRIGGER update_invoice_items_modtime
BEFORE UPDATE ON invoice_items
FOR EACH ROW EXECUTE FUNCTION update_modified_column();

-- User Preferences Table
CREATE TABLE IF NOT EXISTS user_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    language TEXT DEFAULT 'en',
    theme TEXT DEFAULT 'light',
    notification_email BOOLEAN DEFAULT TRUE,
    notification_app BOOLEAN DEFAULT TRUE,
    default_currency TEXT DEFAULT 'INR',
    default_tax_rate DECIMAL(5, 2) DEFAULT 18.00,
    date_format TEXT DEFAULT 'yyyy-MM-dd',
    time_format TEXT DEFAULT 'HH:mm',
    timezone TEXT DEFAULT 'Asia/Kolkata',
    sidebar_collapsed BOOLEAN DEFAULT FALSE,
    show_help_tips BOOLEAN DEFAULT TRUE,
    default_view_mode TEXT DEFAULT 'list',
    default_dashboard TEXT DEFAULT 'overview',
    default_account_id UUID REFERENCES accounts(id) ON DELETE SET NULL,
    custom_fields JSONB,
    alert_preferences JSONB,
    invoice_settings JSONB,
    tax_settings JSONB,
    auto_tax_filing BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_user_prefs UNIQUE (user_id)
);

-- Add updated_at trigger for user_preferences
CREATE TRIGGER update_user_preferences_modtime
BEFORE UPDATE ON user_preferences
FOR EACH ROW EXECUTE FUNCTION update_modified_column();

-- Tax Filings Table
CREATE TABLE IF NOT EXISTS tax_filings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    tax_type TEXT NOT NULL DEFAULT 'gst' CHECK (tax_type IN ('gst', 'income_tax', 'other')),
    period_type TEXT NOT NULL DEFAULT 'quarterly' CHECK (period_type IN ('monthly', 'quarterly', 'annually')),
    total_sales DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    total_tax_collected DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    total_tax_paid DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    net_tax_liability DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    transaction_count INTEGER NOT NULL DEFAULT 0,
    filing_due_date DATE,
    filing_date DATE,
    auto_generated BOOLEAN DEFAULT FALSE,
    submitted_to_government BOOLEAN DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'submitted', 'accepted', 'rejected', 'pending')),
    notes TEXT,
    reference_number TEXT,
    documents JSONB,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add updated_at trigger for tax_filings
CREATE TRIGGER update_tax_filings_modtime
BEFORE UPDATE ON tax_filings
FOR EACH ROW EXECUTE FUNCTION update_modified_column();

-- Tax Filing Items Table (invoices/transactions included in a tax filing)
CREATE TABLE IF NOT EXISTS tax_filing_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filing_id UUID NOT NULL REFERENCES tax_filings(id) ON DELETE CASCADE,
    invoice_id UUID REFERENCES invoices(id) ON DELETE SET NULL,
    transaction_id UUID REFERENCES transactions(id) ON DELETE SET NULL,
    amount DECIMAL(15, 2) NOT NULL,
    tax_amount DECIMAL(15, 2) NOT NULL,
    type TEXT CHECK (type IN ('sale', 'purchase', 'expense', 'adjustment')),
    included_on TIMESTAMPTZ DEFAULT NOW(),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tax_filing_items_filing ON tax_filing_items(filing_id);
CREATE INDEX IF NOT EXISTS idx_tax_filing_items_invoice ON tax_filing_items(invoice_id);
CREATE INDEX IF NOT EXISTS idx_tax_filing_items_transaction ON tax_filing_items(transaction_id);

-- Tax Submissions Table
CREATE TABLE IF NOT EXISTS tax_submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filing_id UUID NOT NULL REFERENCES tax_filings(id) ON DELETE CASCADE,
    submission_date TIMESTAMPTZ DEFAULT NOW(),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    tax_type TEXT NOT NULL DEFAULT 'gst' CHECK (tax_type IN ('gst', 'income_tax', 'other')),
    total_tax_liability DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    payment_amount DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    payment_date TIMESTAMPTZ,
    payment_reference TEXT,
    payment_method TEXT,
    confirmation_number TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'submitted', 'accepted', 'rejected', 'payment_pending', 'payment_complete')),
    submitted_by TEXT,
    submission_method TEXT DEFAULT 'online',
    receipt_document TEXT,
    notes TEXT,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add updated_at trigger for tax_submissions
CREATE TRIGGER update_tax_submissions_modtime
BEFORE UPDATE ON tax_submissions
FOR EACH ROW EXECUTE FUNCTION update_modified_column();

-- Sales Reports Table
CREATE TABLE IF NOT EXISTS sales_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    report_type TEXT NOT NULL DEFAULT 'daily' CHECK (report_type IN ('daily', 'weekly', 'monthly', 'quarterly', 'yearly', 'custom')),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    report_date DATE NOT NULL,
    total_sales DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    total_tax DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    total_invoices INTEGER DEFAULT 0,
    total_paid DECIMAL(15, 2) DEFAULT 0.00,
    total_outstanding DECIMAL(15, 2) DEFAULT 0.00,
    top_customers JSONB,
    top_products JSONB,
    sales_by_category JSONB,
    report_data JSONB,
    is_auto_generated BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Expense Categories Table
CREATE TABLE IF NOT EXISTS expense_categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    is_tax_deductible BOOLEAN DEFAULT FALSE,
    tax_category TEXT,
    parent_category_id UUID REFERENCES expense_categories(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_category_name_per_user UNIQUE (user_id, name)
);

-- Add updated_at trigger for expense_categories
CREATE TRIGGER update_expense_categories_modtime
BEFORE UPDATE ON expense_categories
FOR EACH ROW EXECUTE FUNCTION update_modified_column();

-- Customer Table
CREATE TABLE IF NOT EXISTS customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    address TEXT,
    city TEXT,
    state TEXT,
    postal_code TEXT,
    country TEXT DEFAULT 'India',
    tax_id TEXT,
    notes TEXT,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    total_sales DECIMAL(15, 2) DEFAULT 0.00,
    outstanding_balance DECIMAL(15, 2) DEFAULT 0.00,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add updated_at trigger for customers
CREATE TRIGGER update_customers_modtime
BEFORE UPDATE ON customers
FOR EACH ROW EXECUTE FUNCTION update_modified_column();

-- API Keys Table (for integrations)
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    api_key TEXT NOT NULL UNIQUE,
    permissions JSONB,
    last_used TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add updated_at trigger for api_keys
CREATE TRIGGER update_api_keys_modtime
BEFORE UPDATE ON api_keys
FOR EACH ROW EXECUTE FUNCTION update_modified_column();

-- Audit Logs Table
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id UUID,
    previous_state JSONB,
    new_state JSONB,
    ip_address TEXT,
    user_agent TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Rate Limiting Table
CREATE TABLE IF NOT EXISTS rate_limits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ip_address TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    request_count INTEGER DEFAULT 1,
    first_request_at TIMESTAMPTZ DEFAULT NOW(),
    last_request_at TIMESTAMPTZ DEFAULT NOW(),
    window_size INTEGER DEFAULT 60,  -- Window size in seconds
    max_requests INTEGER DEFAULT 1000000,  -- Maximum allowed requests per window
    CONSTRAINT unique_ip_endpoint_user UNIQUE (ip_address, endpoint, user_id)
);

-- Create indexes for optimized queries
CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(transaction_type);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_transactions_account_id ON transactions(account_id);
CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category);
CREATE INDEX IF NOT EXISTS idx_accounts_user_id ON accounts(user_id);
CREATE INDEX IF NOT EXISTS idx_accounts_is_default ON accounts(is_default);
CREATE INDEX IF NOT EXISTS idx_invoices_user_id ON invoices(user_id);
CREATE INDEX IF NOT EXISTS idx_invoices_number ON invoices(invoice_number);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_invoices_customer ON invoices(customer_name, customer_email);
CREATE INDEX IF NOT EXISTS idx_invoices_dates ON invoices(issue_date, due_date);
CREATE INDEX IF NOT EXISTS idx_invoice_items_invoice_id ON invoice_items(invoice_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_status ON notifications(status);
CREATE INDEX IF NOT EXISTS idx_tax_filings_user_id ON tax_filings(user_id);
CREATE INDEX IF NOT EXISTS idx_tax_filings_period ON tax_filings(period_start, period_end);
CREATE INDEX IF NOT EXISTS idx_tax_filings_status ON tax_filings(status);
CREATE INDEX IF NOT EXISTS idx_tax_filings_tax_type ON tax_filings(tax_type);
CREATE INDEX IF NOT EXISTS idx_tax_submissions_user_id ON tax_submissions(user_id);
CREATE INDEX IF NOT EXISTS idx_tax_submissions_filing_id ON tax_submissions(filing_id);
CREATE INDEX IF NOT EXISTS idx_tax_submissions_status ON tax_submissions(status);
CREATE INDEX IF NOT EXISTS idx_inventory_user_id ON inventory(user_id);
CREATE INDEX IF NOT EXISTS idx_inventory_name_sku ON inventory(name, sku);
CREATE INDEX IF NOT EXISTS idx_customers_user_id ON customers(user_id);
CREATE INDEX IF NOT EXISTS idx_customers_name_email ON customers(name, email);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_rate_limits_ip ON rate_limits(ip_address);
CREATE INDEX IF NOT EXISTS idx_rate_limits_endpoint ON rate_limits(endpoint);
CREATE INDEX IF NOT EXISTS idx_rate_limits_user_id ON rate_limits(user_id);
CREATE INDEX IF NOT EXISTS idx_rate_limits_last_request ON rate_limits(last_request_at);

-- Create views for common queries
CREATE OR REPLACE VIEW invoice_summary AS
SELECT 
    i.user_id,
    DATE_TRUNC('month', i.issue_date) AS month,
    COUNT(*) AS invoice_count,
    SUM(i.total_amount) AS total_amount,
    SUM(i.tax_amount) AS total_tax,
    SUM(CASE WHEN i.status = 'paid' THEN i.total_amount ELSE 0 END) AS paid_amount,
    SUM(CASE WHEN i.status = 'overdue' THEN i.total_amount ELSE 0 END) AS overdue_amount
FROM 
    invoices i
GROUP BY 
    i.user_id, DATE_TRUNC('month', i.issue_date);

-- Financial snapshot view
CREATE OR REPLACE VIEW financial_snapshot AS
SELECT 
    u.id AS user_id,
    COALESCE(SUM(a.balance), 0) AS total_balance,
    COALESCE(sales.total_sales, 0) AS total_sales,
    COALESCE(expenses.total_expenses, 0) AS total_expenses,
    COALESCE(inv.total_outstanding, 0) AS outstanding_invoices,
    COALESCE(tax.tax_liability, 0) AS tax_liability
FROM 
    users u
LEFT JOIN 
    accounts a ON u.id = a.user_id
LEFT JOIN (
    SELECT user_id, SUM(amount) AS total_sales 
    FROM transactions 
    WHERE transaction_type = 'sale' 
    GROUP BY user_id
) sales ON u.id = sales.user_id
LEFT JOIN (
    SELECT user_id, SUM(amount) AS total_expenses 
    FROM transactions 
    WHERE transaction_type = 'expense' 
    GROUP BY user_id
) expenses ON u.id = expenses.user_id
LEFT JOIN (
    SELECT user_id, SUM(CASE WHEN status != 'paid' AND status != 'cancelled' THEN balance_due ELSE 0 END) AS total_outstanding
    FROM invoices
    GROUP BY user_id
) inv ON u.id = inv.user_id
LEFT JOIN (
    SELECT user_id, SUM(net_tax_liability) AS tax_liability
    FROM tax_filings
    WHERE status != 'submitted' AND status != 'accepted'
    GROUP BY user_id
) tax ON u.id = tax.user_id
GROUP BY u.id, sales.total_sales, expenses.total_expenses, inv.total_outstanding, tax.tax_liability;

-- Default security configuration
INSERT INTO security_config (access_token_expire_minutes, refresh_token_expire_days, disable_token_expiry)
VALUES (52560000, 36500, true)
ON CONFLICT DO NOTHING;
