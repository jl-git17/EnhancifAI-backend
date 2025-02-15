           -- Clear all entries in stripe_subscriptions and subscription_payments tables
TRUNCATE TABLE enhancifai.stripe_subscriptions RESTART IDENTITY CASCADE;
TRUNCATE TABLE enhancifai.subscription_payments RESTART IDENTITY CASCADE;
