import logging
from datetime import datetime, timedelta
from decimal import Decimal
from enhancifai_backend.database.access import read_db
from enhancifai_backend.database.handlers.billing import BillingDbCore
from enhancifai_backend.database.handlers.users import UsersDbCore
from enhancifai_backend.database.handlers.utils import schemafy
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def calculate_amount(tokens_standard: int, tokens_pi: int, rate_standard: Decimal, rate_pi: Decimal) -> int:
    """
    Calculate the total amount based on standard and PI tokens used.
    Returns the amount in cents.

    Args:
        tokens_standard (int): Number of standard tokens used.
        tokens_pi (int): Number of PI tokens used.
        rate_standard (Decimal): Price per standard token.
        rate_pi (Decimal): Price per PI token.

    Returns:
        int: Total amount in cents.
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

    Args:
        user_id (int): The user's ID.
        start_date (datetime): Start of the billing period.
        end_date (datetime): End of the billing period.

    Returns:
        int: Total PI tokens used.
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
        # Determine the start and end of the previous month
        today = datetime.today().date()
        first_day_of_current_month = today.replace(day=1)
        last_day_of_previous_month = first_day_of_current_month - timedelta(days=1)
        first_day_of_previous_month = last_day_of_previous_month.replace(day=1)

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
                            f"Could not retrieve date of joining for user {user_id}. Skipping."
                        )
                        continue  # Skip if date of joining is unavailable

                    # Convert date_joined to date if it's datetime.datetime
                    if isinstance(date_joined, datetime):
                        date_joined = date_joined.date()

                    # Normalize to first day of joining month
                    current_start = date_joined.replace(day=1)
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
                    current_end = datetime(next_year, next_month, 1).date()

                    # Adjust if current_end exceeds the last day to invoice
                    if current_end > first_day_of_current_month:
                        current_end = first_day_of_current_month

                    logger.info(
                        f"Generating invoice for user {user_id} for period: {current_start} to {current_end}"
                    )

                    # Check if an invoice already exists for this period
                    invoice_exists = BillingDbCore.invoice_exists(
                        user_id, current_start, current_end
                    )

                    if invoice_exists:
                        logger.info(
                            f"User {user_id} already has an invoice for {current_start} to {current_end}. Skipping."
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
                                f"User {user_id} has no token usage for {current_start} to {current_end}. Skipping invoice."
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
                                    f"Missing pricing information for user {user_id} for period {current_start} to {current_end}. Skipping invoice."
                                )
                                continue  # Skip if pricing information is missing

                            # Calculate the amount due in cents
                            amount_cents = calculate_amount(tokens_standard, tokens_pi, rate_standard, rate_pi)
                            description = (
                                f"Monthly token usage: {tokens_standard} standard tokens and "
                                f"{tokens_pi} PI tokens for {current_start.strftime('%B %Y')}"
                            )

                            # Store the invoice in the database
                            invoice = BillingDbCore.create_invoice(
                                user_id, amount_cents, description, current_start, current_end
                            )
                            logger.info(
                                f"Stored invoice {invoice['id']} for user {user_id}: ${invoice['amount']}"
                            )

                    # Move to the next month
                    current_start = current_end

            except Exception as e:
                # Log the error and continue with other users
                logger.error(
                    f"Failed to create invoice for user {user_id}: {str(e)}",
                    exc_info=True
                )
    except Exception as e:
        # Handle exceptions
        logger.error(f"An error occurred: {e}", exc_info=True)

if __name__ == "__main__":
    generate_monthly_invoices()
