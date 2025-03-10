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