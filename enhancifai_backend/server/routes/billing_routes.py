# enhancifai_backend/server/routes/billing_routes.py

import csv
import io
import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from weasyprint import HTML

import stripe

from enhancifai_backend.database.handlers.billing import BillingDbCore
from enhancifai_backend.server.utils import get_current_user_id, verify_secret_key

router = APIRouter()
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

@router.get("/billing/usage", tags=["Billing"])
async def get_usage_history(
    user_id: int = Depends(get_current_user_id), 
    _api_key: str = Depends(verify_secret_key)
):
    """
    Retrieve the usage history for the current user.

    **Endpoint**: GET `/billing/usage`

    This endpoint returns the history of EnhancifAI executions and token consumption for the authenticated user.

    **Parameters**:
    - None

    **Response**:
    - **200 OK**: Returns a JSON object with the usage history.
        - `usage_history`: A list of usage records, each containing details like execution time, uploaded file name, type, number of rows, total tokens, cost per token, total cost.
    - **500 Internal Server Error**: If an error occurs.

    **Example Response**:
    ```json
    {
      "usage_history": [
        {
          "execution_time": "2023-10-01T12:34:56",
          "uploaded_file_name": "data.csv",
          "type": "csv",
          "number_of_rows": 100,
          "total_tokens": 5000,
          "cost_per_token": 0.0001,
          "total_cost": 0.50
        },
        ...
      ]
    }
    ```
    """
    try:
        usage_history = BillingDbCore.get_usage_history(user_id)
        return JSONResponse(status_code=200, content={"usage_history": usage_history})
    except Exception as e:
        print(e)
        return JSONResponse(status_code=500, content={"detail": str(e)})

@router.get("/billing/usage/download", tags=["Billing"])
async def download_usage_history(
    file_format: str = "csv",
    user_id: int = Depends(get_current_user_id), 
    _api_key: str = Depends(verify_secret_key)
):
    """
    Download the usage history as a CSV or PDF file.

    **Endpoint**: GET `/billing/usage/download`

    This endpoint allows the authenticated user to download their usage history in CSV or PDF format.

    **Parameters**:
    - `file_format` (query parameter, optional): The file format for the download. Accepts `'csv'` or `'pdf'`. Default is `'csv'`.

    **Response**:
    - **200 OK**: Returns the usage history file in the requested format.
        - For CSV: A file with content type `'text/csv'`.
        - For PDF: A file with content type `'application/pdf'` (Note: PDF download is not implemented yet).
    - **400 Bad Request**: If an invalid file format is specified.
    - **501 Not Implemented**: If PDF download is requested (since it's not implemented yet).
    - **500 Internal Server Error**: If an error occurs.
    """
    try:
        usage_history = BillingDbCore.get_usage_history(user_id)
        if file_format.lower() == "csv":
            # Convert usage_history to CSV
            output = io.StringIO()
            writer = csv.writer(output)
            # Write headers
            if usage_history:
                writer.writerow(usage_history[0].keys())
                for record in usage_history:
                    writer.writerow(record.values())
            output.seek(0)
            response = StreamingResponse(
                iter([output.getvalue()]), 
                media_type="text/csv"
            )
            response.headers["Content-Disposition"] = "attachment; filename=usage_history.csv"
            return response
        elif file_format.lower() == "pdf":
            # Implement PDF generation if required
            raise HTTPException(
                status_code=501, detail="PDF download not implemented yet."
            )
        else:
            raise HTTPException(
                status_code=400, detail="Invalid file format. Choose 'csv' or 'pdf'."
            )
    except Exception as e:
        print(e)
        return JSONResponse(status_code=500, content={"detail": str(e)})

@router.get("/billing/monthly-balance", tags=["Billing"])
async def get_monthly_balance(
    user_id: int = Depends(get_current_user_id), 
    _api_key: str = Depends(verify_secret_key)
):
    """
    Provide the current monthly balance for the user.

    **Endpoint**: GET `/billing/monthly-balance`

    This endpoint returns the current monthly balance for the authenticated user, including the total cost for the current month.

    **Parameters**:
    - None

    **Response**:
    - **200 OK**: Returns a JSON object with the monthly balance.
        - `monthly_balance`: An object containing:
            - `billing_month`: The billing month in `'YYYY-MM'` format.
            - `total_monthly_cost`: The total cost for the current month.
    - **500 Internal Server Error**: If an error occurs.

    **Example Response**:
    ```json
    {
      "monthly_balance": {
        "billing_month": "2023-10",
        "total_monthly_cost": 10.00
      }
    }
    ```
    """
    try:
        monthly_balance = BillingDbCore.get_monthly_balance(user_id)
        return JSONResponse(status_code=200, content={"monthly_balance": monthly_balance})
    except Exception as e:
        print(e)
        return JSONResponse(status_code=500, content={"detail": str(e)})

@router.get("/billing/usage-by-model", tags=["Billing"])
async def get_usage_by_model(
    user_id: int = Depends(get_current_user_id), 
    _api_key: str = Depends(verify_secret_key)
):
    """
    Get usage data aggregated by AI model.

    **Endpoint**: GET `/billing/usage-by-model`

    This endpoint returns the usage data for the authenticated user, aggregated by AI model. It includes tokens used, price per token, and total cost for each model.

    **Parameters**:
    - None

    **Response**:
    - **200 OK**: Returns a JSON object with the usage data by model.
        - `usage_by_model`: A list of records, each containing:
            - `ai_model_name`: The name of the AI model.
            - `tokens_used`: Total tokens used for this model in the current month.
            - `price_per_token`: Price per token for this model.
            - `total_cost`: Total cost for this model in the current month.
    - **500 Internal Server Error**: If an error occurs.

    **Example Response**:
    ```json
    {
      "usage_by_model": [
        {
          "ai_model_name": "gpt-4",
          "tokens_used": 10000,
          "price_per_token": 0.0001,
          "total_cost": 1.00
        },
        ...
      ]
    }
    ```
    """
    try:
        usage_by_model = BillingDbCore.get_usage_by_model(user_id)
        return JSONResponse(status_code=200, content={"usage_by_model": usage_by_model})
    except Exception as e:
        print(e)
        return JSONResponse(status_code=500, content={"detail": str(e)})

@router.get("/billing/invoice-history", tags=["Billing"])
async def get_invoice_history(
    user_id: int = Depends(get_current_user_id), 
    _api_key: str = Depends(verify_secret_key)
):
    """
    Retrieve the invoice history for the current user.

    **Endpoint**: GET `/billing/invoice-history`

    This endpoint returns the invoice data for the authenticated user, including date, invoice number, invoice amount, payment date, and status.

    **Parameters**:
    - None

    **Response**:
    - **200 OK**: Returns a JSON object with the invoice history.
        - `invoice_history`: A list of invoices, each containing:
            - `date`: The date of the invoice.
            - `invoice_number`: The invoice number.
            - `invoice_amount`: The amount of the invoice.
            - `payment_date`: The date the invoice was paid.
            - `payment_status`: The status of the invoice (`'paid'`, `'unpaid'`, etc.).
    - **500 Internal Server Error**: If an error occurs.

    **Example Response**:
    ```json
    {
      "invoice_history": [
        {
          "date": "2023-10-01",
          "invoice_number": "INV-12345",
          "invoice_amount": 10.00,
          "payment_date": "2023-10-02",
          "payment_status": "paid"
        },
        ...
      ]
    }
    ```
    """
    try:
        invoice_history = BillingDbCore.get_invoice_history(user_id)
        return JSONResponse(status_code=200, content={"invoice_history": invoice_history})
    except Exception as e:
        print(e)
        return JSONResponse(status_code=500, content={"detail": str(e)})

@router.get("/billing/invoice/download/{invoice_id}", tags=["Billing"])
async def download_invoice(
    invoice_id: str,
    user_id: int = Depends(get_current_user_id),
    _api_key: str = Depends(verify_secret_key)
):
    """
    Download an invoice as a PDF file.

    **Endpoint**: GET `/billing/invoice/download/{invoice_id}`

    This endpoint allows the authenticated user to download a specific invoice as a PDF file.

    **Parameters**:
    - `invoice_id` (path parameter): The ID of the invoice to download.

    **Response**:
    - **200 OK**: Returns the invoice PDF file.
        - Content-Type: `'application/pdf'`
        - Content-Disposition: `'attachment; filename=invoice_{invoice_id}.pdf'`
    - **404 Not Found**: If the invoice is not found.
    - **500 Internal Server Error**: If an error occurs.
    """
    try:
        # Retrieve invoice data from the database
        invoice = BillingDbCore.get_invoice_by_id(user_id, invoice_id)
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found.")
        
        # Generate PDF content
        html_content = f"""
        <html>
        <body>
            <h1>Invoice #{invoice['invoice_number']}</h1>
            <p>Date: {invoice['date']}</p>
            <p>Amount: ${invoice['invoice_amount']/100:.2f}</p>
            <p>Status: {invoice['payment_status']}</p>
            <!-- Add more invoice details as needed -->
        </body>
        </html>
        """
        pdf = HTML(string=html_content).write_pdf()
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=invoice_{invoice_id}.pdf"}
        )
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
    except Exception as e:
        print(e)
        return JSONResponse(status_code=500, content={"detail": str(e)})

@router.post("/billing/invoice/pay/{invoice_id}", tags=["Billing"])
async def pay_invoice(
    invoice_id: str,
    user_id: int = Depends(get_current_user_id),
    _api_key: str = Depends(verify_secret_key)
):
    """
    Create a Stripe Checkout Session to pay an outstanding invoice.

    **Endpoint**: POST `/billing/invoice/pay/{invoice_id}`

    This endpoint initiates a Stripe Checkout Session for the authenticated user to pay a specific outstanding invoice.

    **Parameters**:
    - `invoice_id` (path parameter): The ID of the invoice to pay.

    **Response**:
    - **200 OK**: Returns a JSON object with the checkout URL.
        - `checkout_url`: The URL of the Stripe Checkout Session.
    - **400 Bad Request**: If the invoice is already paid.
    - **404 Not Found**: If the invoice is not found.
    - **500 Internal Server Error**: If an error occurs.

    **Example Response**:
    ```json
    {
      "checkout_url": "https://checkout.stripe.com/pay/cs_test_a1b2c3d4e5f6g7h8i9j0"
    }
    ```
    """
    try:
        # Retrieve invoice data
        invoice = BillingDbCore.get_invoice_by_id(user_id, invoice_id)
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found.")
        
        # Check if invoice is already paid
        if invoice['payment_status'] == 'paid':
            raise HTTPException(status_code=400, detail="Invoice is already paid.")
        
        # Retrieve or create Stripe customer
        customer_id = BillingDbCore.get_stripe_customer_id(user_id)
        if not customer_id:
            # Create new Stripe customer
            user = BillingDbCore.get_user_details(user_id)
            customer = stripe.Customer.create(
                email=user['email'],
                name=user['name']
            )
            customer_id = customer.id
            # Save customer ID in the database
            BillingDbCore.update_stripe_customer_id(user_id, customer_id)
        
        # Create a Checkout Session
        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'unit_amount': int(invoice['invoice_amount']),  # Amount in cents
                    'product_data': {
                        'name': f"Invoice #{invoice_id}",
                    },
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=f"{os.getenv('FRONTEND_URL')}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{os.getenv('FRONTEND_URL')}/billing/cancel",
            metadata={
                'invoice_id': invoice_id
            }
        )
        return JSONResponse(status_code=200, content={'checkout_url': session.url})
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
    except Exception as e:
        print(e)
        return JSONResponse(status_code=500, content={"detail": str(e)})
        
@router.post("/stripe/webhook", tags=["Stripe"])
async def stripe_webhook(request: Request):
    """
    Handle Stripe webhooks for invoice payment events.

    **Endpoint**: POST `/stripe/webhook`

    This endpoint handles webhook events from Stripe related to invoice payments.

    **Note**: This endpoint is used by Stripe to notify the server about payment events. It should not be called by the frontend.

    **Parameters**:
    - The request body and headers are provided by Stripe.

    **Response**:
    - **200 OK**: If the webhook event is successfully processed.
    - **400 Bad Request**: If the payload or signature is invalid.
    - **500 Internal Server Error**: If an error occurs.
    """
    endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

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
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        invoice_id = session['metadata']['invoice_id']
        payment_status = 'paid'  # Since payment was successful
        # Update invoice status in the database
        BillingDbCore.update_invoice_status(invoice_id, payment_status)
    elif event['type'] == 'checkout.session.async_payment_failed':
        session = event['data']['object']
        invoice_id = session['metadata']['invoice_id']
        payment_status = 'failed'
        BillingDbCore.update_invoice_status(invoice_id, payment_status)
    # ... handle other event types as needed

    return JSONResponse(status_code=200, content={"message": "Webhook received!"})

@router.get("/billing/rate-card", tags=["Billing"])
async def get_rate_card(
    month: Optional[int] = None,
    year: Optional[int] = None,
    user_id: int = Depends(get_current_user_id),
    _api_key: str = Depends(verify_secret_key)
):
    """
    Retrieve the rate card for AI models.

    **Endpoint**: GET `/billing/rate-card`

    This endpoint returns the cost per 1000 tokens for each AI model. It supports optional filtering by month and year to retrieve historical rates.

    **Parameters**:
    - `month` (query parameter, optional): The month for which to retrieve rates (1-12).
    - `year` (query parameter, optional): The year for which to retrieve rates.

    **Response**:
    - **200 OK**: Returns a JSON object with the rates.
        - `rates`: A list of rates, each containing:
            - `model_name`: The name of the AI model.
            - `price_per_token`: The price per token for this model.
            - `effective_date`: The date from which this rate is effective.
    - **500 Internal Server Error**: If an error occurs.

    **Example Response**:
    ```json
    {
      "rates": [
        {
          "model_name": "gpt-4",
          "price_per_token": 0.0001,
          "effective_date": "2023-10-01"
        },
        ...
      ]
    }
    ```
    """
    try:
        rates = BillingDbCore.get_rate_card(month, year)
        return JSONResponse(status_code=200, content={"rates": rates})
    except Exception as e:
        print(e)
        return JSONResponse(status_code=500, content={"detail": str(e)})
