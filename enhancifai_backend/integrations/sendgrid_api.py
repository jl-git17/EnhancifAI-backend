import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

REGISTRATION_CONFIRMATION_TEMPLATE = "d-c037b53618264a6caf6d64b653675819"
SOCIAL_ACCOUNT_READY_TEMPLATE = "d-0b74381cc5f2401e94321a6c166e2d9b"
PASSWORD_RESET_TEMPLATE = "d-75c53f9a77304ae480856b429ef8ff7c"

class SendGrid:

    @classmethod
    def send_registration_email(cls, to_email, token, name):
        # create Mail object and populate
        message = Mail(
            from_email="info@enhancifai.com",
            to_emails=[to_email])
        # pass custom values for our HTML placeholders
        activation_url = f'{os.getenv("FRONTEND_URL")}/auth?email={to_email}&token={token}'
        message.dynamic_template_data = {
            'login_url': activation_url,
            'name': name
        }
        message.template_id = REGISTRATION_CONFIRMATION_TEMPLATE
        # create our sendgrid client object, pass it our key, then send and return our response objects
        try:
            sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
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
        reset_url = f'{os.getenv("FRONTEND_URL")}/auth_password_reset?email={to_email}&token={token}'
        message.dynamic_template_data = {
            'reset_url': reset_url
        }
        message.template_id = PASSWORD_RESET_TEMPLATE
        # create our sendgrid client object, pass it our key, then send and return our response objects
        try:
            sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
            response = sg.send(message)
            _code, _body, _headers = response.status_code, response.body, response.headers
            print("Dynamic Messages Sent!")
        except Exception as e:
            print(f"Error: {e}")

    @classmethod
    def send_invoice_email(cls, to_email):
        # create Mail object and populate
        message = Mail(
            from_email="info@enhancifai.com",
            to_emails=[to_email])
        # pass custom values for our HTML placeholders
        button_url = f'{os.getenv("FRONTEND_URL")}/billing'
        message.dynamic_template_data = {
            'button_url': button_url
        }
        message.template_id = PASSWORD_RESET_TEMPLATE
        # create our sendgrid client object, pass it our key, then send and return our response objects
        try:
            sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
            response = sg.send(message)
            _code, _body, _headers = response.status_code, response.body, response.headers
            print("Dynamic Messages Sent!")
        except Exception as e:
            print(f"Error: {e}")

    @classmethod
    def send_invoice_payment_success_email(cls, to_email):
        pass

    @classmethod
    def send_invoice_payment_failure_email(cls, to_email):
        pass

    @classmethod
    def send_subscription_start_email(cls, to_email):
        pass