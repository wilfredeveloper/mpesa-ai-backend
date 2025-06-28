#!/usr/bin/env python3
"""
Unified Webhook Server for M-Pesa and Twilio WhatsApp
This server handles both M-Pesa callbacks and Twilio WhatsApp webhooks
"""

from flask import Flask, request, jsonify
import json
import datetime
import os
import requests
from pathlib import Path

# Import the callback manager
try:
    from app.mpesa_agent.callback_manager import callback_manager
    CALLBACK_MANAGER_AVAILABLE = True
except ImportError:
    print("⚠️  Callback manager not available - running in basic mode")
    CALLBACK_MANAGER_AVAILABLE = False

# Import the agent for processing WhatsApp messages
try:
    from app.mpesa_agent.agent import root_agent
    AGENT_AVAILABLE = True
except ImportError:
    print("⚠️  Agent not available - WhatsApp messages will be logged only")
    AGENT_AVAILABLE = False

app = Flask(__name__)

# Create logs directory if it doesn't exist
logs_dir = Path("logs")
logs_dir.mkdir(exist_ok=True)

def log_callback(data, callback_type="unknown"):
    """Log callback data to file"""
    timestamp = datetime.datetime.now().isoformat()
    log_entry = {
        "timestamp": timestamp,
        "type": callback_type,
        "data": data
    }

    # Log to file
    if callback_type.startswith("WHATSAPP"):
        log_file = logs_dir / f"whatsapp_messages_{datetime.date.today()}.json"
    else:
        log_file = logs_dir / f"mpesa_callbacks_{datetime.date.today()}.json"

    with open(log_file, "a") as f:
        f.write(json.dumps(log_entry) + "\n")

    # Also print to console
    print(f"\n{'='*50}")
    print(f"Webhook Received: {callback_type}")
    print(f"Time: {timestamp}")
    print(f"Data: {json.dumps(data, indent=2)}")
    print(f"{'='*50}\n")

def call_ai_agent(user_id, message, profile_name=None, phone_number=None):
    """Call the AI agent API with user context and message"""
    try:
        # AI Agent API configuration
        AGENT_API_URL = os.getenv('AGENT_API_URL', 'http://localhost:8000')

        # Create session ID based on user
        session_id = f"whatsapp_{user_id}"

        print(f"🤖 Calling AI Agent API for user {user_id}")

        # Step 1: Create or get session with user profile
        session_data = {
            "app_name": "mpesa_agent",
            "user_id": user_id,
            "session_id": session_id,
            "state": {
                "user_profile": {
                    "name": profile_name,
                    "phone": phone_number,
                    "whatsapp_id": user_id,
                    "platform": "whatsapp"
                },
                "conversation_context": {
                    "channel": "whatsapp",
                    "last_message_time": datetime.datetime.now().isoformat()
                }
            }
        }

        # Try to create session (will fail if exists, which is fine)
        try:
            session_response = requests.post(
                f"{AGENT_API_URL}/sessions",
                json=session_data,
                timeout=5
            )
            if session_response.status_code == 200:
                print(f"✅ Created new session for {profile_name}")
            else:
                print(f"📝 Session exists or creation failed: {session_response.status_code}")
        except Exception as e:
            print(f"📝 Session creation skipped: {e}")

        # Step 2: Send message to agent
        agent_request = {
            "app_name": "mpesa_agent",
            "user_id": user_id,
            "session_id": session_id,
            "message": message
        }

        print(f"📤 Sending message to agent: {message}")

        agent_response = requests.post(
            f"{AGENT_API_URL}/run",
            json=agent_request,
            timeout=80
        )

        if agent_response.status_code == 200:
            response_data = agent_response.json()

            # Extract the agent's text response from events
            agent_text = extract_agent_response(response_data.get('events', []))

            if agent_text:
                return agent_text
            else:
                print("⚠️  No agent text found in response")
                return None
        else:
            print(f"❌ Agent API error: {agent_response.status_code} - {agent_response.text}")
            return None

    except Exception as e:
        print(f"❌ Error calling AI agent: {e}")
        return None

def extract_agent_response(events):
    """Extract the agent's text response from API events"""
    try:
        agent_texts = []

        for event in events:
            # Look for agent responses
            if event.get('author') == 'mpesa_payment_agent' and event.get('content'):
                content = event['content']
                if isinstance(content, dict) and content.get('parts'):
                    for part in content['parts']:
                        if isinstance(part, dict) and part.get('text'):
                            agent_texts.append(part['text'])
                        elif isinstance(part, str):
                            agent_texts.append(part)

        if agent_texts:
            return '\n'.join(agent_texts).strip()

        return None

    except Exception as e:
        print(f"❌ Error extracting agent response: {e}")
        return None

def handle_payment_request(message, sender_phone, profile_name):
    """Handle payment requests like 'Send 1000 to 0714025354' by initiating STK to sender"""
    try:
        import re

        # Pattern to match payment requests: "send/pay [amount] to [number]"
        payment_patterns = [
            r'(?:send|pay|transfer)\s+(\d+)\s+(?:to|for)\s+(\d+)',  # "send 1000 to 0714025354"
            r'(?:send|pay|transfer)\s+(\d+)',  # "send 1000" (simplified)
            r'(\d+)\s+(?:to|for)\s+(\d+)',  # "1000 to 0714025354" (no verb)
        ]

        message_lower = message.lower().strip()
        amount = None
        recipient_number = None

        # Try to match payment patterns
        for pattern in payment_patterns:
            match = re.search(pattern, message_lower)
            if match:
                amount = int(match.group(1))
                if len(match.groups()) > 1:
                    recipient_number = match.group(2)
                break

        # If no payment pattern found, return None
        if not amount:
            return None

        print(f"💰 Payment request detected: {amount} KSh from {profile_name} ({sender_phone})")

        # Import M-Pesa tools
        try:
            from app.mpesa_agent.mpesa_tools import initiate_stk_push
        except ImportError as e:
            print(f"❌ Could not import M-Pesa tools: {e}")
            return f"❌ Hi {profile_name}! M-Pesa integration is not available right now. Please try again later."

        # Clean sender phone number (remove whatsapp: prefix, ensure proper format)
        clean_sender_phone = sender_phone.replace('whatsapp:', '').replace('+', '')

        # For now, we initiate STK push to the sender (not peer-to-peer)
        greeting = f"Hi {profile_name}! " if profile_name else "Hello! "

        if recipient_number:
            # User specified a recipient, but we'll charge the sender instead
            response_msg = (
                f"{greeting}I'll initiate a payment of {amount} KSh from your number.\n\n"
                f"📱 You'll receive an STK push prompt on {sender_phone}\n"
                f"💡 Note: Direct transfers aren't supported yet, so the payment will be from your account.\n\n"
                f"Processing payment..."
            )
        else:
            # Simple payment request
            response_msg = (
                f"{greeting}I'll initiate a payment of {amount} KSh from your number.\n\n"
                f"📱 You'll receive an STK push prompt on {sender_phone}\n\n"
                f"Processing payment..."
            )

        # Initiate STK push to sender
        try:
            stk_result = initiate_stk_push(
                phone_number=clean_sender_phone,
                amount=amount,
                account_reference="WhatsApp Payment",
                transaction_desc=f"Payment via WhatsApp - {amount} KSh"
            )

            if stk_result.get('status') == 'success':
                checkout_request_id = stk_result.get('checkout_request_id')
                success_msg = (
                    f"✅ {greeting}Payment request sent successfully!\n\n"
                    f"💰 Amount: {amount} KSh\n"
                    f"📱 Check your phone for M-Pesa prompt\n"
                    f"🔢 Reference: {checkout_request_id[:8]}...\n\n"
                    f"Complete the payment on your phone to proceed."
                )
                return success_msg
            else:
                error_msg = stk_result.get('error_message', 'Unknown error')
                failure_msg = (
                    f"❌ {greeting}Payment initiation failed.\n\n"
                    f"💰 Amount: {amount} KSh\n"
                    f"📝 Error: {error_msg}\n\n"
                    f"Please try again or check your phone number."
                )
                return failure_msg

        except Exception as e:
            print(f"❌ STK push error: {e}")
            error_msg = (
                f"❌ {greeting}Sorry, there was an error processing your payment.\n\n"
                f"💰 Amount: {amount} KSh\n"
                f"📝 Error: {str(e)}\n\n"
                f"Please try again later."
            )
            return error_msg

    except Exception as e:
        print(f"❌ Error handling payment request: {e}")
        return None

def process_whatsapp_message(message_data):
    """Process incoming WhatsApp message with the AI agent via API"""
    try:
        # Extract message details with personalization
        from_number = message_data.get('From', '').replace('whatsapp:', '')
        message_body = message_data.get('Body', '').strip()
        message_sid = message_data.get('MessageSid', '')
        profile_name = message_data.get('ProfileName', '')  # Get user's WhatsApp name
        wa_id = message_data.get('WaId', '')

        print(f"📱 Processing WhatsApp message from {profile_name} ({from_number}): {message_body}")

        if not message_body:
            greeting = f"Hi {profile_name}! " if profile_name else "Hello! "
            return f"👋 {greeting}I'm your M-Pesa assistant. Send me a message like 'send 500 to 0712345678' to make payments!"

        # Check if this is a payment request first
        payment_result = handle_payment_request(message_body, from_number, profile_name)
        if payment_result:
            print(f"💰 Payment request processed: {payment_result}")
            return payment_result

        # Try to integrate with AI agent API for other requests
        try:
            agent_response = call_ai_agent(
                user_id=wa_id or from_number,  # Use WhatsApp ID or phone as user ID
                message=message_body,
                profile_name=profile_name,
                phone_number=from_number
            )

            if agent_response:
                print(f"🤖 AI Agent response: {agent_response}")
                return agent_response
            else:
                print("⚠️  AI Agent returned empty response, using fallback")

        except Exception as e:
            print(f"⚠️  AI Agent API error: {e}")
            print("   Falling back to simple responses...")

        # Fallback to simple responses if AI agent fails
        greeting = f"Hi {profile_name}! " if profile_name else "Hello! "
        message_lower = message_body.lower()

        if any(word in message_lower for word in ['send', 'pay', 'transfer', 'mpesa']):
            response_text = (
                f"💰 {greeting}I can help you with M-Pesa payments!\n\n"
                f"To make a payment, use this format:\n"
                f"'Send [amount]' or 'Send [amount] to [number]'\n\n"
                f"Examples:\n"
                f"• 'Send 500' - Pay 500 KSh from your number\n"
                f"• 'Send 1000 to 0712345678' - Pay 1000 KSh\n\n"
                f"💡 You'll receive an STK push on your phone\n"
                f"Your message: '{message_body}'"
            )
        elif any(word in message_lower for word in ['balance', 'check']):
            response_text = f"💳 {greeting}I can help you check your M-Pesa balance! This feature will be available soon."
        elif any(word in message_lower for word in ['help', 'hi', 'hello', 'start']):
            response_text = (
                f"👋 {greeting}I'm your M-Pesa assistant.\n\n"
                f"I can help you:\n"
                f"💰 Make M-Pesa payments from your number\n"
                f"💳 Check payment status\n"
                f"📊 View transaction history\n\n"
                f"Payment examples:\n"
                f"• 'Send 500' - Pay 500 KSh\n"
                f"• 'Send 1000 to 0712345678' - Pay 1000 KSh\n"
                f"• 'Pay 200' - Pay 200 KSh\n\n"
                f"You'll get an STK push on your phone! 📱"
            )
        else:
            response_text = (
                f"🤖 {greeting}I received: '{message_body}'\n\n"
                f"I'm your M-Pesa assistant! I can help with:\n"
                f"• Sending money\n"
                f"• Checking balances\n"
                f"• Payment status\n\n"
                f"Try: 'Send 500 to 0712345678' or 'Help'"
            )

        print(f"🤖 Fallback response: {response_text}")
        return response_text

    except Exception as e:
        print(f"❌ Error processing WhatsApp message: {e}")
        return "❌ Sorry, I encountered an error processing your message. Please try again."

def send_whatsapp_reply(to_number, message, reply_from=None):
    """Send a reply via Twilio WhatsApp API using Twilio client (like unified_server.py)"""
    try:
        account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        auth_token = os.getenv('TWILIO_AUTH_TOKEN')

        # Use the number that received the message, or fall back to env variable
        if reply_from:
            from_number = reply_from
            print(f"📞 Using receiving number as sender: {from_number}")
        else:
            from_number = os.getenv('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886')
            print(f"📞 Using configured number: {from_number}")

        if not account_sid or not auth_token:
            print("⚠️  Twilio credentials not configured - response logged only")
            print(f"📝 Would send to {to_number}: {message}")
            return False

        # Import Twilio client (like unified_server.py)
        try:
            from twilio.rest import Client
            twilio_client = Client(account_sid, auth_token)
        except ImportError:
            print("❌ Twilio library not installed. Install with: pip install twilio")
            return False
        except Exception as e:
            print(f"❌ Failed to initialize Twilio client: {e}")
            return False

        # Clean the to_number (remove whatsapp: prefix if present)
        clean_to_number = to_number.replace('whatsapp:', '')
        if not clean_to_number.startswith('+'):
            clean_to_number = '+' + clean_to_number

        print(f"🔄 Attempting to send WhatsApp reply...")
        print(f"   From: {from_number}")
        print(f"   To: whatsapp:{clean_to_number}")
        print(f"   Message: {message[:50]}...")

        # Use Twilio client (like unified_server.py)
        message_obj = twilio_client.messages.create(
            body=message,
            from_=from_number,
            to=f'whatsapp:{clean_to_number}'
        )

        print(f"✅ WhatsApp reply sent successfully: {message_obj.sid}")
        return True

    except Exception as e:
        print(f"❌ Error sending WhatsApp reply: {e}")
        print(f"   💡 Tip: Reply from same number that received the message")
        print(f"   💡 Received on: {reply_from if reply_from else 'unknown'}")
        print(f"   💡 Trying to send from: {from_number}")
        return False

@app.route('/')
def home():
    """Home page"""
    return """
    <h1>Unified Webhook Server</h1>
    <p>This server handles both M-Pesa callbacks and Twilio WhatsApp webhooks!</p>

    <h3>📱 M-Pesa Integration</h3>
    <p><strong>Callback URL:</strong> <code>{}/mpesa/callback</code></p>
    <p><strong>Status:</strong> ✅ Active</p>

    <h3>💬 WhatsApp Integration</h3>
    <p><strong>Webhook URL:</strong> <code>{}/whatsapp/webhook</code></p>
    <p><strong>Status:</strong> ✅ Active</p>

    <hr>
    <h3>Recent Logs:</h3>
    <p>Check the <code>logs/</code> directory for detailed logs.</p>
    """.format(request.host_url.rstrip('/'), request.host_url.rstrip('/'))

@app.route('/mpesa/callback', methods=['POST'])
def mpesa_callback():
    """Handle M-Pesa STK Push callbacks with real-time agent integration"""
    try:
        # Get the JSON data from M-Pesa
        callback_data = request.get_json()

        if not callback_data:
            return jsonify({"ResultCode": 1, "ResultDesc": "No data received"}), 400

        # Log the callback
        log_callback(callback_data, "STK_PUSH_CALLBACK")

        # Extract key information
        body = callback_data.get('Body', {})
        stk_callback = body.get('stkCallback', {})

        result_code = stk_callback.get('ResultCode')
        result_desc = stk_callback.get('ResultDesc')
        merchant_request_id = stk_callback.get('MerchantRequestID')
        checkout_request_id = stk_callback.get('CheckoutRequestID')

        print(f"Payment Result: {result_desc} (Code: {result_code})")
        print(f"Merchant Request ID: {merchant_request_id}")
        print(f"Checkout Request ID: {checkout_request_id}")

        # If payment was successful, extract more details
        if result_code == 0:
            callback_metadata = stk_callback.get('CallbackMetadata', {})
            items = callback_metadata.get('Item', [])

            payment_details = {}
            for item in items:
                name = item.get('Name')
                value = item.get('Value')
                payment_details[name] = value

            print(f"Payment Details: {payment_details}")

        # 🚀 NEW: Process callback through callback manager for real-time agent integration
        if CALLBACK_MANAGER_AVAILABLE:
            try:
                manager_result = callback_manager.process_callback(callback_data)
                print(f"📡 Callback Manager Result: {manager_result}")

                # Add manager result to log
                log_callback({
                    "callback_data": callback_data,
                    "manager_result": manager_result
                }, "AGENT_INTEGRATION")

            except Exception as e:
                print(f"⚠️  Error in callback manager: {e}")
                log_callback({"error": str(e), "callback_data": callback_data}, "MANAGER_ERROR")

        # Respond to M-Pesa (important!)
        return jsonify({
            "ResultCode": 0,
            "ResultDesc": "Callback received successfully"
        })

    except Exception as e:
        print(f"Error processing callback: {e}")
        log_callback({"error": str(e), "raw_data": request.get_data(as_text=True)}, "ERROR")

        return jsonify({
            "ResultCode": 1,
            "ResultDesc": f"Error processing callback: {str(e)}"
        }), 500

@app.route('/mpesa/timeout', methods=['POST'])
def mpesa_timeout():
    """Handle M-Pesa timeout callbacks"""
    try:
        timeout_data = request.get_json()
        log_callback(timeout_data, "TIMEOUT")
        
        return jsonify({
            "ResultCode": 0,
            "ResultDesc": "Timeout received successfully"
        })
        
    except Exception as e:
        print(f"Error processing timeout: {e}")
        return jsonify({
            "ResultCode": 1,
            "ResultDesc": f"Error processing timeout: {str(e)}"
        }), 500

# ============================================================================
# WHATSAPP WEBHOOK ENDPOINTS
# ============================================================================

@app.route('/whatsapp/webhook', methods=['GET', 'POST'])
def whatsapp_webhook():
    """Handle Twilio WhatsApp webhooks"""

    if request.method == 'GET':
        # Webhook verification (if needed)
        return "WhatsApp webhook endpoint is active!", 200

    try:
        # Get the form data from Twilio
        webhook_data = request.form.to_dict()

        if not webhook_data:
            return "No data received", 400

        # Log the incoming webhook
        log_callback(webhook_data, "WHATSAPP_INCOMING")

        # Check if this is an incoming message
        if webhook_data.get('Body'):
            # Process the message with the agent
            agent_response = process_whatsapp_message(webhook_data)

            # Send reply back to user using the correct numbers
            from_number = webhook_data.get('From', '').replace('whatsapp:', '')
            to_number = webhook_data.get('To', '')  # This is the number that received the message

            if from_number and to_number:
                send_whatsapp_reply(from_number, agent_response, reply_from=to_number)

            # Log the response
            log_callback({
                "from_number": from_number,
                "to_number": to_number,
                "agent_response": agent_response
            }, "WHATSAPP_RESPONSE")

        # Respond to Twilio
        return "OK", 200

    except Exception as e:
        print(f"Error processing WhatsApp webhook: {e}")
        log_callback({"error": str(e), "raw_data": request.form.to_dict()}, "WHATSAPP_ERROR")
        return f"Error: {str(e)}", 500

@app.route('/whatsapp/status', methods=['POST'])
def whatsapp_status():
    """Handle Twilio WhatsApp status updates"""
    try:
        status_data = request.form.to_dict()
        log_callback(status_data, "WHATSAPP_STATUS")

        return "OK", 200

    except Exception as e:
        print(f"Error processing WhatsApp status: {e}")
        return f"Error: {str(e)}", 500

@app.route('/whatsapp/test', methods=['GET', 'POST'])
def whatsapp_test():
    """Test endpoint for WhatsApp integration"""
    if request.method == 'GET':
        return """
        <h2>WhatsApp Test Endpoint</h2>
        <p>Send a POST request with form data to test message processing:</p>
        <form method="POST">
            <label>From (phone number):</label><br>
            <input type="text" name="From" value="whatsapp:+254712345678" style="width: 300px;"><br><br>

            <label>Body (message):</label><br>
            <textarea name="Body" style="width: 300px; height: 100px;">Hello, I want to send 500 to 0712345678</textarea><br><br>

            <label>MessageSid:</label><br>
            <input type="text" name="MessageSid" value="test-message-123" style="width: 300px;"><br><br>

            <input type="submit" value="Test Message Processing">
        </form>
        """

    try:
        # Process as if it's a real webhook
        test_data = request.form.to_dict()
        log_callback(test_data, "WHATSAPP_TEST")

        # Process the message
        response = process_whatsapp_message(test_data)

        return f"""
        <h2>Test Result</h2>
        <h3>Input:</h3>
        <pre>{json.dumps(test_data, indent=2)}</pre>
        <h3>Agent Response:</h3>
        <pre>{response}</pre>
        <p><a href="/whatsapp/test">Test Again</a></p>
        """

    except Exception as e:
        return f"<h2>Test Error</h2><p>{str(e)}</p>", 500

@app.route('/payment/status/<checkout_request_id>')
def get_payment_status(checkout_request_id):
    """Get real-time payment status for agent integration"""
    if not CALLBACK_MANAGER_AVAILABLE:
        return jsonify({
            "status": "error",
            "message": "Callback manager not available"
        }), 503

    try:
        result = callback_manager.get_payment_status(checkout_request_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Error getting payment status: {str(e)}"
        }), 500

@app.route('/payment/register', methods=['POST'])
def register_payment():
    """Register a payment for tracking"""
    if not CALLBACK_MANAGER_AVAILABLE:
        return jsonify({
            "status": "error",
            "message": "Callback manager not available"
        }), 503

    try:
        data = request.get_json()
        required_fields = ['checkout_request_id', 'phone_number', 'amount', 'description']

        if not all(field in data for field in required_fields):
            return jsonify({
                "status": "error",
                "message": f"Missing required fields: {required_fields}"
            }), 400

        result = callback_manager.register_payment(
            data['checkout_request_id'],
            data['phone_number'],
            data['amount'],
            data['description']
        )

        return jsonify(result)
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Error registering payment: {str(e)}"
        }), 500

@app.route('/payment/wait/<checkout_request_id>')
def wait_for_payment(checkout_request_id):
    """Wait for payment completion with timeout"""
    if not CALLBACK_MANAGER_AVAILABLE:
        return jsonify({
            "status": "error",
            "message": "Callback manager not available"
        }), 503

    try:
        timeout = request.args.get('timeout', 300, type=int)  # Default 5 minutes
        result = callback_manager.wait_for_payment_completion(checkout_request_id, timeout)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Error waiting for payment: {str(e)}"
        }), 500

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.datetime.now().isoformat(),
        "service": "M-Pesa Callback Server",
        "callback_manager": "available" if CALLBACK_MANAGER_AVAILABLE else "unavailable"
    })

@app.route('/logs')
def view_logs():
    """View recent logs"""
    try:
        log_file = logs_dir / f"mpesa_callbacks_{datetime.date.today()}.json"
        
        if not log_file.exists():
            return "<h1>No logs for today</h1><p>No M-Pesa callbacks received yet today.</p>"
        
        logs = []
        with open(log_file, "r") as f:
            for line in f:
                try:
                    logs.append(json.loads(line.strip()))
                except:
                    continue
        
        # Show last 10 logs
        recent_logs = logs[-10:]
        
        html = "<h1>Recent M-Pesa Callbacks</h1>"
        for log in reversed(recent_logs):
            html += f"""
            <div style="border: 1px solid #ccc; margin: 10px; padding: 10px;">
                <h3>{log['type']} - {log['timestamp']}</h3>
                <pre>{json.dumps(log['data'], indent=2)}</pre>
            </div>
            """
        
        return html
        
    except Exception as e:
        return f"<h1>Error loading logs</h1><p>{str(e)}</p>"

def check_twilio_config():
    """Check Twilio configuration and provide helpful tips"""
    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    auth_token = os.getenv('TWILIO_AUTH_TOKEN')
    from_number = os.getenv('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886')

    print(f"\n🔧 Twilio Configuration:")
    print(f"   Account SID: {'✅ Set' if account_sid else '❌ Missing'}")
    print(f"   Auth Token: {'✅ Set' if auth_token else '❌ Missing'}")
    print(f"   WhatsApp Number: {from_number}")

    if not account_sid or not auth_token:
        print(f"\n💡 To enable WhatsApp replies:")
        print(f"   1. Add TWILIO_ACCOUNT_SID to .env")
        print(f"   2. Add TWILIO_AUTH_TOKEN to .env")
        print(f"   3. Set TWILIO_WHATSAPP_NUMBER to your actual number")
        print(f"   4. Restart the server")
        print(f"   📖 See docs/WHATSAPP_SETUP.md for details")
    else:
        print(f"   ✅ Twilio configured - replies will be sent")
        if from_number == 'whatsapp:+14155238886':
            print(f"   💡 Using sandbox number - make sure users joined with correct code")
        else:
            print(f"   💡 Using custom WhatsApp Business number")

def check_agent_api():
    """Check AI Agent API connectivity"""
    agent_api_url = os.getenv('AGENT_API_URL', 'http://localhost:8000')

    print(f"\n🤖 AI Agent API Configuration:")
    print(f"   API URL: {agent_api_url}")

    try:
        # Test connectivity to the agent API
        response = requests.get(f"{agent_api_url}/docs", timeout=3)
        if response.status_code == 200:
            print(f"   ✅ Agent API is running and accessible")
        else:
            print(f"   ⚠️  Agent API responded with status: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print(f"   ❌ Agent API not accessible - make sure main.py is running")
        print(f"   💡 Start with: python app/main.py")
    except Exception as e:
        print(f"   ⚠️  Agent API check failed: {e}")

    print(f"   💡 Agent API provides intelligent M-Pesa responses")

if __name__ == '__main__':
    print("🚀 Starting Unified Webhook Server (M-Pesa + WhatsApp)...")
    print("📝 Logs will be saved to: logs/")
    print("🌐 Access the server at: http://localhost:5455")
    print("\n📱 M-Pesa Endpoints:")
    print("   📞 Callback URL: http://localhost:5455/mpesa/callback")
    print("   ⏰ Timeout URL: http://localhost:5455/mpesa/timeout")
    print("\n💬 WhatsApp Endpoints:")
    print("   📨 Webhook URL: http://localhost:5455/whatsapp/webhook")
    print("   � Status URL: http://localhost:5455/whatsapp/status")
    print(f"\n🤖 Agent Available: {'✅ Yes' if AGENT_AVAILABLE else '❌ No'}")
    print(f"📡 Callback Manager: {'✅ Yes' if CALLBACK_MANAGER_AVAILABLE else '❌ No'}")

    # Check Twilio configuration
    check_twilio_config()

    # Check AI Agent API
    check_agent_api()

    print("\n�💡 Don't forget to expose this with ngrok!")
    print("   Example: ngrok http 5455")

    app.run(host='0.0.0.0', port=5455, debug=True)
