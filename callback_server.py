#!/usr/bin/env python3
"""
Simple Flask server to handle M-Pesa callbacks
This server receives and logs M-Pesa payment notifications
"""

from flask import Flask, request, jsonify
import json
import datetime
import os
from pathlib import Path

# Import the callback manager
try:
    from mpesa_agent.callback_manager import callback_manager
    CALLBACK_MANAGER_AVAILABLE = True
except ImportError:
    print("⚠️  Callback manager not available - running in basic mode")
    CALLBACK_MANAGER_AVAILABLE = False

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
    log_file = logs_dir / f"mpesa_callbacks_{datetime.date.today()}.json"
    with open(log_file, "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    
    # Also print to console
    print(f"\n{'='*50}")
    print(f"M-Pesa Callback Received: {callback_type}")
    print(f"Time: {timestamp}")
    print(f"Data: {json.dumps(data, indent=2)}")
    print(f"{'='*50}\n")

@app.route('/')
def home():
    """Home page"""
    return """
    <h1>M-Pesa Callback Server</h1>
    <p>This server is running and ready to receive M-Pesa callbacks!</p>
    <p><strong>Callback URL:</strong> <code>{}/mpesa/callback</code></p>
    <p><strong>Status:</strong> ✅ Active</p>
    <hr>
    <h3>Recent Logs:</h3>
    <p>Check the <code>logs/</code> directory for detailed callback logs.</p>
    """.format(request.host_url.rstrip('/'))

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

if __name__ == '__main__':
    print("🚀 Starting M-Pesa Callback Server...")
    print("📝 Logs will be saved to: logs/")
    print("🌐 Access the server at: http://localhost:8001")
    print("📞 Callback URL: http://localhost:8001/mpesa/callback")
    print("\n💡 Don't forget to expose this with ngrok!")
    
    app.run(host='0.0.0.0', port=8001, debug=True)
