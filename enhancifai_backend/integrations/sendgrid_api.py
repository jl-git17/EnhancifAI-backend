from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Mail,
    Asm,
    IpPoolName,
    TrackingSettings,
    ClickTracking,
    OpenTracking,
    SubscriptionTracking
)
import logging  # Add logging import

from enhancifai_backend.config import settings

REGISTRATION_CONFIRMATION_TEMPLATE = "d-c037b53618264a6caf6d64b653675819"
SOCIAL_ACCOUNT_READY_TEMPLATE = "d-0b74381cc5f2401e94321a6c166e2d9b"
PASSWORD_RESET_TEMPLATE = "d-75c53f9a77304ae480856b429ef8ff7c"

BILLING_INVOICE_READY = "d-b8e31bce0613459188bb69813cd40be6"

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
    def send_invoice_email(cls, to_email, user_name, invoice_month, invoice_year):
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
    def send_invoice_payment_success_email(cls, to_email):
        pass

    @classmethod
    def send_invoice_payment_failure_email(cls, to_email):
        pass

    @classmethod
    def send_subscription_start_email(cls, to_email):
        pass
