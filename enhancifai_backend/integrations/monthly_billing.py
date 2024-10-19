import logging
from datetime import datetime, timedelta
from enhancifai_backend.database.access import read_db
from enhancifai_backend.database.handlers.users import UsersDbCore
from enhancifai_backend.database.handlers.stripe import StripeDbCore
from enhancifai_backend.database.handlers.utils import schemafy

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define pricing per token (example: $0.0001 per token)
PRICE_PER_TOKEN = 0.0001  # $0.0001 per token

def calculate_amount(tokens_used: int) -> int:
    """
    Calculate the amount in cents based on tokens used.

    Args:
        tokens_used (int): Number of tokens used.

    Returns:
        int: Amount in cents.
    """
    return int(tokens_used * PRICE_PER_TOKEN * 100)  # Convert to cents

def generate_monthly_invoices():
    """
    Generate monthly invoices for all users based on their token usage in the previous month.
    Ensures that no duplicate invoices are sent for the same billing period.
    """
    try:
        # TODO: put a max cap for day, so it spills over (configurable), put a delay
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
                invoice_exists = StripeDbCore.invoice_exists(
                    user_id, first_day_of_previous_month, first_day_of_current_month
                )

                if invoice_exists:
                    logger.info(
                        "User %s has already received an invoice for this period. Skipping.",
                        user_id
                    )
                    continue  # Skip users who already have an invoice for this period

                # Get total tokens used by the user in the previous month
                tokens_used = UsersDbCore.get_user_token_usage(
                    user_id, first_day_of_previous_month, first_day_of_current_month
                )

                if tokens_used <= 0:
                    logger.info(
                        "User %s has no token usage for the month. Skipping invoice.",
                        user_id
                    )
                    continue  # Skip users with no token usage

                # Calculate the amount due in cents
                amount = calculate_amount(tokens_used)
                description = (
                    f"Monthly token usage: {tokens_used} tokens for "
                    f"{first_day_of_previous_month.strftime('%B %Y')}"
                )

                # Create and send the invoice
                invoice = StripeDbCore.create_invoice(
                    user_id, amount, description, first_day_of_previous_month, first_day_of_current_month
                )
                logger.info(
                    "Created invoice %s for user %s: $%.2f",
                    invoice['id'],
                    user_id,
                    amount / 100
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
