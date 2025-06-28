-- Index to speed up queries filtering by user_id
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_stripe_subscriptions_user_id
    ON enhancifai.stripe_subscriptions(user_id);

-- Index to speed up queries filtering by status
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_stripe_subscriptions_status
    ON enhancifai.stripe_subscriptions(status);

-- Composite index for user_id and status for optimal performance on queries filtering both
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_stripe_subscriptions_user_id_status
    ON enhancifai.stripe_subscriptions(user_id, status);

-- Index on run_id for faster JOINs and queries filtering by run_id
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_run_logs_run_id 
    ON enhancifai.run_logs(run_id);

-- Index on user_name for quicker lookups based on user_name
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_run_logs_user_name 
    ON enhancifai.run_logs(user_name);

-- Index on engine_model for efficient queries filtering by engine_model
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_run_logs_engine_model 
    ON enhancifai.run_logs(engine_model);

-- Index on log_timestamp for improved performance on time-based queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_run_logs_log_timestamp 
    ON enhancifai.run_logs(log_timestamp);

-- Create indexes to optimize query performance
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_prompt_improver_engine_model 
    ON enhancifai.prompt_improver_run_logs(engine_model);

-- Index on log_timestamp for efficient time-based queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_prompt_improver_log_timestamp 
    ON enhancifai.prompt_improver_run_logs(log_timestamp);