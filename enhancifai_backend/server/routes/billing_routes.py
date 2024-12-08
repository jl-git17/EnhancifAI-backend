# enhancifai_backend/server/routes/billing_routes.py

import csv
from datetime import datetime
from decimal import Decimal
import io
import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from weasyprint import HTML

import stripe

from enhancifai_backend.database.handlers.billing import BillingDbCore
from enhancifai_backend.server.utils import get_current_user_id, verify_secret_key

router = APIRouter()
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


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
        monthly_balance = BillingDbCore.get_monthly_balance(user_id)
        return JSONResponse(status_code=200, content={"monthly_balance": monthly_balance})
    except Exception as e:
        print(e)
        return JSONResponse(status_code=500, content={"detail": str(e)})

@router.get("/billing/usage-by-model", tags=["Billing"])
async def get_usage_by_model(
    month: int = Depends(get_default_month),
    year: int = Depends(get_default_year),
    user_id: int = Depends(get_current_user_id),
    _api_key: str = Depends(verify_secret_key)
):
    """
    Get usage data aggregated by AI model, filtered by month and year if provided.
    """
    try:
        # Call the modified get_usage_by_model function with month and year
        usage_by_model = BillingDbCore.get_usage_by_model(user_id, month=month, year=year)
        return JSONResponse(status_code=200, content={"usage_by_model": usage_by_model})
    except ValueError as ve:
        # Handle validation errors from BillingDbCore
        print(f"Validation error in get_usage_by_model: {str(ve)}")
        raise HTTPException(status_code=400, detail=str(ve))
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
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found.")

        invoice_number = invoice['invoice_number']
        date_issued = invoice['date']
        amount = invoice['invoice_amount']
        status = invoice['payment_status']
        payment_date = invoice['payment_date'] if invoice['payment_date'] else "N/A"
        billing_period_start = invoice.get('billing_period_start', 'N/A')
        billing_period_end = invoice.get('billing_period_end', 'N/A')
        metadata = invoice.get('metadata', {})
        description = metadata.get('description', 'N/A')
        line_items = metadata.get('line_items', [])

        # Build line items HTML table
        line_items_html = ""
        if line_items:
            line_items_html = """
            <h3>Usage Details</h3>
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
            for item in line_items:
                line_items_html += f"""
                <tr>
                    <td>{item['date']}</td>
                    <td>{item['model']}</td>
                    <td>{item['tokens']}</td>
                    <td>${item['rate']:.6f}</td>
                    <td>${item['amount']:.2f}</td>
                </tr>
                """
            line_items_html += "</tbody></table>"

        # Improved invoice HTML
        html_content = f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Invoice #{invoice_number}</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 40px;
                    font-size: 14px;
                    color: #333;
                }}
                h1, h2, h3 {{
                    margin-bottom: 0.5em;
                }}
                .header, .footer {{
                    text-align: center;
                    margin-bottom: 40px;
                }}
                .header h1 {{
                    font-size: 24px;
                    margin-bottom: 5px;
                }}
                .header p {{
                    margin: 0;
                    font-size: 14px;
                }}
                hr {{
                    border: none;
                    border-bottom: 1px solid #ccc;
                    margin: 20px 0;
                }}
                .details-table, .line-items-table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-bottom: 20px;
                }}
                .details-table td, .details-table th,
                .line-items-table td, .line-items-table th {{
                    padding: 8px;
                    border-bottom: 1px solid #eee;
                    vertical-align: top;
                }}
                .details-table th, .line-items-table th {{
                    text-align: left;
                    font-weight: bold;
                }}
                .amount {{
                    font-size: 18px;
                    font-weight: bold;
                    color: #000;
                }}
                .footer p {{
                    font-size: 12px;
                    color: #999;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Invoice</h1>
                <p>Enhancifai Inc.<br>1234 AI Drive<br>Innovation City, AI 56789</p>
            </div>

            <hr>

            <h2>Invoice Details</h2>
            <table class="details-table">
                <tr><th>Invoice #</th><td>{invoice_number}</td></tr>
                <tr><th>Date Issued</th><td>{date_issued}</td></tr>
                <tr><th>Billing Period</th><td>{billing_period_start} to {billing_period_end}</td></tr>
                <tr><th>Description</th><td>{description}</td></tr>
                <tr><th>Status</th><td>{status}</td></tr>
                <tr><th>Payment Date</th><td>{payment_date}</td></tr>
                <tr><th>Amount Due</th><td class="amount">${amount:.2f}</td></tr>
            </table>

            {line_items_html}

            <p>Thank you for your business. Please contact our support team if you have any questions about this invoice.</p>

            <div class="footer">
                <p>&copy; {datetime.now().year} Enhancifai Inc.</p>
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
    user_id: int = Depends(get_current_user_id),
    _api_key: str = Depends(verify_secret_key)
):
    """
    Create a Stripe Checkout Session to pay an outstanding invoice.
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
                    'unit_amount': int(invoice['invoice_amount'] * 100),  # Convert dollars to cents
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
        print("Error in pay_invoice: %s", str(e), exc_info=True)
        return JSONResponse(status_code=500, content={"detail": "Internal server error."})

@router.post("/stripe/webhook", tags=["Stripe"])
async def stripe_webhook(request: Request):
    """
    Handle Stripe webhooks for invoice payment events.
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
    """
    try:
        rates = BillingDbCore.get_rate_card(month, year)
        # Convert price_per_token to float with four decimal places
        for rate in rates:
            rate['price_per_token'] = float(Decimal(rate['price_per_token']).quantize(Decimal('0.0001')))
        return JSONResponse(status_code=200, content={"rates": rates})
    except Exception as e:
        print(e)
        return JSONResponse(status_code=500, content={"detail": str(e)})
