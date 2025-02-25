from datetime import datetime, timedelta, date, time, timezone
from decimal import Decimal
import logging
import calendar

import stripe

from enhancifai_backend.config import settings
from enhancifai_backend.database.access import read_db
from enhancifai_backend.database.handlers.billing import BillingDbCore
from enhancifai_backend.database.handlers.stripe import StripeDbCore
from enhancifai_backend.database.handlers.users import UsersDbCore
from enhancifai_backend.database.handlers.utils import schemafy
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
        user_id: int, invoice_id: str,
        amount: int, currency: str = "usd",
        description: str = "Invoice charge"
    ):
    """
    Automatically create and charge a Stripe invoice when an internal invoice is created.
    """
    print(
        f"[DEBUG] create_and_charge_invoice called with user_id={user_id}, "
        f"amount={amount}, currency={currency}, description='{description}'"
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
        # TODO: send email receipt to user
        return payment_intent
    except Exception as e:
        print(f"Error charging customer: {str(e)}")
        # TODO: send email to user about failed payment


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
        # Temporarily allow invoicing for the current month
        last_day_current = calendar.monthrange(first_day_of_current_month.year, first_day_of_current_month.month)[1]
        last_day_of_current_month = first_day_of_current_month.replace(
            day=last_day_current, hour=23, minute=59, second=59, microsecond=999999
        )

        users = UsersDbCore.get_all_user_ids()
        print(f"[DEBUG] Retrieved all users: {len(users)} total")

        for user_id in users:
            print(f"[DEBUG] Processing user_id={user_id}")
            if not StripeDbCore.is_user_subscribed(user_id):
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
                    billing_start_str = settings.billing_start
                    if billing_start_str:
                        billing_start_str = str(billing_start_str)
                        try:
                            billing_start_month, billing_start_day = map(int, billing_start_str.split('-'))
                        except Exception as e:
                            logger.error(
                                "Invalid BILLING_START format: %s. "
                                "Expected 'MM-DD'. Error: %s",
                                billing_start_str, str(e)
                                )
                            continue
                    else:
                        billing_start_month, billing_start_day = 1, 1  # default to Jan 1 if not set

                    date_joined = UsersDbCore.get_date_joined(user_id)
                    if not date_joined:
                        logger.error("Could not retrieve date of joining for user %s. Skipping.", user_id)
                        continue
                    if date_joined.tzinfo is None:
                        date_joined = date_joined.replace(tzinfo=timezone.utc)
                    # Determine the candidate billing start based on the join year.
                    candidate = datetime(
                        date_joined.year, billing_start_month, billing_start_day,
                        0, 0, 0, tzinfo=timezone.utc
                    )
                    if date_joined > candidate:
                        candidate = datetime(
                            date_joined.year + 1, billing_start_month,
                            billing_start_day, 0, 0, 0, tzinfo=timezone.utc
                        )
                    current_start = candidate
                    if isinstance(date_joined, date) and not isinstance(date_joined, datetime):
                        date_joined = datetime.combine(date_joined, time.min, tzinfo=timezone.utc)
                    current_start = date_joined.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                    if current_start.tzinfo is None:
                        current_start = current_start.replace(tzinfo=timezone.utc)

                print(f"[DEBUG] Current start: {current_start}, last day of current month: {last_day_of_current_month}")
                if current_start > last_day_of_current_month:
                    continue

                while current_start <= last_day_of_current_month:
                    last_day = calendar.monthrange(current_start.year, current_start.month)[1]
                    current_end = current_start.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)

                    if current_end > last_day_of_current_month:
                        current_end = last_day_of_current_month

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
                        total_amount_cents = 0

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
                            amount_cents = (Decimal(tokens) * Decimal(rate) * 100).quantize(Decimal('1'))
                            total_amount_cents += int(amount_cents)
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
                            amount_cents = (Decimal(tokens) * Decimal(rate) * 100).quantize(Decimal('1'))
                            total_amount_cents += int(amount_cents)
                            pi_line_items.append({
                                'date': usage_date.strftime('%Y-%m-%d'),
                                'model': model,
                                'tokens': tokens,
                                'rate': float(rate),
                                'amount': float(amount_cents) / 100.0
                            })

                        if total_amount_cents > 0:
                            description = f"Monthly token usage for {current_start.strftime('%B %Y')}"
                            metadata_dict = {
                                'description': description,
                                'line_items': normal_line_items,
                                'pi_line_items': pi_line_items
                            }
                            print(f"[DEBUG] Creating invoice with amount (cents): {total_amount_cents}")
                            invoice = BillingDbCore.create_invoice(
                                user_id, total_amount_cents, description,
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
                                    invoice_year=current_start.year
                                )
                                create_and_charge_invoice(
                                    user_id,
                                    invoice['invoice_id'],
                                    total_amount_cents,
                                    "usd",
                                    description
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
            invoice_id = invoice['invoice_id']
            # invoice['amount'] is in dollars; convert to cents for charging
            amount_cents = int(round(invoice['amount'] * 100))
            try:
                create_and_charge_invoice(user_id, invoice_id, amount_cents)
                BillingDbCore.update_invoice_status(invoice_id, 'paid')
            except Exception as e:
                logger.error("Failed to charge invoice %s for user %s: %s", invoice_id, user_id, str(e))
    except Exception as e:
        logger.error("Failed to retrieve or charge unpaid invoices: %s", str(e))

if __name__ == "__main__":
    generate_monthly_invoices()
