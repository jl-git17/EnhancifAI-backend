import logging
from datetime import datetime, timedelta, date, time, timezone
from decimal import Decimal, ROUND_HALF_UP
import calendar
from enhancifai_backend.database.access import read_db
from enhancifai_backend.database.handlers.billing import BillingDbCore
from enhancifai_backend.database.handlers.users import UsersDbCore
from enhancifai_backend.database.handlers.utils import schemafy

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_one_month(dt):
    """
    Adds one month to the given datetime object.
    """
    year = dt.year + (dt.month // 12)
    month = dt.month % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)

def generate_monthly_invoices():
    """
    Generate monthly invoices for all users with detailed line items.
    """
    failed = False
    try:
        today = datetime.now(timezone.utc)
        first_day_of_current_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_day_of_previous_month = first_day_of_current_month - timedelta(seconds=1)
        first_day_of_previous_month = last_day_of_previous_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        logger.info(
            "Generating invoices up to the period: %s to %s",
            first_day_of_previous_month.strftime('%Y-%m-%d'),
            last_day_of_previous_month.strftime('%Y-%m-%d')
        )

        sql = schemafy("SELECT user_id FROM enhancifai.users;")
        users = read_db.do('select', sql=sql)
        logger.info("Fetched %s users from the database.", len(users))

        for user in users:
            user_id = user['user_id']
            skipThisUser = False
            try:
                last_invoice_end_date = BillingDbCore.get_last_invoice_end_date(user_id)

                if last_invoice_end_date:
                    current_start = last_invoice_end_date + timedelta(days=1)
                    if isinstance(current_start, date) and not isinstance(current_start, datetime):
                        current_start = datetime.combine(current_start, time.min, tzinfo=timezone.utc)
                    if current_start.tzinfo is None:
                        current_start = current_start.replace(tzinfo=timezone.utc)
                else:
                    date_joined = UsersDbCore.get_date_joined(user_id)
                    if not date_joined:
                        logger.error("Could not retrieve date of joining for user %s. Skipping.", user_id)
                        continue
                    if isinstance(date_joined, date) and not isinstance(date_joined, datetime):
                        date_joined = datetime.combine(date_joined, time.min, tzinfo=timezone.utc)
                    current_start = date_joined.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                    if current_start.tzinfo is None:
                        current_start = current_start.replace(tzinfo=timezone.utc)

                if current_start > last_day_of_previous_month:
                    logger.info("User %s has no new periods to invoice up to %s.", user_id, last_day_of_previous_month.strftime('%Y-%m-%d'))
                    continue

                while current_start <= last_day_of_previous_month:
                    last_day = calendar.monthrange(current_start.year, current_start.month)[1]
                    current_end = current_start.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)

                    if current_end > last_day_of_previous_month:
                        current_end = last_day_of_previous_month

                    logger.info("Generating invoice for user %s for period: %s to %s",
                                user_id, current_start.strftime('%Y-%m-%d'), current_end.strftime('%Y-%m-%d'))

                    invoice_exists = BillingDbCore.invoice_exists(user_id, current_start, current_end)
                    if invoice_exists:
                        logger.info("User %s already has an invoice for %s to %s. Skipping.",
                                    user_id, current_start.strftime('%Y-%m-%d'), current_end.strftime('%Y-%m-%d'))
                    else:
                        normal_tokens_per_model_per_day = UsersDbCore.get_user_normal_token_usage_per_model_per_day(user_id, current_start, current_end)
                        pi_tokens_per_model_per_day = UsersDbCore.get_user_pi_token_usage_per_model_per_day(user_id, current_start, current_end)

                        # Now process normal tokens and PI tokens separately
                        normal_line_items = []
                        pi_line_items = []
                        total_amount_cents = 0

                        for usage in normal_tokens_per_model_per_day:
                            usage_date = usage['usage_date']
                            model = usage['model']
                            tokens = usage['total_tokens']
                            rate = BillingDbCore.get_price_per_token(model_name=model, year=usage_date.year, month=usage_date.month)
                            if rate is None:
                                logger.error(
                                    "Missing pricing info for model %s on %s (user %s).",
                                    model, usage_date.strftime('%Y-%m-%d'), user_id
                                )
                                skipThisUser = True
                                break
                            amount_cents = (Decimal(tokens) * Decimal(rate) * 100).quantize(Decimal('1'))
                            total_amount_cents += int(amount_cents)
                            normal_line_items.append({
                                'date': usage_date.strftime('%Y-%m-%d'),
                                'model': model,
                                'tokens': tokens,
                                'rate': float(rate),
                                'amount': float(amount_cents) / 100.0
                            })

                        if skipThisUser:
                            break

                        for usage in pi_tokens_per_model_per_day:
                            usage_date = usage['usage_date']
                            model = usage['model']
                            tokens = usage['total_tokens']
                            rate = BillingDbCore.get_price_per_token(model_name=model, year=usage_date.year, month=usage_date.month)
                            if rate is None:
                                logger.error(
                                    "Missing pricing info for PI model %s on %s (user %s).",
                                    model, usage_date.strftime('%Y-%m-%d'), user_id
                                )
                                skipThisUser = True
                                break
                            amount_cents = (Decimal(tokens) * Decimal(rate) * 100).quantize(Decimal('1'))
                            total_amount_cents += int(amount_cents)
                            pi_line_items.append({
                                'date': usage_date.strftime('%Y-%m-%d'),
                                'model': model,
                                'tokens': tokens,
                                'rate': float(rate),
                                'amount': float(amount_cents) / 100.0
                            })

                        if skipThisUser:
                            break

                        if total_amount_cents > 0:
                            description = f"Monthly token usage for {current_start.strftime('%B %Y')}"
                            metadata_dict = {
                                'description': description,
                                'line_items': normal_line_items,
                                'pi_line_items': pi_line_items
                            }
                            invoice = BillingDbCore.create_invoice(
                                user_id, total_amount_cents, description, current_start.date(), current_end.date(), metadata=metadata_dict
                            )
                            if invoice:
                                logger.info("Stored invoice %s for user %s: $%.2f",
                                            invoice['invoice_id'], user_id, invoice['amount'] / 100)
                        else:
                            logger.info("No tokens used by user %s for period %s to %s.",
                                        user_id, current_start.strftime('%Y-%m-%d'), current_end.strftime('%Y-%m-%d'))
                            skipThisUser = True
                            break


                    current_start = add_one_month(current_start)

                if skipThisUser:
                    continue

                current_timestamp = datetime.now(timezone.utc)
                BillingDbCore.update_last_invoice_run(user_id, current_timestamp)

            except Exception as e:
                logger.error("Failed to create invoice for user %s: %s", user_id, str(e), exc_info=True)
    except Exception as e:
        logger.critical("Failed to generate monthly invoices: %s", str(e), exc_info=True)


if __name__ == "__main__":
    generate_monthly_invoices()
