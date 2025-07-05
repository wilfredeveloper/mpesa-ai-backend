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
                "sender_phone_number": phone_number,  # State variable for agent prompt
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



def process_whatsapp_message(message_data):
    """Process incoming WhatsApp message directly with the AI agent - SIMPLIFIED"""
    try:
        # Extract message details
        from_number = message_data.get('From', '').replace('whatsapp:', '')
        message_body = message_data.get('Body', '').strip()
        profile_name = message_data.get('ProfileName', '')
        wa_id = message_data.get('WaId', '')

        print(f"📱 Processing WhatsApp message from {profile_name} ({from_number}): {message_body}")

        if not message_body:
            greeting = f"Hi {profile_name}! " if profile_name else "Hello! "
            return f"👋 {greeting}I'm your M-Pesa assistant. Send me a message like 'send 500 to 0712345678' to make payments!"

        # SIMPLIFIED: Always call AI agent directly - let it handle everything
        try:
            agent_response = call_ai_agent(
                user_id=wa_id or from_number,
                message=message_body,
                profile_name=profile_name,
                phone_number=from_number
            )

            if agent_response:
                print(f"🤖 AI Agent response: {agent_response}")
                return agent_response
            else:
                print("⚠️ AI Agent returned empty response")
                return f"❌ Sorry, I couldn't process your message. Please try again."

        except Exception as e:
            print(f"❌ AI Agent error: {e}")
            return f"❌ Sorry, I encountered an error. Please try again."

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



        # 🚀 Process callback through callback manager for real-time agent integration
        if CALLBACK_MANAGER_AVAILABLE:
            try:
                manager_result = callback_manager.process_callback(callback_data)
                print(f"📡 Callback Manager Result: {manager_result}")

                # SIMPLIFIED: If payment completed, notify user via AI agent
                if manager_result.get('status') == 'success' and manager_result.get('payment_info'):
                    payment_info = manager_result['payment_info']
                    phone_number = payment_info.get('phone_number')

                    if phone_number:
                        # Create a natural message about the payment completion
                        if payment_info.get('status') == 'success':
                            completion_message = f"Payment completed successfully! Transaction details: {payment_info.get('payment_details', {})}"
                        elif payment_info.get('status') == 'failed':
                            completion_message = f"Payment failed: {payment_info.get('error_message', 'Unknown error')}"
                        else:
                            completion_message = f"Payment status update: {payment_info.get('status')}"

                        # Send completion notification via AI agent
                        try:
                            agent_response = call_ai_agent(
                                user_id=phone_number,
                                message=completion_message,
                                profile_name=None,  # We don't have profile name from callback
                                phone_number=phone_number
                            )

                            if agent_response:
                                # Send the agent's response to WhatsApp
                                send_whatsapp_reply(phone_number, agent_response)
                                print(f"✅ Payment completion notification sent via AI agent")
                        except Exception as e:
                            print(f"⚠️ Error sending payment completion via AI agent: {e}")

                # Add manager result to log
                log_callback({
                    "callback_data": callback_data,
                    "manager_result": manager_result,
                    "callback_tracking": True
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
        timeout = request.args.get('timeout', 80, type=int)  # Default 80 seconds
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
