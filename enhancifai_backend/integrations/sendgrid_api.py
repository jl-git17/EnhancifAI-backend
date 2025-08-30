import logging

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Mail,
    TrackingSettings,
    ClickTracking,
    OpenTracking,
    SubscriptionTracking
)

from enhancifai_backend.config import settings

REGISTRATION_CONFIRMATION_TEMPLATE = "d-c037b53618264a6caf6d64b653675819"

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
        except Exception as e:
            logging.error("Error: %s", e)
