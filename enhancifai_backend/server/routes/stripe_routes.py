import os
import stripe
from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import JSONResponse
from enhancifai_backend.database.handlers.stripe import StripeDbCore

# Initialize Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

router = APIRouter()
