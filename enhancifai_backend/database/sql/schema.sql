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
    is_paid_usage BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT now()
);
ALTER TABLE enhancifai.users_token_usage
ADD COLUMN IF NOT EXISTS is_paid_usage BOOLEAN DEFAULT false;

CREATE TABLE IF NOT EXISTS enhancifai.users_token_usage_pi (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES enhancifai.users(user_id),
    model VARCHAR,
    tokens INT,
    is_paid_usage BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT now()
);
ALTER TABLE enhancifai.users_token_usage_pi
ADD COLUMN IF NOT EXISTS is_paid_usage BOOLEAN DEFAULT false;

CREATE TABLE IF NOT EXISTS enhancifai.internal_invoices (
    id SERIAL PRIMARY KEY,
    invoice_id VARCHAR(25) UNIQUE NOT NULL,
    user_id INT REFERENCES enhancifai.users(user_id),
    amount FLOAT NOT NULL,
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT now(),
    email_sent BOOLEAN DEFAULT false,
    billing_period_start DATE,
    billing_period_end DATE,
    metadata JSONB,
    paid_at TIMESTAMP
);

-- Create sequence if it does not exist
CREATE SEQUENCE IF NOT EXISTS enhancifai.invoice_number_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

-- Create or replace function
CREATE OR REPLACE FUNCTION enhancifai.generate_invoice_number()
RETURNS TRIGGER AS $func$
BEGIN
    -- Reset the sequence at the start of a new month
    IF to_char(NEW.created_at, 'YYYYMM') <> to_char(current_date, 'YYYYMM') THEN
        PERFORM setval('enhancifai.invoice_number_seq', 1, false);
    END IF;

    -- Assign the invoice_id using the specified format
    NEW.invoice_id := CONCAT(
        'INV-',
        TO_CHAR(NEW.created_at, 'YYYYMM'),
        '-',
        LPAD(nextval('enhancifai.invoice_number_seq')::text, 9, '0') -- Nine-digit sequence
    );
    RETURN NEW;
END;
$func$ LANGUAGE plpgsql;

-- Create trigger if it does not exist
DO $do$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE t.tgname = 'trg_generate_invoice_number'
          AND c.relname = 'internal_invoices'
          AND n.nspname = 'enhancifai'
    ) THEN
        CREATE TRIGGER trg_generate_invoice_number
        BEFORE INSERT ON enhancifai.internal_invoices
        FOR EACH ROW
        EXECUTE FUNCTION enhancifai.generate_invoice_number();
    END IF;
END
$do$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS enhancifai.stripe_invoices (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES enhancifai.users(user_id),
    invoice_id VARCHAR(25) UNIQUE NOT NULL REFERENCES enhancifai.internal_invoices(invoice_id),
    amount FLOAT NOT NULL,
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT now()
);

-- For failed invoice payments: add retry attempt count and scheduled retry/cutoff timestamps
ALTER TABLE enhancifai.stripe_invoices
    ADD COLUMN IF NOT EXISTS retry_attempt INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS first_retry_at TIMESTAMP,   -- scheduled 1 day after failure
    ADD COLUMN IF NOT EXISTS second_retry_at TIMESTAMP,  -- scheduled 2 days after failure
    ADD COLUMN IF NOT EXISTS service_cutoff_at TIMESTAMP; -- cutoff scheduled after 2 weeks

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
    errors TEXT,
    filename VARCHAR,
    overflow BOOLEAN,
    batched BOOLEAN,
    input_tokens INT,
    output_tokens INT
);



CREATE TABLE IF NOT EXISTS enhancifai.prompt_improver_run_logs (
    log_id SERIAL PRIMARY KEY,
    engine_model VARCHAR(50) NOT NULL,
    log_timestamp TIMESTAMP DEFAULT NOW(),
    time_elapsed FLOAT CHECK (time_elapsed >= 0),
    num_prompts INT CHECK (num_prompts >= 0),
    input_tokens INT CHECK (input_tokens >= 0),
    output_tokens INT CHECK (output_tokens >= 0),
    errors TEXT
);


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

CREATE TABLE IF NOT EXISTS enhancifai.model_pricing (
    model_name VARCHAR(100) NOT NULL,
    month INT NOT NULL,
    year INT NOT NULL,
    price FLOAT NOT NULL,
    PRIMARY KEY (model_name, month, year)
);

ALTER TABLE enhancifai.run_logs
    ADD COLUMN IF NOT EXISTS input_tokens INT,
    ADD COLUMN IF NOT EXISTS output_tokens INT,
    DROP COLUMN IF EXISTS num_tokens;

ALTER TABLE enhancifai.prompt_improver_run_logs
    ADD COLUMN IF NOT EXISTS input_tokens INT,
    ADD COLUMN IF NOT EXISTS output_tokens INT,
    DROP COLUMN IF EXISTS num_tokens;

CREATE TABLE IF NOT EXISTS enhancifai.stripe_subscriptions (
    subscription_id VARCHAR(255) PRIMARY KEY,
    user_id INT REFERENCES enhancifai.users(user_id),
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT now(),
    current_period_start TIMESTAMP,
    current_period_end TIMESTAMP
);

-- For failed subscription payments: add payment retry attempt count and scheduled retry/cutoff timestamps
ALTER TABLE enhancifai.stripe_subscriptions
    ADD COLUMN IF NOT EXISTS payment_retry_attempt INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS first_payment_retry_at TIMESTAMP,  -- scheduled after 2 days
    ADD COLUMN IF NOT EXISTS second_payment_retry_at TIMESTAMP, -- scheduled second retry within 2 weeks
    ADD COLUMN IF NOT EXISTS service_cutoff_at TIMESTAMP;         -- cutoff after 2 weeks

CREATE TABLE IF NOT EXISTS enhancifai.subscription_payments (
    payment_id VARCHAR(255) PRIMARY KEY,
    subscription_id VARCHAR(255) REFERENCES enhancifai.stripe_subscriptions(subscription_id),
    amount FLOAT NOT NULL,
    currency VARCHAR(10) NOT NULL,
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT now(),
    paid_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS enhancifai.use_cases_free (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    thumbnail BYTEA,
    sample_input_file_csv BYTEA,
    sample_input_file_excel BYTEA,
    prompt_config_file BYTEA,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

DROP TABLE IF EXISTS enhancifai.demo_usage_logs; -- Temp
CREATE TABLE IF NOT EXISTS enhancifai.demo_usage_logs (
    id SERIAL PRIMARY KEY,
    ip_address VARCHAR(45),
    use_case_id INT,
    model_name VARCHAR(100),
    tokens_used INT,
    created_at TIMESTAMP DEFAULT now()
);

-- Settings for public demo (model_default, model_fallback)
CREATE TABLE IF NOT EXISTS enhancifai.demo_settings (
    id SERIAL PRIMARY KEY,
    model_default VARCHAR(100),
    model_fallback VARCHAR(100),
    updated_at TIMESTAMP DEFAULT now()
);

-- Insert default row if not exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM enhancifai.demo_settings) THEN
        INSERT INTO enhancifai.demo_settings (model_default, model_fallback) VALUES ('', '');
    END IF;
END $$;

-- Table to record each demo run
CREATE TABLE IF NOT EXISTS enhancifai.demo_runs (
    id SERIAL PRIMARY KEY,
    use_case_id INT REFERENCES enhancifai.use_cases_free(id),
    session_id VARCHAR(64),
    ip_address VARCHAR(45),
    source_type VARCHAR(20), -- e.g., 'csv', 'excel'
    source_filename VARCHAR,
    run_details JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT now(),
    check_in FLOAT,
    cancelled BOOLEAN
);

-- Table to record each prompt call within a demo run
CREATE TABLE IF NOT EXISTS enhancifai.demo_run_calls (
    id SERIAL PRIMARY KEY,
    demo_run_id INT REFERENCES enhancifai.demo_runs(id),
    prompt TEXT,
    tokens_used INT
);

CREATE TABLE IF NOT EXISTS enhancifai.global_settings (
    active PRIMARY KEY BOOLEAN DEFAULT TRUE,
    openai_temperature FLOAT,
    openai_temperature_batched FLOAT
);
INSERT INTO enhancifai.global_settings (active, openai_temperature, openai_temperature_batched)
VALUES (TRUE, 0.5, 0.5)
ON CONFLICT (active) DO NOTHING;
