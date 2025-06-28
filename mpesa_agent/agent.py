import datetime
import requests
import time
import os
from zoneinfo import ZoneInfo
from google.adk.agents import Agent
from .mpesa_tools import validate_phone_number, initiate_stk_push, check_transaction_status
from dotenv import load_dotenv

# Load environment variables
import pathlib
root_dir = pathlib.Path(__file__).parent.parent
env_path = root_dir / '.env'
load_dotenv(env_path)

# Callback server configuration - read from environment
def get_callback_server_url():
    """Get callback server URL from environment or default"""
    # Try to extract from MPESA_CALLBACK_URL
    callback_url = os.getenv('MPESA_CALLBACK_URL', '')
    if callback_url:
        # Extract base URL from callback URL
        # e.g., https://abc123.ngrok.io/mpesa/callback -> https://abc123.ngrok.io
        if '/mpesa/callback' in callback_url:
            return callback_url.replace('/mpesa/callback', '')

    # Fallback to explicit callback server URL or localhost
    return os.getenv('CALLBACK_SERVER_URL', 'http://localhost:8001')

CALLBACK_SERVER_URL = get_callback_server_url()

def send_mpesa_payment(phone_number: str, amount: float, description: str = "AI Agent Payment") -> dict:
    """
    Sends an M-Pesa payment request to a phone number.
    Automatically validates the phone number and processes the payment immediately.

    Args:
        phone_number (str): The recipient's phone number (any format - will be auto-validated)
        amount (float): Amount to send in KSh
        description (str): Description for the payment (auto-inferred if not provided)

    Returns:
        dict: Payment initiation result with status and details
    """
    # The initiate_stk_push function already validates the phone number internally
    # So we can go straight to payment processing
    return initiate_stk_push(
        phone_number=phone_number,
        amount=amount,
        account_reference="AI Agent Payment",
        transaction_desc=description
    )


def check_payment_status_realtime(checkout_request_id: str) -> dict:
    """
    Checks the real-time status of an M-Pesa payment using callback integration.

    Args:
        checkout_request_id (str): The checkout request ID from the payment initiation

    Returns:
        dict: Real-time transaction status and details
    """
    try:
        # First try to get status from callback manager
        response = requests.get(f"{CALLBACK_SERVER_URL}/payment/status/{checkout_request_id}", timeout=10)

        if response.status_code == 200:
            result = response.json()

            if result.get('status') == 'found':
                payment_info = result.get('payment_info', {})
                payment_status = payment_info.get('status')

                if payment_status == 'success':
                    return {
                        "status": "success",
                        "message": "✅ Payment completed successfully",
                        "payment_status": "completed",
                        "payment_details": payment_info.get('payment_details', {}),
                        "completed_at": payment_info.get('completed_at'),
                        "real_time_data": True
                    }
                elif payment_status == 'failed':
                    return {
                        "status": "failed",
                        "message": f"❌ Payment failed: {payment_info.get('error_message', 'Unknown error')}",
                        "payment_status": "failed",
                        "error_message": payment_info.get('error_message'),
                        "real_time_data": True
                    }
                elif payment_status == 'pending':
                    return {
                        "status": "pending",
                        "message": "⏳ Payment is still pending - waiting for user to complete on phone",
                        "payment_status": "pending",
                        "initiated_at": payment_info.get('initiated_at'),
                        "real_time_data": True
                    }
                elif payment_status == 'timeout':
                    return {
                        "status": "timeout",
                        "message": "⏱️  Payment timed out - user may not have completed the transaction",
                        "payment_status": "timeout",
                        "real_time_data": True
                    }
            else:
                # Payment not found in callback manager, fall back to M-Pesa API
                return check_transaction_status(checkout_request_id)
        else:
            # Callback server not available, fall back to M-Pesa API
            return check_transaction_status(checkout_request_id)

    except Exception as e:
        print(f"⚠️  Error checking real-time status: {e}")
        # Fall back to M-Pesa API
        return check_transaction_status(checkout_request_id)

def check_mpesa_payment_status(checkout_request_id: str) -> dict:
    """
    Legacy function - now uses real-time checking by default
    """
    return check_payment_status_realtime(checkout_request_id)


def send_instant_payment_with_tracking(phone_number: str, amount: float, context: str = "", wait_for_completion: bool = True) -> dict:
    """
    Sends an instant M-Pesa payment with real-time tracking and automatic status updates.
    This is the main function for frictionless payments with callback integration.

    Args:
        phone_number (str): The recipient's phone number (any format)
        amount (float): Amount to send in KSh
        context (str): Conversation context to infer description from
        wait_for_completion (bool): Whether to wait for payment completion

    Returns:
        dict: Payment result with real-time status and details
    """
    # Smart description inference based on context
    description = "AI Agent Payment"  # Default

    if context:
        context_lower = context.lower()
        if any(word in context_lower for word in ["lunch", "food", "meal", "eat"]):
            description = "Lunch Payment"
        elif any(word in context_lower for word in ["transport", "fare", "bus", "matatu", "uber", "taxi"]):
            description = "Transport Payment"
        elif any(word in context_lower for word in ["rent", "house", "accommodation"]):
            description = "Rent Payment"
        elif any(word in context_lower for word in ["shopping", "groceries", "shop", "buy"]):
            description = "Shopping Payment"
        elif any(word in context_lower for word in ["bill", "electricity", "water", "utility"]):
            description = "Bill Payment"
        elif any(word in context_lower for word in ["loan", "debt", "borrow", "owe"]):
            description = "Loan Payment"
        elif any(word in context_lower for word in ["gift", "present", "birthday", "celebration"]):
            description = "Gift Payment"
        elif any(word in context_lower for word in ["emergency", "urgent", "help"]):
            description = "Emergency Payment"
        elif any(word in context_lower for word in ["business", "service", "work"]):
            description = "Business Payment"

    # Step 1: Initiate payment
    payment_result = initiate_stk_push(
        phone_number=phone_number,
        amount=amount,
        account_reference="AI Agent",
        transaction_desc=description
    )

    if payment_result.get('status') != 'success':
        return payment_result

    checkout_request_id = payment_result.get('checkout_request_id')
    if not checkout_request_id:
        return {
            "status": "error",
            "error_message": "No checkout request ID received from M-Pesa"
        }

    # Step 2: Register payment for tracking
    try:
        register_url = f"{CALLBACK_SERVER_URL}/payment/register"
        print(f"🔗 Registering payment at: {register_url}")

        register_response = requests.post(register_url,
            json={
                'checkout_request_id': checkout_request_id,
                'phone_number': phone_number,
                'amount': amount,
                'description': description
            },
            timeout=5
        )

        if register_response.status_code == 200:
            print(f"✅ Payment registered for tracking: {checkout_request_id}")
        else:
            print(f"⚠️  Failed to register payment for tracking: {register_response.status_code} - {register_response.text}")
    except Exception as e:
        print(f"⚠️  Could not register payment for tracking: {e}")
        print(f"   Callback server URL: {CALLBACK_SERVER_URL}")

    # Step 3: Wait for completion if requested
    if wait_for_completion:
        try:
            wait_url = f"{CALLBACK_SERVER_URL}/payment/wait/{checkout_request_id}?timeout=120"
            print(f"⏳ Waiting for payment completion at: {wait_url}")
            wait_response = requests.get(wait_url, timeout=125)

            if wait_response.status_code == 200:
                wait_result = wait_response.json()

                if wait_result.get('status') == 'completed':
                    payment_info = wait_result.get('payment_info', {})
                    payment_status = payment_info.get('status')

                    if payment_status == 'success':
                        return {
                            "status": "success",
                            "message": f"💰 Payment completed successfully! {amount} KSh sent to {phone_number}",
                            "checkout_request_id": checkout_request_id,
                            "payment_status": "completed",
                            "payment_details": payment_info.get('payment_details', {}),
                            "description": description,
                            "real_time_tracking": True
                        }
                    else:
                        return {
                            "status": "failed",
                            "message": f"❌ Payment failed: {payment_info.get('error_message', 'Unknown error')}",
                            "checkout_request_id": checkout_request_id,
                            "payment_status": "failed",
                            "description": description,
                            "real_time_tracking": True
                        }
                else:
                    return {
                        "status": "timeout",
                        "message": f"⏱️  Payment initiated but completion status unknown. Check manually with ID: {checkout_request_id}",
                        "checkout_request_id": checkout_request_id,
                        "payment_status": "pending",
                        "description": description,
                        "real_time_tracking": True
                    }
        except Exception as e:
            print(f"⚠️  Could not wait for payment completion: {e}")

    # Return immediate result if not waiting or if waiting failed
    return {
        "status": "initiated",
        "message": f"📱 Payment request sent to {phone_number} for {amount} KSh. User will receive STK push prompt.",
        "checkout_request_id": checkout_request_id,
        "payment_status": "pending",
        "description": description,
        "real_time_tracking": True,
        "note": "Payment completion will be tracked automatically"
    }

def send_instant_payment(phone_number: str, amount: float, context: str = "") -> dict:
    """
    Legacy function for backward compatibility - now uses tracking by default
    """
    return send_instant_payment_with_tracking(phone_number, amount, context, wait_for_completion=True)


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
        "Ultra-fast M-Pesa payment agent with REAL-TIME callback integration. "
        "Processes transactions instantly, tracks payment completion automatically, and provides immediate feedback on payment success/failure."
    ),
    instruction=(
        "You are a lightning-fast M-Pesa payment assistant with REAL-TIME payment tracking and ZERO friction.\n\n"

        "🚀 CORE BEHAVIOR WITH REAL-TIME TRACKING:\n"
        "- When a user mentions sending money, use send_instant_payment() IMMEDIATELY\n"
        "- The system now AUTOMATICALLY tracks payment completion via M-Pesa callbacks\n"
        "- You will get INSTANT feedback when payments succeed or fail\n"
        "- Provide immediate status updates to users without them asking\n"
        "- NO confirmations, NO separate validations, NO extra steps\n\n"

        "💡 SMART DESCRIPTION INFERENCE:\n"
        "- Analyze conversation context to determine payment purpose\n"
        "- Use contextual clues: 'lunch', 'transport', 'rent', 'shopping', 'emergency', etc.\n"
        "- Default to 'AI Agent Payment' if context is unclear\n"
        "- Pass full conversation context to send_instant_payment()\n\n"

        "⚡ INSTANT PROCESSING WITH REAL-TIME FEEDBACK:\n"
        "- User: 'Send 500 to 0712345678 for lunch' → IMMEDIATELY process\n"
        "- System: Sends STK push + tracks completion automatically\n"
        "- You: Provide real-time updates: 'Payment sent! ✅ Completed successfully!' or 'Payment failed ❌'\n"
        "- Users get immediate feedback without asking for status\n\n"

        "🔔 AUTOMATIC NOTIFICATIONS:\n"
        "- When payment completes successfully: '✅ Payment completed! 500 KSh sent successfully'\n"
        "- When payment fails: '❌ Payment failed: [reason]'\n"
        "- When payment times out: '⏱️ Payment pending - user may not have completed on phone'\n"
        "- Always include payment details and next steps\n\n"

        "🎯 TOOLS PRIORITY:\n"
        "1. send_instant_payment() - Primary tool with real-time tracking\n"
        "2. send_instant_payment_with_tracking() - Advanced tracking options\n"
        "3. check_payment_status_realtime() - Real-time status checks\n"
        "4. send_mpesa_payment() - Legacy backup\n"
        "5. get_mpesa_balance() - Balance inquiries\n\n"

        "🎯 EXAMPLES:\n"
        "User: 'Send 500 for lunch to 0712345678'\n"
        "You: [Immediately call send_instant_payment()]\n"
        "Result: '📱 Payment sent! Waiting for completion... ✅ Success! 500 KSh sent for lunch!'\n\n"

        "Remember: Your goal is INSTANT payments with REAL-TIME completion feedback!"
    ),
    tools=[
        send_instant_payment,
        send_instant_payment_with_tracking,
        check_payment_status_realtime,
        send_mpesa_payment,
        check_mpesa_payment_status,
        get_mpesa_balance
    ],
)