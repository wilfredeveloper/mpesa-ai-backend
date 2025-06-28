import datetime
from zoneinfo import ZoneInfo
from google.adk.agents import Agent
from .mpesa_tools import validate_phone_number, initiate_stk_push, check_transaction_status

def get_weather(city: str) -> dict:
    """Retrieves the current weather report for a specified city.

    Args:
        city (str): The name of the city for which to retrieve the weather report.

    Returns:
        dict: status and result or error msg.
    """
    if city.lower() == "new york":
        return {
            "status": "success",
            "report": (
                "The weather in New York is sunny with a temperature of 25 degrees"
                " Celsius (77 degrees Fahrenheit)."
            ),
        }
    else:
        return {
            "status": "error",
            "error_message": f"Weather information for '{city}' is not available.",
        }


def get_current_time(city: str) -> dict:
    """Returns the current time in a specified city.

    Args:
        city (str): The name of the city for which to retrieve the current time.

    Returns:
        dict: status and result or error msg.
    """

    if city.lower() == "new york":
        tz_identifier = "America/New_York"
    else:
        return {
            "status": "error",
            "error_message": (
                f"Sorry, I don't have timezone information for {city}."
            ),
        }

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    report = (
        f'The current time in {city} is {now.strftime("%Y-%m-%d %H:%M:%S %Z%z")}'
    )
    return {"status": "success", "report": report}


def send_mpesa_payment(phone_number: str, amount: float, description: str = "Payment") -> dict:
    """
    Sends an M-Pesa payment request to a phone number.

    Args:
        phone_number (str): The recipient's phone number (Kenyan format)
        amount (float): Amount to send in KSh
        description (str): Description for the payment

    Returns:
        dict: Payment initiation result with status and details
    """
    return initiate_stk_push(
        phone_number=phone_number,
        amount=amount,
        account_reference="AI Agent Payment",
        transaction_desc=description
    )


def check_mpesa_payment_status(checkout_request_id: str) -> dict:
    """
    Checks the status of an M-Pesa payment transaction.

    Args:
        checkout_request_id (str): The checkout request ID from the payment initiation

    Returns:
        dict: Transaction status and details
    """
    return check_transaction_status(checkout_request_id)


def validate_kenyan_phone(phone_number: str) -> dict:
    """
    Validates and formats a Kenyan phone number for M-Pesa transactions.

    Args:
        phone_number (str): Phone number to validate

    Returns:
        dict: Validation result with formatted number
    """
    return validate_phone_number(phone_number)


def get_mpesa_balance() -> dict:
    """
    Gets the current M-Pesa business account balance.

    Returns:
        dict: Account balance information
    """
    return {
        "status": "info",
        "message": "Account balance feature not implemented yet. Use Safaricom portal to check balance."
    }


root_agent = Agent(
    name="mpesa_payment_agent",
    model="gemini-2.0-flash",
    description=(
        "AI agent that can process M-Pesa payments and handle payment-related queries. "
        "Can validate phone numbers, initiate payments, check transaction status, and get account balance."
    ),
    instruction=(
        "You are a helpful M-Pesa payment assistant. You can help users with:\n"
        "1. Sending M-Pesa payments to phone numbers\n"
        "2. Validating Kenyan phone numbers\n"
        "3. Checking payment transaction status\n"
        "4. Getting account balance information\n"
        "5. Answering questions about time and weather\n\n"
        "Always validate phone numbers before initiating payments. "
        "Be clear about payment amounts and ask for confirmation before processing. "
        "Provide helpful error messages if something goes wrong."
    ),
    tools=[
        send_mpesa_payment,
        check_mpesa_payment_status,
        validate_kenyan_phone,
        get_mpesa_balance
    ],
)