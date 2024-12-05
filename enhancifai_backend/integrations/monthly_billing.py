import logging
from datetime import datetime, timedelta, date, time, timezone
from decimal import Decimal
import calendar
from enhancifai_backend.database.access import read_db
from enhancifai_backend.database.handlers.billing import BillingDbCore
from enhancifai_backend.database.handlers.users import UsersDbCore
from enhancifai_backend.database.handlers.utils import schemafy

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_monthly_invoices():
    """
    Generate monthly invoices for all users starting from the month after the last invoiced month.
    This avoids processing months that have already been invoiced.
    """
    try:
        # Determine the start and end of the previous month using timezone-aware datetime
        today = datetime.now(timezone.utc)
        first_day_of_current_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_day_of_previous_month = first_day_of_current_month - timedelta(seconds=1)
        first_day_of_previous_month = last_day_of_previous_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        logger.info(
            "Generating invoices up to the period: %s to %s",
            first_day_of_previous_month.strftime('%Y-%m-%d'),
            last_day_of_previous_month.strftime('%Y-%m-%d')
        )

        # Fetch all users
        sql = schemafy("SELECT user_id FROM enhancifai.users;")
        users = read_db.do('select', sql=sql)

        logger.info("Fetched %s users from the database.", len(users))

        for user in users:
            user_id = user['user_id']
            try:
                # Get the last invoice end date for the user
                last_invoice_end_date = BillingDbCore.get_last_invoice_end_date(user_id)

                if last_invoice_end_date:
                    # Start from the day after the last invoiced period
                    current_start = last_invoice_end_date + timedelta(days=1)

                    # Ensure current_start is a datetime.datetime object at midnight UTC
                    if isinstance(current_start, date) and not isinstance(current_start, datetime):
                        current_start = datetime.combine(current_start, time.min, tzinfo=timezone.utc)
                    
                    if isinstance(current_start, datetime) and current_start.tzinfo is None:
                        current_start = current_start.replace(tzinfo=timezone.utc)

                else:
                    # No invoices exist; start from the date the user joined
                    date_joined = UsersDbCore.get_date_joined(user_id)
                    if not date_joined:
                        logger.error(
                            "Could not retrieve date of joining for user %s. Skipping.",
                            user_id
                        )
                        continue  # Skip if date_joined is unavailable

                    # Convert date_joined to datetime at midnight UTC if it's a date object
                    if isinstance(date_joined, date) and not isinstance(date_joined, datetime):
                        date_joined = datetime.combine(date_joined, time.min, tzinfo=timezone.utc)

                    # Normalize to first day of joining month at midnight UTC
                    current_start = date_joined.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

                # Adjust current_start if it's after the last day of the previous month
                if current_start > last_day_of_previous_month:
                    logger.info(
                        "User %s has no new periods to invoice up to %s.",
                        user_id,
                        last_day_of_previous_month.strftime('%Y-%m-%d')
                    )
                    continue  # No new periods to invoice

                # Generate invoices up to the last day of the previous month
                while current_start <= last_day_of_previous_month:
                    # Calculate the last day of the current month
                    last_day = calendar.monthrange(current_start.year, current_start.month)[1]
                    current_end = current_start.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)

                    # Adjust if current_end exceeds the last day to invoice
                    if current_end > last_day_of_previous_month:
                        current_end = last_day_of_previous_month

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
                        # Get token usage per model per day for the user in the billing period
                        tokens_per_model_per_day = UsersDbCore.get_user_token_usage_per_model_per_day(
                            user_id, current_start, current_end
                        )

                        if not tokens_per_model_per_day:
                            logger.info(
                                "User %s has no token usage for %s to %s. Skipping invoice.",
                                user_id,
                                current_start.strftime('%Y-%m-%d'),
                                current_end.strftime('%Y-%m-%d')
                            )
                        else:
                            total_amount_cents = 0
                            usage_summary = {}  # key: (model, rate), value: total_tokens
                            for usage in tokens_per_model_per_day:
                                usage_date = usage['usage_date']
                                if isinstance(usage_date, date) and not isinstance(usage_date, datetime):
                                    usage_date = datetime.combine(usage_date, time.min, tzinfo=timezone.utc)
                                model = usage['model']
                                tokens = usage['total_tokens']
                                rate = BillingDbCore.get_price_per_token(
                                    model_name=model,
                                    effective_date=usage_date
                                )
                                if rate is None:
                                    logger.error(
                                        "Missing pricing information for model %s used by user %s on %s. Skipping this usage.",
                                        model,
                                        user_id,
                                        usage_date.strftime('%Y-%m-%d')
                                    )
                                    continue  # Skip this usage if rate is missing

                                key = (model, rate)
                                if key in usage_summary:
                                    usage_summary[key] += tokens
                                else:
                                    usage_summary[key] = tokens

                                amount_cents = int(Decimal(tokens) * Decimal(rate) * 100)
                                total_amount_cents += amount_cents

                            if total_amount_cents <= 0:
                                logger.info(
                                    "User %s has no billable token usage for %s to %s. Skipping invoice.",
                                    user_id,
                                    current_start.strftime('%Y-%m-%d'),
                                    current_end.strftime('%Y-%m-%d')
                                )
                            else:
                                description_lines = []
                                for (model, rate), tokens in usage_summary.items():
                                    description_lines.append(
                                        f"{tokens} tokens of {model} at ${Decimal(rate):.6f} per token"
                                    )
                                description = "Monthly token usage for {}: {}".format(
                                    current_start.strftime('%B %Y'),
                                    "; ".join(description_lines)
                                )

                                # Store the invoice in the database
                                invoice = BillingDbCore.create_invoice(
                                    user_id, total_amount_cents, description, current_start.date(), current_end.date()
                                )
                                if invoice:
                                    logger.info(
                                        "Stored invoice %s for user %s: $%.2f",
                                        invoice['invoice_id'],
                                        user_id,
                                        invoice['amount'] / 100  # Convert cents to dollars
                                    )

                # Update the last_invoice_run_at timestamp after processing all invoices for the user
                current_timestamp = datetime.now(timezone.utc)  # Use timezone-aware datetime
                BillingDbCore.update_last_invoice_run(user_id, current_timestamp)

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
