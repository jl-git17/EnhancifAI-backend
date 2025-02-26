from fastapi import APIRouter, Request, HTTPException, Header
from fastapi.responses import JSONResponse
import stripe
import logging

from enhancifai_backend.config import settings
from enhancifai_backend.database.handlers.stripe import StripeDbCore
from enhancifai_backend.database.handlers.users import UsersDbCore

# Initialize Stripe
stripe.api_key = settings.stripe_secret_key

router = APIRouter()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

    # Log the event
    logger.info(f"Received Stripe event: {event}")

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
