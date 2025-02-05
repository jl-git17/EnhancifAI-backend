-- Delete all records from stripe_invoices
DELETE FROM enhancifai.stripe_invoices;

DELETE FROM enhancifai.runs;

DELETE FROM enhancifai.prompt_improver_run_logs;

DELETE FROM enhancifai.users_token_usage;

DELETE FROM enhancifai.users_token_usage_pi;

DELETE FROM enhancifai.run_logs;

-- Delete all records from model_price_history


-- Reset the invoice_number_seq to start at 1
SELECT setval('enhancifai.invoice_number_seq', 1, false);

-- Truncate invoices table and reset its sequence
TRUNCATE TABLE enhancifai.stripe_invoices RESTART IDENTITY CASCADE;

-- Additionally, reset the invoice_number_seq if necessary
SELECT setval('enhancifai.invoice_number_seq', 1, false);

