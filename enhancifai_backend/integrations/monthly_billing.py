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

def generate_monthly_invoices():
    """
    Generate monthly invoices for all users based on their token usage per model.
    Calculates cost for every token usage and sums it up.
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
                        # Get total tokens used per model by the user in the billing period
                        tokens_per_model = UsersDbCore.get_user_token_usage_per_model(
                            user_id, current_start, current_end
                        )

                        if not tokens_per_model:
                            logger.info(
                                "User %s has no token usage for %s to %s. Skipping invoice.",
                                user_id,
                                current_start.strftime('%Y-%m-%d'),
                                current_end.strftime('%Y-%m-%d')
                            )
                        else:
                            total_amount_cents = 0
                            description_lines = []
                            for usage in tokens_per_model:
                                model = usage['model']
                                tokens = usage['total_tokens']
                                rate = BillingDbCore.get_price_per_token(
                                    model_name=model,
                                    effective_date=current_start
                                )
                                if rate is None:
                                    logger.error(
                                        "Missing pricing information for model %s used by user %s for period %s to %s. Skipping this model.",
                                        model,
                                        user_id,
                                        current_start.strftime('%Y-%m-%d'),
                                        current_end.strftime('%Y-%m-%d')
                                    )
                                    continue  # Skip this model if rate is missing
                                amount_cents = int(Decimal(tokens) * Decimal(rate) * 100)
                                total_amount_cents += amount_cents
                                description_lines.append(
                                    f"{tokens} tokens of {model} at ${Decimal(rate):.6f} per token"
                                )

                            if total_amount_cents <= 0:
                                logger.info(
                                    "User %s has no billable token usage for %s to %s. Skipping invoice.",
                                    user_id,
                                    current_start.strftime('%Y-%m-%d'),
                                    current_end.strftime('%Y-%m-%d')
                                )
                            else:
                                description = "Monthly token usage for {}: {}".format(
                                    current_start.strftime('%B %Y'),
                                    "; ".join(description_lines)
                                )

                                # Store the invoice in the database
                                invoice = BillingDbCore.create_invoice(
                                    user_id, total_amount_cents, description, current_start, current_end
                                )
                                logger.info(
                                    "Stored invoice %s for user %s: $%.2f",
                                    invoice['id'],
                                    user_id,
                                    invoice['amount'] / 100  # Convert cents to dollars
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
