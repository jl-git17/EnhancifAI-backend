
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from enhancifai_backend.database.access import read_db
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
    Generate monthly invoices for all users based on their token usage in the previous month.
    Stores invoice details in the database without making any Stripe API calls.
    """
    try:
        # Determine the start and end of the previous month
        today = datetime.today().date()
        first_day_of_current_month = today.replace(day=1)
        last_day_of_previous_month = first_day_of_current_month - timedelta(days=1)
        first_day_of_previous_month = last_day_of_previous_month.replace(day=1)

        logger.info(
            "Generating invoices for the period: %s to %s",
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
                # Check if an invoice already exists for this billing period
                invoice_exists = BillingDbCore.invoice_exists(
                    user_id, first_day_of_previous_month, first_day_of_current_month
                )

                if invoice_exists:
                    logger.info(
                        "User %s has already received an invoice for this period. Skipping.",
                        user_id
                    )
                    continue  # Skip users who already have an invoice for this period

                # Get total standard tokens used by the user in the previous month
                tokens_standard = UsersDbCore.get_user_token_usage(
                    user_id, first_day_of_previous_month, first_day_of_current_month
                )

                # Get total PI tokens used by the user in the previous month
                tokens_pi = get_user_token_usage_pi(
                    user_id, first_day_of_previous_month, first_day_of_current_month
                )

                total_tokens = tokens_standard + tokens_pi

                if total_tokens <= 0:
                    logger.info(
                        "User %s has no token usage for the month. Skipping invoice.",
                        user_id
                    )
                    continue  # Skip users with no token usage

                # Fetch rates from the database
                rate_standard = BillingDbCore.get_price_per_token(
                    model_name='standard',
                    effective_date=first_day_of_previous_month
                )
                rate_pi = BillingDbCore.get_price_per_token(
                    model_name='pi',
                    effective_date=first_day_of_previous_month
                )

                if rate_standard is None or rate_pi is None:
                    logger.error(
                        "Missing pricing information for user %s. Skipping invoice.",
                        user_id
                    )
                    continue  # Skip if pricing information is missing

                # Calculate the amount due in cents
                amount_cents = calculate_amount(tokens_standard, tokens_pi, rate_standard, rate_pi)
                description = (
                    f"Monthly token usage: {tokens_standard} standard tokens and "
                    f"{tokens_pi} PI tokens for {first_day_of_previous_month.strftime('%B %Y')}"
                )

                # Store the invoice in the database
                invoice = BillingDbCore.create_invoice(
                    user_id, amount_cents, description, first_day_of_previous_month, first_day_of_current_month
                )
                logger.info(
                    "Stored invoice %s for user %s: $%.2f",
                    invoice['id'],
                    user_id,
                    invoice['amount'] / 100
                )

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
