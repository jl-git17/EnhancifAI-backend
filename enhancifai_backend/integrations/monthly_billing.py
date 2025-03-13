from datetime import datetime, timedelta, date, time, timezone
from decimal import Decimal
import logging
import calendar

import stripe

from enhancifai_backend.config import settings
from enhancifai_backend.database.handlers.billing import BillingDbCore
from enhancifai_backend.database.handlers.stripe import StripeDbCore
from enhancifai_backend.database.handlers.users import UsersDbCore
from enhancifai_backend.integrations.sendgrid_api import SendGrid

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_one_month(dt):
    """
    Returns a new datetime that is one month after the given datetime (dt).

    If the resulting month has fewer days than dt.day, the day is adjusted to the
    last valid day of the month.

    Parameters:
        dt (datetime): The original datetime.

    Returns:
        datetime: The datetime incremented by one month.
    """
    year = dt.year + (dt.month // 12)
    month = dt.month % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)

def create_and_charge_invoice(
        user_id: int,
        invoice_id: str,
        invoice_month: str,
        invoice_year: int,
        amount: int, currency: str = "usd",
        description: str = "Monthly token usage",
    ):
    """
    Automatically create and charge a Stripe invoice when an internal invoice is created.
    """
    print(
        f"[DEBUG] create_and_charge_invoice called with user_id={user_id}, "
        f"amount={amount}, currency={currency}"
    )
    try:
        customer_id = BillingDbCore.get_stripe_customer_id(user_id)
        if not customer_id:
            raise ValueError(f"No Stripe customer ID found for user {user_id}")

        customer = stripe.Customer.retrieve(customer_id)

        # Attempt to retrieve the default payment method
        default_pm = customer.invoice_settings.get("default_payment_method")

        # Fallback: If no default payment method is set, list attached payment methods and pick the first one.
        if not default_pm:
            payment_methods = stripe.PaymentMethod.list(
                customer=customer_id,
                type="card"
            )
            if payment_methods.data:
                default_pm = payment_methods.data[0].id
                print(f"[DEBUG] Fallback: Using attached payment method {default_pm}")
            else:
                raise ValueError(f"User {user_id} does not have any saved payment methods.")

        payment_intent = stripe.PaymentIntent.create(
            amount=amount,  # Amount in cents
            currency=currency,
            customer=customer_id,
            payment_method=default_pm,
            confirm=True,
            off_session=True,  # Charges the customer without their confirmation
            description=description
        )
        print(f"[DEBUG] Successfully charged user {user_id}, PaymentIntent ID: {payment_intent['id']}")

        # Record the payment (status updated to "charged")
        StripeDbCore.store_invoice_record(user_id, invoice_id, amount, "charged")
        # Update the invoice as paid
        BillingDbCore.update_invoice_status(invoice_id, "paid")
        # Send an email to the user
        user = UsersDbCore.get_user_by_id(user_id)
        SendGrid.send_invoice_payment_success_email(
            to_email=user['email'],
            user_name=user['name'],
            invoice_month=invoice_month,
            invoice_year=invoice_year,
            invoice_id=invoice_id,
            user_id=user_id
        )
        # temporarily send failure email for testing
        SendGrid.send_invoice_payment_failure_email(
            to_email=user['email'],
            user_name=user['name'],
            invoice_month=invoice_month,
            invoice_year=invoice_year,
            invoice_id=invoice_id,
            user_id=user_id
        )
        return payment_intent
    except Exception as e:
        print(f"Error charging customer: {str(e)}")
        SendGrid.send_invoice_payment_failure_email(
            to_email=user['email'],
            user_name=user['name'],
            invoice_month=invoice_month,
            invoice_year=invoice_year,
            invoice_id=invoice_id,
            user_id=user_id
        )


def generate_monthly_invoices():
    """
    Generates monthly invoices for all users based on their token usage.

    For each user, the function determines the billing period using the date of the last issued invoice
    or the user's join date, up to the end of the previous month. It then processes both normal and PI token
    usages. Detailed invoices are created if token consumption is detected, and the invoice run timestamp is updated.

    Raises:
        Logs errors and continues processing on individual user failures.
    """
    print("[DEBUG] Starting generate_monthly_invoices")
    try:
        today = datetime.now(timezone.utc)
        first_day_of_current_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_day_of_previous_month = (first_day_of_current_month - timedelta(days=1)).replace(
            hour=23, minute=59, second=59, microsecond=999999
        )

        users = UsersDbCore.get_all_user_ids()
        print(f"[DEBUG] Retrieved all users: {len(users)} total")

        for user_id in users:
            print(f"[DEBUG] Processing user_id={user_id}")
            if not StripeDbCore.is_user_subscribed(user_id) and not StripeDbCore.is_user_subscribed_cancelled(user_id):
                continue
            invoices_generated = False
            try:
                last_invoice_end_date = BillingDbCore.get_last_invoice_end_date(user_id)
                print(f"[DEBUG] Last invoice end date: {last_invoice_end_date}")
                if last_invoice_end_date:
                    current_start = last_invoice_end_date + timedelta(days=1)
                    if isinstance(current_start, date) and not isinstance(current_start, datetime):
                        current_start = datetime.combine(current_start, time.min, tzinfo=timezone.utc)
                    if current_start.tzinfo is None:
                        current_start = current_start.replace(tzinfo=timezone.utc)
                else:
                    # Use billing start from settings with a fixed year 2025.
                    billing_start_str = str(settings.billing_start)
                    if billing_start_str:
                        try:
                            billing_start_year, billing_start_month, billing_start_day = map(int, billing_start_str.split('-'))
                        except Exception as e:
                            logger.error(
                                "Invalid BILLING_START format: %s. Expected 'MM-DD'. Error: %s",
                                billing_start_str, str(e)
                            )
                            continue
                    else:
                        billing_start_year, billing_start_month, billing_start_day = 2025, 3, 1
                    current_start = datetime(billing_start_year, billing_start_month, billing_start_day, 0, 0, 0, tzinfo=timezone.utc)

                print(f"[DEBUG] Current start: {current_start}, last day of previous month: {last_day_of_previous_month}")
                if current_start > last_day_of_previous_month:
                    continue

                while current_start <= last_day_of_previous_month:
                    last_day = calendar.monthrange(current_start.year, current_start.month)[1]
                    current_end = current_start.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)

                    if current_end > last_day_of_previous_month:
                        current_end = last_day_of_previous_month

                    print(f"[DEBUG] Checking invoices for range {current_start} to {current_end}")
                    invoice_exists = BillingDbCore.invoice_exists(user_id, current_start, current_end)
                    if not invoice_exists:
                        normal_tokens_per_model_per_day = UsersDbCore.get_user_normal_token_usage_per_model_per_day(
                            user_id, current_start, current_end
                        )

                        pi_tokens_per_model_per_day = UsersDbCore.get_user_pi_token_usage_per_model_per_day(
                            user_id, current_start, current_end
                        )

                        # Now process normal tokens and PI tokens separately
                        normal_line_items = []
                        pi_line_items = []
                        total_amount_cents = Decimal(0)

                        print(f"[DEBUG] Normal usage records: {normal_tokens_per_model_per_day}")
                        print(f"[DEBUG] PI usage records: {pi_tokens_per_model_per_day}")
                        for usage in normal_tokens_per_model_per_day:
                            usage_date = usage['usage_date']
                            model = usage['model']
                            tokens = usage['total_tokens']
                            rate = BillingDbCore.get_price_per_token(
                                model_name=model, year=usage_date.year, month=usage_date.month
                            )

                            if rate is None:
                                logger.error(
                                    "Missing pricing info for model %s on %s (user %s).",
                                    model,
                                    usage_date.strftime('%Y-%m-%d'),
                                    user_id
                                )
                                continue  # Skip this usage record only.
                            amount_cents = Decimal(tokens) * Decimal(rate) * 100
                            total_amount_cents += amount_cents
                            normal_line_items.append({
                                'date': usage_date.strftime('%Y-%m-%d'),
                                'model': model,
                                'tokens': tokens,
                                'rate': float(rate),
                                'amount': float(amount_cents) / 100.0
                            })

                        for usage in pi_tokens_per_model_per_day:
                            usage_date = usage['usage_date']
                            model = usage['model']
                            tokens = usage['total_tokens']
                            rate = BillingDbCore.get_price_per_token(
                                model_name=model, year=usage_date.year, month=usage_date.month
                            )

                            if rate is None:
                                logger.error(
                                    "Missing pricing info for PI model %s on %s (user %s).",
                                    model,
                                    usage_date.strftime('%Y-%m-%d'),
                                    user_id
                                )
                                continue  # Skip this record only.
                            amount_cents = Decimal(tokens) * Decimal(rate) * 100
                            total_amount_cents += amount_cents
                            pi_line_items.append({
                                'date': usage_date.strftime('%Y-%m-%d'),
                                'model': model,
                                'tokens': tokens,
                                'rate': float(rate),
                                'amount': float(amount_cents) / 100.0
                            })
                        
                        _total_amount_cents = total_amount_cents.quantize(Decimal('1'))

                        if _total_amount_cents > 0:
                            description = f"Monthly token usage for {current_start.strftime('%B %Y')}"
                            metadata_dict = {
                                'description': description,
                                'line_items': normal_line_items,
                                'pi_line_items': pi_line_items,
                                'invoice_month': current_start.strftime('%B'),
                                'invoice_year': current_start.year
                            }
                            print(f"[DEBUG] Creating invoice with amount (cents): {_total_amount_cents}")
                            invoice = BillingDbCore.create_invoice(
                                user_id, _total_amount_cents, description,
                                current_start.date(), current_end.date(), metadata=metadata_dict
                            )
                            if invoice:
                                invoices_generated = True
                                print(f"[DEBUG] Invoice creation successful: {invoice}")
                                user = UsersDbCore.get_user_by_id(user_id)
                                SendGrid.send_invoice_email(
                                    to_email=user['email'],
                                    user_name=user['name'],
                                    invoice_month=current_start.strftime('%B'),
                                    invoice_year=current_start.year,
                                    invoice_id=invoice['invoice_id'],
                                    user_id=user_id
                                )

                    current_start = add_one_month(current_start)

                if invoices_generated:
                    current_timestamp = datetime.now(timezone.utc)
                    BillingDbCore.update_last_invoice_run(user_id, current_timestamp)

            except Exception as e:
                logger.error("Failed to create invoice for user %s: %s", user_id, str(e), exc_info=True)
    except Exception as e:
        logger.critical("Failed to generate monthly invoices: %s", str(e), exc_info=True)
    print("[DEBUG] Finished generate_monthly_invoices")

def charge_unpaid_invoices():
    """
    Loops through unpaid internal_invoices and attempts to charge them.
    """
    try:
        unpaid_invoices = BillingDbCore.list_unpaid_invoices()
        for invoice in unpaid_invoices:
            user_id = invoice['user_id']
            # Retrieve the subscription charge date
            subscription_charge_date = BillingDbCore.get_user_subscription_charge_date(user_id)
            today = datetime.now(timezone.utc).date()
            print(f"[DEBUG] Checking invoice for user {user_id} with charge date {subscription_charge_date}")
            print(f"[DEBUG] Today's date: {today}")
            print(f"[DEBUG] Today type: {type(today)},  charge date type: {type(subscription_charge_date)}")
            # Check if today's date is the subscription charge date; skip if not.
            if subscription_charge_date is None or subscription_charge_date != today:
                continue

            invoice_id = invoice['invoice_id']
            metadata = invoice['metadata']
            # invoice['amount'] is in dollars; convert to cents for charging
            amount_cents = int(round(invoice['amount'] * 100))
            try:
                current_retry = invoice.get('retry_attempt', 0)
                first_retry_at = invoice.get('first_retry_at')
                second_retry_at = invoice.get('second_retry_at')
                now = datetime.now(timezone.utc)
                should_charge = False
                if current_retry == 0:
                    should_charge = True
                elif current_retry == 1 and first_retry_at and now >= first_retry_at:
                    should_charge = True
                elif current_retry == 2 and first_retry_at and now >= first_retry_at + timedelta(hours=4):
                    should_charge = True
                elif current_retry == 3 and second_retry_at and now >= second_retry_at:
                    should_charge = True
                elif current_retry == 4 and second_retry_at and now >= second_retry_at + timedelta(hours=4):
                    should_charge = True

                print(f"[DEBUG] current_retry={current_retry}, should_charge={should_charge}")

                if should_charge:
                    create_and_charge_invoice(
                        user_id=user_id,
                        invoice_id=invoice_id,
                        amount=amount_cents,
                        currency="usd",
                        description=metadata['description'],
                        invoice_month=metadata['invoice_month'],
                        invoice_year=metadata['invoice_year']
                    )
            except Exception as e:
                logger.error("Failed to charge invoice %s for user %s: %s", invoice_id, user_id, str(e))
                # Implement invoice retry logic
                current_retry = invoice.get('retry_attempt', 0) + 1
                now_retry = datetime.now(timezone.utc)
                if current_retry == 1:
                    first_retry_at = now_retry + timedelta(days=1)
                    second_retry_at = now_retry + timedelta(days=2)
                    service_cutoff_at = now_retry + timedelta(days=14)
                    BillingDbCore.update_stripe_invoice_retry_info(
                        invoice_id,
                        current_retry,
                        first_retry_at,
                        second_retry_at,
                        service_cutoff_at
                    )
                else:
                    BillingDbCore.add_stripe_invoice_retry_count(invoice_id)
    except Exception as e:
        logger.error("Failed to retrieve or charge unpaid invoices: %s", str(e))

def send_invoice_emails():
    try:
        unpaid_invoices = BillingDbCore.list_unpaid_invoices()
        for invoice in unpaid_invoices:
            if invoice['email_sent']:
                continue
            user_id = invoice['user_id']
            invoice_id = invoice['invoice_id']
            metadata = invoice['metadata']
            user = UsersDbCore.get_user_by_id(user_id)
            SendGrid.send_invoice_email(
                to_email=user['email'],
                user_name=user['name'],
                invoice_month=metadata['invoice_month'],
                invoice_year=metadata['invoice_year'],
                invoice_id=invoice_id,
                user_id=user_id
            )
            BillingDbCore.mark_internal_invoice_email_sent(invoice_id)
    except Exception as e:
        logger.error("Failed to send invoice emails: %s", str(e))


if __name__ == "__main__":
    generate_monthly_invoices()
