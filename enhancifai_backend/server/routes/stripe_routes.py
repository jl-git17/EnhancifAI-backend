import os
import stripe
from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import JSONResponse
from enhancifai_backend.database.handlers.stripe import StripeDbCore

# Initialize Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

router = APIRouter()


@router.post("/stripe/webhook", tags=["Stripe"])
async def stripe_webhook(payload: dict, sig_header: str = Header(None)):
    """
    Handle Stripe webhooks for invoice payment events.
    """
    endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not endpoint_secret:
        raise HTTPException(status_code=500, detail="Webhook secret not configured.")
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError:
        # Invalid payload
        return JSONResponse(status_code=400, content={"detail": "Invalid payload"})
    except stripe.error.SignatureVerificationError:
        # Invalid signature
        return JSONResponse(status_code=400, content={"detail": "Invalid signature"})
    
    # Handle the event
    if event['type'] == 'invoice.payment_succeeded':
        invoice = event['data']['object']
        # Update invoice status in the database
        StripeDbCore.update_invoice_status(invoice.id, invoice.status)
    elif event['type'] == 'invoice.payment_failed':
        invoice = event['data']['object']
        # Handle payment failure
        StripeDbCore.update_invoice_status(invoice.id, invoice.status)
    # ... handle other event types as needed
    
    return JSONResponse(status_code=200, content={"message": "Webhook received!"})

