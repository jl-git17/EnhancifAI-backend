
CREATE TABLE IF NOT EXISTS enhancifai.users (
    user_id SERIAL PRIMARY KEY,
    email VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(100),
    google_oauth_token TEXT,
    email_verified BOOLEAN DEFAULT false,
    password_hash VARCHAR,
    stripe_customer_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS enhancifai.users_sessions (
    session_id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES enhancifai.users(user_id),
    token TEXT NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT now() NOT NULL
);

CREATE TABLE IF NOT EXISTS enhancifai.users_token_usage (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES enhancifai.users(user_id),
    model VARCHAR,
    tokens INT,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS enhancifai.users_token_usage_pi (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES enhancifai.users(user_id),
    model VARCHAR,
    tokens INT,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS enhancifai.stripe_invoices (
    invoice_id SERIAL PRIMARY KEY,
    user_id INT REFERENCES enhancifai.users(user_id),
    amount INT NOT NULL,
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT now(),
    billing_period_start DATE,
    billing_period_end DATE,
    metadata JSONB
);

-- Step 1: Add the invoice_number column if it doesn't exist
ALTER TABLE enhancifai.stripe_invoices
ADD COLUMN IF NOT EXISTS invoice_number VARCHAR(20) UNIQUE NOT NULL DEFAULT '';

-- Step 2: Create the invoice_number_seq sequence if it doesn't exist
CREATE SEQUENCE IF NOT EXISTS enhancifai.invoice_number_seq START 1;

-- Step 3: Create the generate_invoice_number trigger function if it doesn't exist
CREATE OR REPLACE FUNCTION enhancifai.generate_invoice_number()
RETURNS TRIGGER AS $$
BEGIN
    -- Reset sequence if it's a new month
    IF to_char(NEW.created_at, 'YYYYMM') <> to_char(current_date, 'YYYYMM') THEN
        PERFORM setval('enhancifai.invoice_number_seq', 1, false);
    END IF;

    -- Generate the invoice_number
    NEW.invoice_number := CONCAT(
        'INV-',
        TO_CHAR(NEW.created_at, 'YYYYMM'),
        '-',
        LPAD(nextval('enhancifai.invoice_number_seq')::text, 4, '0')
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Step 4: Create the trg_generate_invoice_number trigger if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'trg_generate_invoice_number'
    ) THEN
        CREATE TRIGGER trg_generate_invoice_number
        BEFORE INSERT ON enhancifai.stripe_invoices
        FOR EACH ROW
        EXECUTE FUNCTION enhancifai.generate_invoice_number();
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS enhancifai.google_sheets_credentials (
    user_id INT REFERENCES enhancifai.users(user_id) UNIQUE,
    credentials BYTEA NOT NULL,
    updated_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS enhancifai.google_oauth_state (
    user_id INT REFERENCES enhancifai.users(user_id),
    state VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT now(),
    PRIMARY KEY (user_id, state)
);

CREATE TABLE IF NOT EXISTS enhancifai.user_register_tokens (
    email VARCHAR(100) NOT NULL,
    token VARCHAR(64) NOT NULL,
    redeemed BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS enhancifai.user_login_tokens (
    email VARCHAR(100) NOT NULL,
    token VARCHAR(64) NOT NULL,
    redeemed BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS enhancifai.user_password_reset_tokens (
    email VARCHAR(100) NOT NULL,
    token VARCHAR(64) NOT NULL,
    redeemed BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS enhancifai.login_events (
    user_id INT REFERENCES enhancifai.users(user_id),
    logged_in_at TIMESTAMP DEFAULT now()
);


-- Create an ENUM type for source_type values
DO $$ BEGIN
    CREATE TYPE source_type AS ENUM ('csv', 'excel', 'google_sheets');
EXCEPTION
    WHEN duplicate_object THEN null; -- Avoid error if the type already exists
END $$;

CREATE TABLE IF NOT EXISTS enhancifai.runs (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES enhancifai.users(user_id),
    source_type source_type, -- Changed from ENUM to VARCHAR for simplicity
    run_details JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT now(),
    check_in FLOAT,
    cancelled BOOLEAN,
    source_filename VARCHAR
);

CREATE TABLE IF NOT EXISTS enhancifai.runs_calls (
    id SERIAL PRIMARY KEY,
    run_id INT REFERENCES enhancifai.runs(id),
    prompt TEXT,
    tokens_used INT
);

CREATE TABLE IF NOT EXISTS enhancifai.run_logs (
    log_id SERIAL PRIMARY KEY,
    run_id INT REFERENCES enhancifai.runs(id),
    user_name VARCHAR(100),
    engine_model VARCHAR(50),
    log_timestamp TIMESTAMP DEFAULT now(),
    time_elapsed FLOAT,
    num_rows_processed INT,
    num_rows_in_file INT,
    num_prompts INT,
    num_tokens INT,
    errors TEXT,
    filename VARCHAR,
    overflow BOOLEAN,
    batched BOOLEAN
);

-- Index on run_id for faster JOINs and queries filtering by run_id
CREATE INDEX IF NOT EXISTS idx_run_logs_run_id 
    ON enhancifai.run_logs(run_id);

-- Index on user_name for quicker lookups based on user_name
CREATE INDEX IF NOT EXISTS idx_run_logs_user_name 
    ON enhancifai.run_logs(user_name);

-- Index on engine_model for efficient queries filtering by engine_model
CREATE INDEX IF NOT EXISTS idx_run_logs_engine_model 
    ON enhancifai.run_logs(engine_model);

-- Index on log_timestamp for improved performance on time-based queries
CREATE INDEX IF NOT EXISTS idx_run_logs_log_timestamp 
    ON enhancifai.run_logs(log_timestamp);


CREATE TABLE IF NOT EXISTS enhancifai.prompt_improver_run_logs (
    log_id SERIAL PRIMARY KEY,
    user_name VARCHAR(100) NOT NULL,
    engine_model VARCHAR(50) NOT NULL,
    log_timestamp TIMESTAMP DEFAULT NOW(),
    time_elapsed FLOAT CHECK (time_elapsed >= 0),
    num_prompts INT CHECK (num_prompts >= 0),
    num_tokens INT CHECK (num_tokens >= 0),
    errors TEXT
);

-- Create indexes to optimize query performance
CREATE INDEX IF NOT EXISTS idx_prompt_improver_user_name 
    ON enhancifai.prompt_improver_run_logs(user_name);

CREATE INDEX IF NOT EXISTS idx_prompt_improver_engine_model 
    ON enhancifai.prompt_improver_run_logs(engine_model);

CREATE INDEX IF NOT EXISTS idx_prompt_improver_log_timestamp 
    ON enhancifai.prompt_improver_run_logs(log_timestamp);

CREATE TABLE IF NOT EXISTS enhancifai.prompts (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES enhancifai.users(user_id),
    prompt TEXT NOT NULL,
    ai_engine VARCHAR(50),
    version INT NOT NULL,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS enhancifai.users_additional_credits (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES enhancifai.users(user_id),
    credits INT NOT NULL,
    created_at TIMESTAMP DEFAULT now() NOT NULL
);

CREATE TABLE IF NOT EXISTS enhancifai.model_prices (
    model_name VARCHAR(100) PRIMARY KEY,
    price_per_token FLOAT NOT NULL,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);
