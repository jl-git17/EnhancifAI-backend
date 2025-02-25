import calendar
import csv
from datetime import datetime
from decimal import Decimal
import io
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from weasyprint import HTML

import stripe

from enhancifai_backend.config import settings
from enhancifai_backend.database.handlers.billing import BillingDbCore
from enhancifai_backend.database.handlers.run_logs import PromptImproverRunLogsDbCore, RunLogsDbCore
from enhancifai_backend.database.handlers.stripe import StripeDbCore
from enhancifai_backend.server.utils import get_current_user_id, verify_secret_key

router = APIRouter()
stripe.api_key = settings.stripe_secret_key


def get_default_month(
    month: Optional[int] = Query(
        None, ge=1, le=12, description="Month for filtering (1-12)"
    )
) -> int:
    """
    Dependency to provide the month, defaulting to the current month if not provided.
    """
    return month if month is not None else datetime.now().month

def get_default_year(
    year: Optional[int] = Query(
        None, ge=2000, le=datetime.now().year, description="Year for filtering (e.g., 2023)"
    )
) -> int:
    """
    Dependency to provide the year, defaulting to the current year if not provided.
    """
    return year if year is not None else datetime.now().year

@router.get("/billing/usage", tags=["Billing"])
async def get_usage_history(
    user_id: int = Depends(get_current_user_id),
    _api_key: str = Depends(verify_secret_key)
):
    """
    Retrieve the usage history for the current user.
    """
    try:
        usage_history = BillingDbCore.get_usage_history(user_id)
        # Note: total_tokens is computed as the sum of input_tokens and output_tokens.
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
    """
    try:
        # Note: Monthly cost is based on the sum of input_tokens and output_tokens.
        monthly_balance = BillingDbCore.get_monthly_balance(user_id)
        return JSONResponse(status_code=200, content={"monthly_balance": monthly_balance})
    except Exception as e:
        print(e)
        return JSONResponse(status_code=500, content={"detail": str(e)})

@router.get("/billing/usage-by-model", tags=["Billing"])
async def get_usage_by_model_endpoint(
    month: int = Depends(get_default_month),
    year: int = Depends(get_default_year),
    user_id: int = Depends(get_current_user_id),
    _api_key: str = Depends(verify_secret_key)
):
    """
    Get usage data aggregated by AI model, filtered by month and year if provided.
    """
    # Return blank array if user is not subscribed.
    if not StripeDbCore.is_user_subscribed(user_id):
        return JSONResponse(status_code=200, content={"usage_by_model": []})
    
    try:
        # Call the modified get_usage_by_model function with month and year
        usage_by_model = BillingDbCore.get_usage_by_model(user_id, month=month, year=year)
        return JSONResponse(status_code=200, content={"usage_by_model": usage_by_model})
    except ValueError as ve:
        # Handle validation errors from BillingDbCore
        print('Validation error in get_usage_by_model: ' + str(ve))
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        print(e)
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


@router.get("/billing/invoice-history", tags=["Billing"])
async def get_invoice_history(
    user_id: int = Depends(get_current_user_id),
    _api_key: str = Depends(verify_secret_key)
):
    """
    Retrieve the invoice history for the current user.
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
    Download an invoice as a PDF file with itemized details.
    """
    try:
        invoice = BillingDbCore.get_invoice_by_id(user_id, invoice_id)
        print(invoice)
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found.")

        invoice_number = invoice['invoice_id']

        # Format Date Issued
        date_issued_raw = invoice['date']
        date_issued = datetime.fromisoformat(date_issued_raw.replace('Z', '+00:00')).strftime('%B %d, %Y')

        amount = invoice['invoice_amount']
        status = invoice['payment_status']

        # Format Payment Date or set to empty string
        payment_date_raw = invoice.get('payment_date')
        if payment_date_raw:
            payment_date = datetime.fromisoformat(payment_date_raw.replace('Z', '+00:00')).strftime('%B %d, %Y')
        else:
            payment_date = ""

        # Format Billing Period
        billing_period_start_raw = invoice.get('billing_period_start')
        billing_period_end_raw = invoice.get('billing_period_end')
        if billing_period_start_raw and billing_period_end_raw:
            try:
                billing_period_start = datetime.fromisoformat(billing_period_start_raw).strftime('%B %d, %Y')
                billing_period_end = datetime.fromisoformat(billing_period_end_raw).strftime('%B %d, %Y')
            except ValueError:
                billing_period_start = billing_period_start_raw
                billing_period_end = billing_period_end_raw
        else:
            billing_period_start = billing_period_start_raw or ""
            billing_period_end = billing_period_end_raw or ""

        metadata = invoice.get('metadata', {})
        description = metadata.get('description', 'N/A')

        # Status Coloring
        status_color_map = {
            'paid': '#28a745',      # Green
            'unpaid': '#dc3545',   # Red
        }
        status_color = status_color_map.get(status, '#000000')  # Default to black

        # Normal token usage line items
        line_items = metadata.get('line_items', [])
        line_items_html = ""
        if line_items:
            line_items_html = """
            <h3 style="margin-top: 40px;">Execution Token Usage Details</h3>
            <table class="line-items-table">
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Model</th>
                        <th>Tokens</th>
                        <th>Rate (USD/token)</th>
                        <th>Subtotal (USD)</th>
                    </tr>
                </thead>
                <tbody>
            """
            for i, item in enumerate(line_items):
                row_bg = "#f9f9f9" if i % 2 == 0 else "#fff"

                item_date = datetime.fromisoformat(item['date'].replace('Z', '+00:00')).strftime('%B %d, %Y')
                line_items_html += f"""
                <tr style="background: {row_bg};">
                    <td>{item_date}</td>
                    <td>{item['model']}</td>
                    <td>{item['tokens']}</td>
                    <td>${item['rate']:.6f}</td>
                    <td>${item['amount']:.2f}</td>
                </tr>
                """
            line_items_html += "</tbody></table>"

        # PI token usage line items
        pi_line_items = metadata.get('pi_line_items', [])
        pi_line_items_html = ""
        if pi_line_items:
            pi_line_items_html = """
            <h3 style="margin-top: 40px;">Prompt Improver Token Usage Details</h3>
            <table class="line-items-table">
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Model</th>
                        <th>Tokens</th>
                        <th>Rate (USD/token)</th>
                        <th>Subtotal (USD)</th>
                    </tr>
                </thead>
                <tbody>
            """
            for i, item in enumerate(pi_line_items):
                row_bg = "#f9f9f9" if i % 2 == 0 else "#fff"
                item_date = datetime.fromisoformat(item['date'].replace('Z', '+00:00')).strftime('%B %d, %Y')
                pi_line_items_html += f"""
                <tr style="background: {row_bg};">
                    <td>{item_date}</td>
                    <td>{item['model']}</td>
                    <td>{item['tokens']}</td>
                    <td>${item['rate']:.6f}</td>
                    <td>${item['amount']:.2f}</td>
                </tr>
                """
            pi_line_items_html += "</tbody></table>"

        html_content = f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Invoice #{invoice_number}</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    font-size: 14px;
                    color: #333;
                    background: #f0f0f0;
                    margin: 0;
                    padding: 0;
                }}
                .invoice-container {{
                    max-width: 700px;
                    margin: 40px auto;
                    background: #fff;
                    border-radius: 8px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    padding: 40px;
                }}
                .header {{
                    text-align: center;
                    padding: 20px;
                    background: linear-gradient(to right, #1FBCFF, #66d0ff);
                    border-radius: 8px 8px 0 0;
                    margin: -40px -40px 20px -40px;
                }}
                .header h1 {{
                    font-size: 26px;
                    color: #fff;
                    margin: 0;
                }}
                .header p {{
                    font-size: 14px;
                    color: #eaf9ff;
                    margin: 5px 0 0 0;
                }}
                h2, h3 {{
                    color: #1FBCFF;
                    margin-top: 30px;
                    margin-bottom: 10px;
                }}
                .divider {{
                    border: none;
                    border-bottom: 1px solid #1FBCFF;
                    margin: 20px 0;
                }}
                .details-table, .line-items-table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-bottom: 20px;
                }}
                .details-table th, .line-items-table th {{
                    text-align: left;
                    font-weight: bold;
                    border-bottom: 2px solid #1FBCFF;
                    padding: 8px;
                }}
                .details-table td, .line-items-table td {{
                    padding: 8px;
                    border-bottom: 1px solid #eee;
                    vertical-align: top;
                }}
                .amount {{
                    font-size: 18px;
                    font-weight: bold;
                    color: #000;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 40px;
                }}
                .footer p {{
                    font-size: 12px;
                    color: #999;
                }}
                .highlight-row th, .highlight-row td {{
                    background: #eaf7ff;
                }}
                p {{
                    line-height: 1.5em;
                }}
            </style>
        </head>
        <body>
            <div class="invoice-container">
                <div class="header">
                    <h1>EnhancifAI - Invoice</h1>
                </div>

                <h2>Invoice Details</h2>
                <hr class="divider">
                <table class="details-table">
                    <tr><th>Invoice #</th><td>{invoice_number}</td></tr>
                    <tr><th>Date Issued</th><td>{date_issued}</td></tr>
                    <tr><th>Billing Period</th><td>{billing_period_start} to {billing_period_end}</td></tr>
                    <tr><th>Description</th><td>{description}</td></tr>
                    <tr><th>Status</th><td style="color: {status_color};">{status}</td></tr>
                    <tr><th>Payment Date</th><td>{payment_date}</td></tr>
                    <tr class="highlight-row"><th>Amount Due</th><td class="amount">${amount:.2f}</td></tr>
                </table>

                {line_items_html}

                {pi_line_items_html}

                <p>Thank you for your business. Please contact our support team if you have any questions about this invoice.</p>

                <div class="footer">
                    <p>&copy; {datetime.now().year} EnhancifAI.</p>
                </div>
            </div>
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
    _user_id: int = Depends(get_current_user_id),
    _api_key: str = Depends(verify_secret_key)
):
    """
    Create a Stripe Checkout Session to pay an outstanding invoice.
    """
    try:
        # Retrieve invoice data
        invoice = BillingDbCore.get_invoice_by_id(_user_id, invoice_id)
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found.")

        # Check if invoice is already paid
        if invoice['payment_status'] == 'paid':
            raise HTTPException(status_code=400, detail="Invoice is already paid.")

        # Retrieve or create Stripe customer
        customer_id = BillingDbCore.get_stripe_customer_id(_user_id)
        if not customer_id:
            # Create new Stripe customer
            user = BillingDbCore.get_user_details(_user_id)
            customer = stripe.Customer.create(
                email=user['email'],
                name=user['name']
            )
            customer_id = customer.id
            # Save customer ID in the database
            BillingDbCore.update_stripe_customer_id(_user_id, customer_id)

        # Create a Checkout Session
        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'unit_amount': int(invoice['invoice_amount'] * 100),  # Convert dollars to cents
                    'product_data': {
                        'name': f"Invoice #{invoice_id}",
                    },
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=f"{settings.frontend_url}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.frontend_url}/billing/cancel",
            metadata={
                'invoice_id': invoice_id
            }
        )
        return JSONResponse(status_code=200, content={'checkout_url': session.url})
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
    except Exception as e:
        print("Error in pay_invoice: %s", str(e), exc_info=True)
        return JSONResponse(status_code=500, content={"detail": "Internal server error."})

@router.post("/stripe/webhook", tags=["Stripe"])
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature")
):
    """
    Handle Stripe webhooks for invoice payment events.
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
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        invoice_id = session["metadata"].get("invoice_id")
        payment_status = "paid"  # Since payment was successful
        if invoice_id:
            BillingDbCore.update_invoice_status(invoice_id, payment_status)
        else:
            # Handle missing invoice_id in metadata
            return JSONResponse(status_code=400, content={"detail": "Missing invoice_id in session metadata"})
    elif event["type"] == "checkout.session.async_payment_failed":
        session = event["data"]["object"]
        invoice_id = session["metadata"].get("invoice_id")
        payment_status = "failed"
        if invoice_id:
            BillingDbCore.update_invoice_status(invoice_id, payment_status)
        else:
            # Handle missing invoice_id in metadata
            return JSONResponse(status_code=400, content={"detail": "Missing invoice_id in session metadata"})
    # ... handle other event types as needed

    return JSONResponse(status_code=200, content={"message": "Webhook received!"})

@router.get("/billing/rate-card", tags=["Billing"])
async def get_rate_card(
    month: Optional[int] = None,
    year: Optional[int] = None,
    _user_id: int = Depends(get_current_user_id),
    _api_key: str = Depends(verify_secret_key)
):
    """
    Retrieve the rate card for AI models.
    """
    try:
        # Return blank array if the user is not subscribed
        if not StripeDbCore.is_user_subscribed(_user_id):
            return JSONResponse(status_code=200, content={"rates": []})
        rates = BillingDbCore.get_rate_card(month, year)
        # Convert price_per_token to float with four decimal places
        for rate in rates:
            rate['price_per_1000_tokens'] = float(Decimal(rate['price_per_token'])) * 1000
        return JSONResponse(status_code=200, content={"rates": rates})
    except Exception as e:
        print(e)
        return JSONResponse(status_code=500, content={"detail": str(e)})

@router.get("/billing/rate-card/history", tags=["Billing"])
async def get_rate_card_history(
    _user_id: int = Depends(get_current_user_id),
    _api_key: str = Depends(verify_secret_key)
):
    """
    Retrieve the historical rate card data, showing rates per month.
    """
    try:
        if not StripeDbCore.is_user_subscribed(_user_id):
            return JSONResponse(status_code=200, content={"rate_history": []})
        rate_history = BillingDbCore.get_rate_card_history()
        # Process the rate_history to include price_per_1000_tokens
        for rate in rate_history:
            rate['price_per_1000_tokens'] = float(Decimal(rate['price_per_token'])) * 1000
        return JSONResponse(status_code=200, content={"rate_history": rate_history})
    except Exception as e:
        print(e)
        return JSONResponse(status_code=500, content={"detail": str(e)})

@router.get("/billing/logs/{month}/{year}", tags=["Billing"])
async def download_monthly_activity_logs(
    month: int,
    year: int,
    user_id: int = Depends(get_current_user_id),
    _api_key: str = Depends(verify_secret_key)
):
    """
    Download the user's activity logs (normal usage and PI usage) for a specified month and year.
    """
    try:
        # Validate the month and year
        if month < 1 or month > 12:
            raise HTTPException(status_code=400, detail="Invalid month. Must be between 1 and 12.")
        if year < 2000 or year > datetime.now().year:
            raise HTTPException(status_code=400, detail="Invalid year.")

        # Calculate the start and end dates for the month
        start_date = datetime(year, month, 1)
        days_in_month = calendar.monthrange(year, month)[1]
        end_date = datetime(year, month, days_in_month, 23, 59, 59)

        # Retrieve logs from the database
        normal_logs = RunLogsDbCore.retrieve_logs_by_date_range(start_date, end_date)
        pi_logs = PromptImproverRunLogsDbCore.retrieve_logs_by_user_and_date_range(user_id, start_date, end_date)

        # Prepare CSV output
        output = io.StringIO()
        writer = csv.writer(output)

        # Write headers
        writer.writerow(["Source", "Timestamp", "Model", "Tokens", "Prompts", "Errors", "Time Elapsed (s)"])

        # Write normal logs
        for log in normal_logs:
            writer.writerow([
                "Normal Usage",
                log['log_timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                log['engine_model'],
                log['num_tokens'],
                log['num_prompts'],
                log['errors'] if log['errors'] else "",
                log['time_elapsed']
            ])

        # Write PI logs
        for log in pi_logs:
            writer.writerow([
                "Prompt Improver",
                log['log_timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                log['engine_model'],
                log['num_tokens'],
                log['num_prompts'],
                log['errors'] if log['errors'] else "",
                log['time_elapsed']
            ])

        # Reset buffer position
        output.seek(0)

        # Return as a streaming response
        response = StreamingResponse(iter([output.getvalue()]), media_type="text/csv")
        response.headers["Content-Disposition"] = f"attachment; filename=activity_logs_{year}_{month:02}.csv"
        return response

    except HTTPException as e:
        raise e
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@router.post("/billing/subscription/start", tags=["Billing"])
async def start_subscription(
    user_id: int = Depends(get_current_user_id),
    _api_key: str = Depends(verify_secret_key)
):
    """
    Create a Stripe Checkout Session to start a subscription.
    """
    try:
        # Check if the user is already subscribed
        if StripeDbCore.is_user_subscribed(user_id):
            raise HTTPException(status_code=400, detail="User is already subscribed.")

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

        # Create a Checkout Session for subscription
        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=['card'],
            line_items=[{
                'price': settings.stripe_subscription_price_id,  # Subscription price ID from Stripe
                'quantity': 1,
            }],
            mode='subscription',
            success_url=f"{settings.frontend_url}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.frontend_url}/billing/cancel",
            payment_method_collection="always",
            allow_promotion_codes=True,
        )
        return JSONResponse(status_code=200, content={'checkout_url': session.url})
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
    except Exception as e:
        print("Error in start_subscription: %s", str(e), exc_info=True)
        return JSONResponse(status_code=500, content={"detail": "Internal server error."})

@router.get("/billing/subscription/status", tags=["Billing"])
async def check_subscription_status(user_id: int = Depends(get_current_user_id), _api_key: str = Depends(verify_secret_key)):
    """
    Check if the current user is subscribed.

    Returns:
        JSONResponse: A JSON response containing the subscription status.
    """
    try:
        is_subscribed = StripeDbCore.is_user_subscribed(user_id)
        return JSONResponse(status_code=200, content={"subscribed": is_subscribed})
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred", "error": str(e)})
