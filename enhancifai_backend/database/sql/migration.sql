ALTER TABLE enhancifai.runs
ADD COLUMN IF NOT EXISTS check_in FLOAT;

ALTER TABLE enhancifai.runs
ADD COLUMN IF NOT EXISTS cancelled BOOLEAN;

ALTER TABLE enhancifai.runs
ADD COLUMN IF NOT EXISTS source_filename VARCHAR;

CREATE INDEX IF NOT EXISTS idx_check_in ON enhancifai.runs (check_in);

CREATE INDEX IF NOT EXISTS idx_run_details ON enhancifai.runs USING GIN (run_details);

ALTER TABLE enhancifai.run_logs
ADD COLUMN IF NOT EXISTS batched BOOLEAN;

ALTER TABLE enhancifai.users
ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;

-- Table to store different account tiers
CREATE TABLE IF NOT EXISTS enhancifai.account_tiers (
    tier_id SERIAL PRIMARY KEY,
    tier_name VARCHAR(100) NOT NULL UNIQUE,
    max_tokens INT,
    max_rows INT,
    max_prompts INT,
    created_at TIMESTAMP DEFAULT now()
);

ALTER TABLE enhancifai.users
ADD COLUMN IF NOT EXISTS ai_consent TIMESTAMP;

-- Remove tier-related tables if they exist
DROP TABLE IF EXISTS enhancifai.account_tiers CASCADE;

-- Remove Stripe subscription-related columns from users table
ALTER TABLE enhancifai.users
    DROP COLUMN IF EXISTS stripe_subscription_id,
    DROP COLUMN IF EXISTS subscription_status,
    DROP COLUMN IF EXISTS subscription_start,
    DROP COLUMN IF EXISTS subscription_end;

ALTER TABLE enhancifai.users_token_usage
ADD COLUMN IF NOT EXISTS run_id INT REFERENCES enhancifai.runs(id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM pg_constraint 
        WHERE conname = 'unique_user_billing_period'
    ) THEN
        ALTER TABLE enhancifai.stripe_invoices
        ADD CONSTRAINT unique_user_billing_period 
        UNIQUE (user_id, billing_period_start, billing_period_end);
    END IF;
END $$;

ALTER TABLE enhancifai.users
ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(255);

CREATE TABLE IF NOT EXISTS enhancifai.model_price_history (
    model_name VARCHAR(100),
    price_per_token FLOAT NOT NULL,
    effective_date DATE NOT NULL,
    PRIMARY KEY (model_name, effective_date)
);

ALTER TABLE enhancifai.stripe_invoices
ADD COLUMN IF NOT EXISTS paid_at TIMESTAMP;

ALTER TABLE enhancifai.stripe_invoices
ALTER COLUMN amount TYPE FLOAT USING amount::FLOAT;

ALTER TABLE enhancifai.users
ADD COLUMN IF NOT EXISTS last_invoice_run_at TIMESTAMPTZ;

ALTER TABLE enhancifai.prompt_improver_run_logs
ADD COLUMN IF NOT EXISTS user_id INT REFERENCES enhancifai.users(user_id);

-- Migration script to enforce constraints

-- Step 1: Add a CHECK constraint to ensure effective_date is the first of the month
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'check_effective_date_first_of_month'
            AND conrelid = 'enhancifai.model_price_history'::regclass
    ) THEN
        ALTER TABLE enhancifai.model_price_history
            ADD CONSTRAINT check_effective_date_first_of_month
            CHECK (effective_date = DATE_TRUNC('month', effective_date));
    END IF;
END 
$$;

-- Ensure one price per model per month/year in model_price_history
ALTER TABLE enhancifai.model_price_history
    ADD CONSTRAINT unique_model_month
    UNIQUE (model_name, effective_date);

-- Step 2: Create or replace the function to prevent updates to past rates
CREATE OR REPLACE FUNCTION enhancifai.prevent_past_rate_updates()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.effective_date < DATE_TRUNC('month', CURRENT_DATE) THEN
        RAISE EXCEPTION 'Cannot update rates for past months';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Step 3: Create the trigger only if it does not already exist
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE t.tgname = 'trg_prevent_past_rate_updates'
          AND c.relname = 'model_price_history'
          AND n.nspname = 'enhancifai'
    ) THEN
        CREATE TRIGGER trg_prevent_past_rate_updates
        BEFORE UPDATE ON enhancifai.model_price_history
        FOR EACH ROW
        EXECUTE FUNCTION enhancifai.prevent_past_rate_updates();
    END IF;
END
$$ LANGUAGE plpgsql;

ALTER TABLE enhancifai.prompt_improver_run_logs
    DROP COLUMN IF EXISTS user_name;