# enhancifai_backend/billing/monthly_billing.py

import os
from datetime import datetime, timedelta
from enhancifai_backend.database.access import read_db, write_db
from enhancifai_backend.database.handlers.users import UsersDbCore
from enhancifai_backend.database.handlers.stripe import StripeDbCore
from enhancifai_backend.database.handlers.utils import schemafy

# Define pricing per token (example: $0.0001 per token)
PRICE_PER_TOKEN = 0.0001  # $0.0001 per token

def calculate_amount(tokens_used):
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
    """
    # Determine the start and end of the previous month
    today = datetime.today()
    first_day_of_current_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_day_of_previous_month = first_day_of_current_month - timedelta(seconds=1)
    first_day_of_previous_month = last_day_of_previous_month.replace(day=1)

    # Fetch all users
    sql = schemafy("SELECT user_id FROM enhancifai.users;")
    users = read_db.do('select', sql=sql)

    for user in users:
        user_id = user['user_id']
        try:
            # Get total tokens used by the user in the previous month
            tokens_used = UsersDbCore.get_user_token_usage(user_id)

            if tokens_used <= 0:
                print(f"User {user_id} has no token usage for the month. Skipping invoice.")
                continue  # Skip users with no token usage

            # Calculate the amount due in cents
            amount = calculate_amount(tokens_used)
            description = f"Monthly token usage: {tokens_used} tokens for {first_day_of_previous_month.strftime('%B %Y')}"

            # Create and send the invoice
            invoice = StripeDbCore.create_invoice(user_id, amount, description)
            print(f"Created invoice {invoice['id']} for user {user_id}: ${amount / 100:.2f}")

        except Exception as e:
            # Log the error and continue with other users
            print(f"Failed to create invoice for user {user_id}: {str(e)}")

if __name__ == "__main__":
    generate_monthly_invoices()
