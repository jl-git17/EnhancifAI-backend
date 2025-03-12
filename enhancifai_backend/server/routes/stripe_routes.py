from fastapi import APIRouter, Request, HTTPException, Header
from fastapi.responses import JSONResponse
import stripe

from enhancifai_backend.config import settings
from enhancifai_backend.database.handlers.billing import BillingDbCore
from enhancifai_backend.database.handlers.stripe import StripeDbCore
from enhancifai_backend.database.handlers.users import UsersDbCore

# Initialize Stripe
stripe.api_key = settings.stripe_secret_key

router = APIRouter()

@router.post("/stripe/webhook", tags=["Stripe"])
async def stripe_webhook(request: Request, stripe_signature: str = Header(None, alias="Stripe-Signature")):
    """
    Handle Stripe webhooks for subscription events.
    """
    endpoint_secret = settings.stripe_webhook_secret
    if not endpoint_secret:
        raise HTTPException(status_code=500, detail="Webhook secret not configured.")

    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, endpoint_secret
        )
    except ValueError:
        # Invalid payload
        return JSONResponse(status_code=400, content={"detail": "Invalid payload"})
    except stripe.error.SignatureVerificationError:
        # Invalid signature
        return JSONResponse(status_code=400, content={"detail": "Invalid signature"})

    # Handle the event
    if event["type"] == "invoice.payment_succeeded":
        invoice = event["data"]["object"]
        subscription_id = invoice.get("subscription")
        if subscription_id:
            # Update subscription status in the database
            StripeDbCore.update_subscription_status(subscription_id, "active")
            # TODO: send email to user
        else:
            # One-time invoice
            StripeDbCore.update_invoice_status(invoice["id"], "paid")
            StripeDbCore.update_invoice_record(invoice["id"], "paid")
            print(f"Invoice {invoice['id']} paid successfully.")
    elif event["type"] == "invoice.payment_failed":
        invoice = event["data"]["object"]
        subscription_id = invoice.get("subscription")
        if subscription_id:
            # Update subscription status in the database
            StripeDbCore.update_subscription_status(subscription_id, "past_due")
            # Implement subscription retry logic
            from datetime import datetime, timedelta  # added local import
            subscription = StripeDbCore.get_subscription(subscription_id)
            current_retry = (subscription.get('payment_retry_attempt') if (subscription and subscription.get('payment_retry_attempt') is not None) else 0) + 1
            now = datetime.now()
            if current_retry == 1:
                first_payment_retry_at = now + timedelta(days=1)
                second_payment_retry_at = now + timedelta(days=2)
                service_cutoff_at = now + timedelta(days=14)
                BillingDbCore.update_stripe_subscription_retry_info(
                    subscription_id,
                    current_retry,
                    first_payment_retry_at,
                    second_payment_retry_at,
                    service_cutoff_at
                )
            else:
                BillingDbCore.add_stripe_subscription_retry_count(subscription_id)
            # TODO: send email to user
        else:
            StripeDbCore.update_invoice_status(invoice["id"], "failed")
            StripeDbCore.update_invoice_record(invoice["id"], "failed")
            print(f"Invoice {invoice['id']} failed to charge.")
    elif event["type"] == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        # Update subscription status in the database
        StripeDbCore.update_subscription_status(subscription["id"], "canceled")
        # TODO: send email to user
    elif event["type"] == "checkout.session.completed":
        data = event["data"]["object"]
        customer_id = data["customer"]
        user = UsersDbCore.get_user_by_stripe_customer_id(customer_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user_id = user["user_id"]
        exists = StripeDbCore.get_subscription(data["subscription"])
        if exists:
            # Update subscription status in the database
            StripeDbCore.update_subscription_status(data["subscription"], "active")
        else:
            # Create a new subscription in the database
            StripeDbCore.create_subscription(data["subscription"], user_id, "active")
        # TODO: send email to user
    else:
        # Log unsupported webhook events in detail
        print(str(event))

    return JSONResponse(status_code=200, content={"detail": "Webhook received"})
