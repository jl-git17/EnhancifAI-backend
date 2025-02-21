TRUNCATE TABLE enhancifai.stripe_invoices
RESTART IDENTITY CASCADE;
TRUNCATE TABLE enhancifai.internal_invoices
RESTART IDENTITY CASCADE;


-- Query to delete stripe_customer_id for all users by setting it to NULL
UPDATE enhancifai.users SET stripe_customer_id = NULL;


SELECT setval('enhancifai.invoice_number_seq', 1, false);

--,
               --enhancifai.runs,
               --enhancifai.prompt_improver_run_logs,
               --enhancifai.users_token_usage,
               --enhancifai.users_token_usage_pi,
               --enhancifai.run_logs


-- Reset the invoice_number_seq to start at 1
