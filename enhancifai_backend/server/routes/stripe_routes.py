import os
import stripe
from datetime import datetime
from fastapi import APIRouter, Depends, Form, HTTPException, Header, status
from fastapi.responses import JSONResponse
from enhancifai_backend.database.handlers.stripe import StripeDbCore
from enhancifai_backend.database.handlers.users import UsersDbCore
from enhancifai_backend.server.utils import get_current_user_id, verify_secret_key

# Initialize Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

router = APIRouter()

@router.post("/stripe/create-customer", tags=["Stripe"])
async def create_customer(email: str, user_id: int = Depends(get_current_user_id), _api_key: str = Depends(verify_secret_key)):
    try:
        customer_id = StripeDbCore.get_stripe_customer_id(user_id)
        
        if customer_id:
            return JSONResponse(status_code=200, content={"customer_id": customer_id})

        # Create a new customer if one does not exist
        customer = stripe.Customer.create(email=email)
        StripeDbCore.save_stripe_customer_id(user_id, customer.id)
        return JSONResponse(status_code=200, content={"customer_id": customer.id})
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@router.post("/stripe/payment-intent", tags=["Stripe"])
async def create_payment_intent(amount: int, currency: str = "usd", user_id: int = Depends(get_current_user_id), _api_key: str = Depends(verify_secret_key)):
    try:
        customer_id = StripeDbCore.get_stripe_customer_id(user_id)
        payment_intent = stripe.PaymentIntent.create(
            amount=amount,
            currency=currency,
            customer=customer_id,
            payment_method_types=["card"],
        )
        return JSONResponse(status_code=200, content={"client_secret": payment_intent.client_secret})
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@router.post("/stripe/generate-invoice", tags=["Stripe"])
async def generate_invoice(user_id: int = Depends(get_current_user_id), _api_key: str = Depends(verify_secret_key)):
    """
    Generate a Stripe invoice based on the user's token usage for the current month.
    """
    try:
        # Calculate total tokens used by the user this month
        tokens_used = UsersDbCore.get_user_token_usage(user_id)
        
        # Define your pricing logic here, e.g., $0.01 per token
        PRICE_PER_TOKEN = 1  # in cents, adjust as needed
        amount_due = tokens_used * PRICE_PER_TOKEN
        
        if amount_due <= 0:
            return JSONResponse(status_code=200, content={"message": "No charges due for this month."})
        
        customer_id = StripeDbCore.get_stripe_customer_id(user_id)
        if not customer_id:
            raise HTTPException(status_code=400, detail="Stripe customer not found.")
        
        # Create an invoice item
        stripe.InvoiceItem.create(
            customer=customer_id,
            amount=amount_due,
            currency="usd",
            description=f"Token usage for {datetime.now().strftime('%B %Y')}",
        )
        
        # Create the invoice
        invoice = stripe.Invoice.create(
            customer=customer_id,
            auto_advance=True,  # Auto-finalize the invoice
        )
        
        # Optionally, you can send the invoice to the customer
        stripe.Invoice.send_invoice(invoice.id)
        
        # Save the invoice details in the database
        StripeDbCore.save_stripe_invoice(invoice.id, user_id, amount_due, invoice.status)
        
        return JSONResponse(status_code=200, content={"invoice_id": invoice.id, "amount_due": amount_due})
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@router.get("/stripe/payment-history", tags=["Stripe"])
async def payment_history(user_id: int = Depends(get_current_user_id), _api_key: str = Depends(verify_secret_key)):
    """
    Retrieve the payment history for the user.
    """
    try:
        invoices = StripeDbCore.get_user_invoices(user_id)
        return JSONResponse(status_code=200, content={"invoices": invoices})
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

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

