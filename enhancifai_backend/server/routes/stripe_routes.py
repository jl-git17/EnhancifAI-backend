import os
import stripe
from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.responses import JSONResponse
from enhancifai_backend.database.handlers.stripe import StripeDbCore
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

@router.post("/stripe/create-subscription", tags=["Stripe"])
async def create_subscription(user_id: int = Depends(get_current_user_id), plan_id: str = Form(...), _api_key: str = Depends(verify_secret_key)):
    try:
        customer_id = StripeDbCore.get_stripe_customer_id(user_id)
        subscription = StripeDbCore.get_stripe_subscription(user_id)
        
        if subscription:
            return JSONResponse(status_code=400, content={"detail": "User is already subscribed."})

        subscription = stripe.Subscription.create(
            customer=customer_id,
            items=[{"plan": plan_id}],
        )
        StripeDbCore.save_stripe_subscription(user_id, subscription.id)
        return JSONResponse(status_code=200, content={"subscription_id": subscription.id})
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@router.post("/stripe/cancel-subscription", tags=["Stripe"])
async def cancel_subscription(user_id: int = Depends(get_current_user_id), _api_key: str = Depends(verify_secret_key)):
    try:
        subscription_id = StripeDbCore.get_stripe_subscription(user_id)
        stripe.Subscription.delete(subscription_id)

        # Retrieve the Stripe subscription ID from the database
        subscription_id = StripeDbCore.get_stripe_subscription(user_id)
        if not subscription_id:
            return JSONResponse(status_code=404, content={"detail": "Subscription not found."})
        # Cancel the subscription via Stripe API
        stripe.Subscription.delete(subscription_id)
        
        StripeDbCore.cancel_stripe_subscription(user_id)
        return JSONResponse(status_code=200, content={"message": "Subscription canceled."})
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

@router.post("/stripe/webhook", tags=["Stripe"])
async def stripe_webhook(payload: dict):
    event = None
    try:
        event = stripe.Webhook.construct_event(payload['data'], payload['signature'], os.getenv("STRIPE_WEBHOOK_SECRET"))
        if event['type'] == 'customer.subscription.updated':
            subscription = event['data']['object']
            # Handle subscription update in your database
            StripeDbCore.update_subscription_status(subscription['id'], subscription['status'])
        elif event['type'] == 'customer.subscription.deleted':
            subscription = event['data']['object']
            # Handle subscription cancellation
            StripeDbCore.cancel_stripe_subscription(subscription['id'])
    except ValueError as e:
        return JSONResponse(status_code=400, content={"detail": "Invalid payload"})
    except stripe.error.SignatureVerificationError as e:
        return JSONResponse(status_code=400, content={"detail": "Invalid signature"})
    
    return JSONResponse(status_code=200, content={"message": "Webhook received!"})
