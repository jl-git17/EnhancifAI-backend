import logging
from datetime import datetime, timedelta, date, time
from decimal import Decimal
import json
from enhancifai_backend.database.access import read_db, write_db
from enhancifai_backend.database.handlers.billing import BillingDbCore
from enhancifai_backend.database.handlers.users import UsersDbCore
from enhancifai_backend.database.handlers.utils import schemafy

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def calculate_amount(tokens_standard: int, tokens_pi: int, rate_standard: Decimal, rate_pi: Decimal) -> int:
    """
    Calculate the total amount based on standard and PI tokens used.
    Returns the amount in cents.
    """
    if tokens_standard < 0 or tokens_pi < 0:
        raise ValueError("Token counts cannot be negative.")

    amount_standard = Decimal(tokens_standard) * rate_standard
    amount_pi = Decimal(tokens_pi) * rate_pi
    total_amount = amount_standard + amount_pi
    return int(total_amount * 100)  # Convert to cents

def get_user_token_usage_pi(user_id: int, start_date: datetime, end_date: datetime) -> int:
    """
    Retrieve the total number of PI tokens used by the user in the specified period.
    """
    try:
        sql = schemafy("""
            SELECT SUM(tokens) AS total_tokens
            FROM enhancifai.users_token_usage_pi
            WHERE user_id = %s
              AND created_at >= %s
              AND created_at < %s;
        """)
        data = (user_id, start_date, end_date)
        result = read_db.do('select_one', sql=sql, data=data)
        return result['total_tokens'] if result and result['total_tokens'] else 0
    except Exception as e:
        logger.error(
            "Error fetching PI token usage for user %s: %s",
            user_id,
            str(e),
            exc_info=True
        )
        return 0

def generate_monthly_invoices():
    """
    Generate monthly invoices for all users based on their token usage.
    If a user has no invoices, generate invoices monthly from their date of joining.
    Otherwise, generate an invoice for the last month only.
    Stores invoice details in the database without making any Stripe API calls.
    """
    try:
        # Determine the start and end of the previous month as datetime.datetime objects
        today = datetime.today()
        first_day_of_current_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_day_of_previous_month = first_day_of_current_month - timedelta(days=1)
        first_day_of_previous_month = last_day_of_previous_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        logger.info(
            "Generating invoices up to the period: %s to %s",
            first_day_of_previous_month,
            first_day_of_current_month
        )

        # Fetch all users
        sql = schemafy("SELECT user_id FROM enhancifai.users;")
        users = read_db.do('select', sql=sql)

        logger.info("Fetched %s users from the database.", len(users))

        for user in users:
            user_id = user['user_id']
            try:
                # Check if any invoice exists for this user
                any_invoice = BillingDbCore.has_any_invoice(user_id)

                if not any_invoice:
                    # User has no invoices, generate invoices from joining date
                    date_joined = UsersDbCore.get_date_joined(user_id)
                    if not date_joined:
                        logger.error(
                            "Could not retrieve date of joining for user %s. Skipping.",
                            user_id
                        )
                        continue  # Skip if date of joining is unavailable

                    # Convert date_joined to datetime at midnight if it's a date object
                    if isinstance(date_joined, date):
                        date_joined = datetime.combine(date_joined, time.min)

                    # Ensure date_joined is datetime.datetime
                    if not isinstance(date_joined, datetime):
                        logger.error(
                            "Invalid date_joined type for user %s. Skipping.",
                            user_id
                        )
                        continue  # Skip if date_joined is not datetime.datetime

                    # Normalize to first day of joining month at midnight
                    current_start = date_joined.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                else:
                    # User has existing invoices, generate invoice for last month only
                    current_start = first_day_of_previous_month

                # Determine the end date for invoice generation
                while current_start <= first_day_of_previous_month:
                    # Calculate the first day of the next month
                    if current_start.month == 12:
                        next_month = 1
                        next_year = current_start.year + 1
                    else:
                        next_month = current_start.month + 1
                        next_year = current_start.year
                    current_end = current_start.replace(year=next_year, month=next_month, day=1)

                    # Adjust if current_end exceeds the last day to invoice
                    if current_end > first_day_of_current_month:
                        current_end = first_day_of_current_month

                    logger.info(
                        "Generating invoice for user %s for period: %s to %s",
                        user_id,
                        current_start.strftime('%Y-%m-%d'),
                        current_end.strftime('%Y-%m-%d')
                    )

                    # Check if an invoice already exists for this period
                    invoice_exists = BillingDbCore.invoice_exists(
                        user_id, current_start, current_end
                    )

                    if invoice_exists:
                        logger.info(
                            "User %s already has an invoice for %s to %s. Skipping.",
                            user_id,
                            current_start.strftime('%Y-%m-%d'),
                            current_end.strftime('%Y-%m-%d')
                        )
                    else:
                        # Get total standard tokens used by the user in the billing period
                        tokens_standard = UsersDbCore.get_user_token_usage(
                            user_id, current_start, current_end
                        )

                        # Get total PI tokens used by the user in the billing period
                        tokens_pi = get_user_token_usage_pi(
                            user_id, current_start, current_end
                        )

                        total_tokens = tokens_standard + tokens_pi

                        if total_tokens <= 0:
                            logger.info(
                                "User %s has no token usage for %s to %s. Skipping invoice.",
                                user_id,
                                current_start.strftime('%Y-%m-%d'),
                                current_end.strftime('%Y-%m-%d')
                            )
                        else:
                            # Fetch rates from the database
                            rate_standard = BillingDbCore.get_price_per_token(
                                model_name='standard',
                                effective_date=current_start
                            )
                            rate_pi = BillingDbCore.get_price_per_token(
                                model_name='pi',
                                effective_date=current_start
                            )

                            if rate_standard is None or rate_pi is None:
                                logger.error(
                                    "Missing pricing information for user %s for period %s to %s. Skipping invoice.",
                                    user_id,
                                    current_start.strftime('%Y-%m-%d'),
                                    current_end.strftime('%Y-%m-%d')
                                )
                            else:
                                # Calculate the amount due in cents
                                amount_cents = calculate_amount(
                                    tokens_standard, tokens_pi, rate_standard, rate_pi
                                )
                                description = (
                                    f"Monthly token usage: {tokens_standard} standard tokens and "
                                    f"{tokens_pi} PI tokens for {current_start.strftime('%B %Y')}"
                                )

                                # Store the invoice in the database
                                invoice = BillingDbCore.create_invoice(
                                    user_id, amount_cents, description, current_start, current_end
                                )
                                logger.info(
                                    "Stored invoice %s for user %s: $%.2f",
                                    invoice['id'],
                                    user_id,
                                    invoice['amount']
                                )

                    # Move to the next month
                    current_start = current_end

            except Exception as e:
                # Log the error and continue with other users
                logger.error(
                    "Failed to create invoice for user %s: %s",
                    user_id,
                    str(e),
                    exc_info=True
                )
    except Exception as e:
        logger.critical(
            "Failed to generate monthly invoices: %s",
            str(e),
            exc_info=True
        )

if __name__ == "__main__":
    generate_monthly_invoices()
