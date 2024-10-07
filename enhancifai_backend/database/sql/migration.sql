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
