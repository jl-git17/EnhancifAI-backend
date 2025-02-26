import base64
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Mail,
    Asm,
    IpPoolName,
    TrackingSettings,
    ClickTracking,
    OpenTracking,
    SubscriptionTracking,
    Attachment
)
import logging  # Add logging import
from weasyprint import HTML
from datetime import datetime
from fastapi import HTTPException, Response
from enhancifai_backend.database.handlers.billing import BillingDbCore

from enhancifai_backend.config import settings

REGISTRATION_CONFIRMATION_TEMPLATE = "d-c037b53618264a6caf6d64b653675819"
SOCIAL_ACCOUNT_READY_TEMPLATE = "d-0b74381cc5f2401e94321a6c166e2d9b"
PASSWORD_RESET_TEMPLATE = "d-75c53f9a77304ae480856b429ef8ff7c"

BILLING_INVOICE_READY = "d-b8e31bce0613459188bb69813cd40be6"
BILLING_INVOICE_PAYMENT_SUCCESS = "d-060257d7c1254441a301792ab484d445"

class SendGrid:

    @classmethod
    def send_registration_email(cls, to_email, token, name):
        # create Mail object and populate
        message = Mail(
            from_email="info@enhancifai.com",
            to_emails=[to_email])
        # pass custom values for our HTML placeholders
        activation_url = f'{settings.frontend_url}/auth?email={to_email}&token={token}'
        
        # disable tracking
        tracking_settings = TrackingSettings()
        tracking_settings.click_tracking = ClickTracking(enable=False)
        tracking_settings.open_tracking = OpenTracking(enable=False)
        tracking_settings.subscription_tracking = SubscriptionTracking(enable=True)
        message.tracking_settings = tracking_settings

        message.dynamic_template_data = {
            'login_url': activation_url,
            'name': name
        }
        message.template_id = REGISTRATION_CONFIRMATION_TEMPLATE
        # create our sendgrid client object, pass it our key, then send and return our response objects
        try:
            sg = SendGridAPIClient(settings.sendgrid_api_key)
            response = sg.send(message)
            _code, _body, _headers = response.status_code, response.body, response.headers
            print("Dynamic Messages Sent!")
        except Exception as e:
            print(f"Error: {e}")

    @classmethod
    def send_password_reset_email(cls, to_email, token):
        # create Mail object and populate
        message = Mail(
            from_email="info@enhancifai.com",
            to_emails=[to_email])
        # pass custom values for our HTML placeholders
        reset_url = f'{settings.frontend_url}/auth_password_reset?email={to_email}&token={token}'

        # disable tracking
        tracking_settings = TrackingSettings()
        tracking_settings.click_tracking = ClickTracking(enable=False)
        tracking_settings.open_tracking = OpenTracking(enable=False)
        tracking_settings.subscription_tracking = SubscriptionTracking(enable=True)
        message.tracking_settings = tracking_settings

        message.dynamic_template_data = {
            'reset_url': reset_url
        }
        message.template_id = PASSWORD_RESET_TEMPLATE
        # create our sendgrid client object, pass it our key, then send and return our response objects
        try:
            sg = SendGridAPIClient(settings.sendgrid_api_key)
            response = sg.send(message)
            _code, _body, _headers = response.status_code, response.body, response.headers
            print("Dynamic Messages Sent!")
        except Exception as e:
            print(f"Error: {e}")

    @classmethod
    def send_invoice_email(cls, to_email, user_name, invoice_month, invoice_year, invoice_id, user_id):
        logging.debug(f"Preparing to send invoice email to {to_email}")
        # create Mail object and populate
        message = Mail(
            from_email="info@enhancifai.com",
            to_emails=[to_email])
        logging.debug("Mail object created")
        
        # pass custom values for our HTML placeholders
        button_url = f'{settings.frontend_url}/billings'
        logging.debug(f"Button URL: {button_url}")

        # disable tracking
        tracking_settings = TrackingSettings()
        tracking_settings.click_tracking = ClickTracking(enable=False)
        tracking_settings.open_tracking = OpenTracking(enable=False)
        tracking_settings.subscription_tracking = SubscriptionTracking(enable=True)
        message.tracking_settings = tracking_settings
        
        message.dynamic_template_data = {
            'button_url': button_url,
            'user_name': user_name,
            'invoice_month': invoice_month,
            'invoice_year': invoice_year
        }
        logging.debug(f"Dynamic template data: {message.dynamic_template_data}")
        
        message.template_id = BILLING_INVOICE_READY
        logging.debug(f"Template ID set to {BILLING_INVOICE_READY}")
        
        # Download the invoice PDF
        pdf_data = cls._download_invoice_pdf(user_id, invoice_id)
        logging.debug("Invoice PDF downloaded")

        # Attach the PDF to the email
        encoded_pdf = base64.b64encode(pdf_data).decode()
        attachment = Attachment(
            file_content=encoded_pdf,
            file_name=f"Invoice_{invoice_month}_{invoice_year}.pdf",
            file_type="application/pdf",
            disposition="attachment"
        )
        message.attachment = attachment
        logging.debug("PDF attached to the email")
        
        # create our sendgrid client object, pass it our key, then send and return our response objects
        try:
            sg = SendGridAPIClient(settings.sendgrid_api_key)
            logging.debug("SendGridAPIClient created")
            response = sg.send(message)
            _code, _body, _headers = response.status_code, response.body, response.headers
            logging.debug(f"Email sent with status code: {_code}")
            logging.debug(f"Response body: {_body}")
            logging.debug(f"Response headers: {_headers}")
            print("Dynamic Messages Sent!")
        except Exception as e:
            logging.error(f"Error sending email: {e}")

    @classmethod
    def send_invoice_payment_success_email(cls, to_email, user_name, invoice_month, invoice_year, invoice_id, user_id):
        # create Mail object and populate
        message = Mail(
            from_email="info@enhancifai.com",
            to_emails=[to_email])
        logging.debug("Mail object created")
        
        # pass custom values for our HTML placeholders
        button_url = f'{settings.frontend_url}/billings'
        logging.debug(f"Button URL: {button_url}")

        # disable tracking
        tracking_settings = TrackingSettings()
        tracking_settings.click_tracking = ClickTracking(enable=False)
        tracking_settings.open_tracking = OpenTracking(enable=False)
        tracking_settings.subscription_tracking = SubscriptionTracking(enable=True)
        message.tracking_settings = tracking_settings
        
        message.dynamic_template_data = {
            'button_url': button_url,
            'user_name': user_name,
            'invoice_month': invoice_month,
            'invoice_year': invoice_year
        }
        logging.debug(f"Dynamic template data: {message.dynamic_template_data}")
        
        message.template_id = BILLING_INVOICE_PAYMENT_SUCCESS
        logging.debug(f"Template ID set to {BILLING_INVOICE_PAYMENT_SUCCESS}")
        
        # Download the invoice PDF
        pdf_data = cls._download_invoice_pdf(user_id, invoice_id)
        logging.debug("Invoice PDF downloaded")

        # Attach the PDF to the email
        encoded_pdf = base64.b64encode(pdf_data).decode()
        attachment = Attachment(
            file_content=encoded_pdf,
            file_name=f"Invoice_{invoice_month}_{invoice_year}.pdf",
            file_type="application/pdf",
            disposition="attachment"
        )
        message.attachment = attachment
        logging.debug("PDF attached to the email")
        
        # create our sendgrid client object, pass it our key, then send and return our response objects
        try:
            sg = SendGridAPIClient(settings.sendgrid_api_key)
            logging.debug("SendGridAPIClient created")
            response = sg.send(message)
            _code, _body, _headers = response.status_code, response.body, response.headers
            logging.debug(f"Email sent with status code: {_code}")
            logging.debug(f"Response body: {_body}")
            logging.debug(f"Response headers: {_headers}")
            print("Dynamic Messages Sent!")
        except Exception as e:
            logging.error(f"Error sending email: {e}")

    @classmethod
    def send_invoice_payment_failure_email(cls, to_email):
        pass

    @classmethod
    def send_subscription_start_email(cls, to_email):
        pass

    @classmethod
    def _download_invoice_pdf(cls, user_id: int, invoice_id: str) -> bytes:
        """
        Download an invoice as a PDF file with itemized details.
        """
        try:
            invoice = BillingDbCore.get_invoice_by_id(user_id, invoice_id)
            if not invoice:
                raise HTTPException(status_code=404, detail="Invoice not found.")

            invoice_number = invoice['invoice_id']
            date_issued_raw = invoice['date']
            date_issued = datetime.fromisoformat(date_issued_raw.replace('Z', '+00:00')).strftime('%B %d, %Y')
            amount = invoice['invoice_amount']
            status = invoice['payment_status']
            payment_date_raw = invoice.get('payment_date')
            payment_date = datetime.fromisoformat(payment_date_raw.replace('Z', '+00:00')).strftime('%B %d, %Y') if payment_date_raw else ""
            billing_period_start_raw = invoice.get('billing_period_start')
            billing_period_end_raw = invoice.get('billing_period_end')
            billing_period_start = datetime.fromisoformat(billing_period_start_raw).strftime('%B %d, %Y') if billing_period_start_raw else ""
            billing_period_end = datetime.fromisoformat(billing_period_end_raw).strftime('%B %d, %Y') if billing_period_end_raw else ""
            metadata = invoice.get('metadata', {})
            description = metadata.get('description', 'N/A')
            status_color_map = {'paid': '#28a745', 'unpaid': '#dc3545'}
            status_color = status_color_map.get(status, '#000000')
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
            return pdf
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
