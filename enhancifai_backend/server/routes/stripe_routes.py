import os
import logging  # added logging module

from fastapi import APIRouter, Request, HTTPException, Header
from fastapi.responses import JSONResponse
import stripe

from enhancifai_backend.database.handlers.stripe import StripeDbCore

# Initialize Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

router = APIRouter()

@router.post("/stripe/webhook", tags=["Stripe"])
async def stripe_webhook(request: Request, stripe_signature: str = Header(None, alias="Stripe-Signature")):
    """
    Handle Stripe webhooks for subscription events.
    """
    endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
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
        subscription_id = invoice["subscription"]
        # Update subscription status in the database
        StripeDbCore.update_subscription_status(subscription_id, "active")
    elif event["type"] == "invoice.payment_failed":
        invoice = event["data"]["object"]
        subscription_id = invoice["subscription"]
        # Update subscription status in the database
        StripeDbCore.update_subscription_status(subscription_id, "past_due")
    elif event["type"] == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        # Update subscription status in the database
        StripeDbCore.update_subscription_status(subscription["id"], "canceled")
    elif event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        subscription_id = session.get("subscription")
        if subscription_id:
            subscription = StripeDbCore.get_subscription(subscription_id)  # new method call
            if not subscription:
                user_id = session.get("client_reference_id")
                if user_id:
                    StripeDbCore.create_subscription(subscription_id, int(user_id), "active")  # new method call
                else:
                    logging.info("Checkout session missing client_reference_id for subscription creation: %s", session)
            else:
                StripeDbCore.update_subscription_status(subscription_id, "active")
        else:
            logging.info("Checkout session completed without subscription id: %s", session)
    else:
        # Log unsupported webhook events in detail
        logging.info("Received unsupported event type: %s, event details: %s", event.get("type"), event)

    return JSONResponse(status_code=200, content={"detail": "Webhook received"})
