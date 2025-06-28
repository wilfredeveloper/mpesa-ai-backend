#!/usr/bin/env python3
"""
🚀 Unified WhatsApp + M-Pesa Callback Server (FastAPI)
=====================================================
Single server handling:
- WhatsApp webhooks (Twilio)
- M-Pesa payment callbacks (Daraja API)
- Health checks and status endpoints
- Contact management

Run with: python3 unified_server.py
Expose with: ngrok http 5000
API Docs: http://localhost:5000/docs
"""

import os
import json
import re
import requests
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from dotenv import load_dotenv
from contact_manager import resolve_contact_name, list_all_contacts, search_contacts
import logging
import uvicorn

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Unified WhatsApp + M-Pesa Server",
    description="Single server handling WhatsApp webhooks, M-Pesa callbacks, and AI agent integration",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Pydantic models for request/response validation
class HealthResponse(BaseModel):
    service: str
    status: str
    twilio_configured: bool
    mpesa_configured: bool
    endpoints: Dict[str, str]

class ContactsResponse(BaseModel):
    contacts: Dict[str, str]

class PaymentStatusResponse(BaseModel):
    result_code: Optional[int] = None
    result_desc: Optional[str] = None
    timestamp: Optional[str] = None
    callback_data: Optional[Dict[str, Any]] = None

class MPesaCallbackResponse(BaseModel):
    ResultCode: int
    ResultDesc: str

# Twilio configuration
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_WHATSAPP_NUMBER = os.getenv('TWILIO_WHATSAPP_NUMBER')

# Initialize Twilio client
twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    try:
        twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        logger.info("✅ Twilio client initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Twilio client: {e}")
else:
    logger.warning("⚠️ Twilio credentials not found")

# M-Pesa configuration
MPESA_CONSUMER_KEY = os.getenv('MPESA_CONSUMER_KEY')
MPESA_CONSUMER_SECRET = os.getenv('MPESA_CONSUMER_SECRET')

# Payment tracking storage (in production, use a database)
payment_tracking = {}

def send_whatsapp_message(to_number, message):
    """Send WhatsApp message via Twilio"""
    if not twilio_client:
        logger.error("Twilio client not initialized")
        return False
    
    try:
        message = twilio_client.messages.create(
            body=message,
            from_=TWILIO_WHATSAPP_NUMBER,
            to=f'whatsapp:+{to_number}'
        )
        logger.info(f"WhatsApp message sent: {message.sid}")
        return True
    except Exception as e:
        logger.error(f"Failed to send WhatsApp message: {e}")
        return False

def create_or_get_session(app_name, user_id):
    """Create or get an existing session for the user"""
    try:
        # Try to create a new session
        session_response = requests.post(
            f"http://localhost:8000/apps/{app_name}/users/{user_id}/sessions",
            json={},
            timeout=10
        )
        
        if session_response.status_code == 200:
            session_data = session_response.json()
            session_id = session_data.get("id")
            logger.info(f"✅ Created new session: {session_id}")
            return session_id
        else:
            logger.error(f"Failed to create session: {session_response.status_code} - {session_response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error creating session: {e}")
        return None

def process_with_ai_agent(message, sender_phone):
    """Process message using the Google ADK API server"""
    try:
        logger.info(f"🤖 Processing with AI Agent via ADK API: {message}")
        
        # Clean phone number for user ID
        user_id = sender_phone.replace('+', '').replace(' ', '')
        app_name = "mpesa_agent"
        
        # Create or get session
        session_id = create_or_get_session(app_name, user_id)
        if not session_id:
            return "❌ Failed to create AI Agent session\n\n⚠️ Falling back to basic processing..."
        
        # Prepare the request for ADK API
        adk_request = {
            "appName": app_name,
            "userId": user_id,
            "sessionId": session_id,
            "newMessage": {
                "parts": [
                    {
                        "text": f"""USER REQUEST: "{message}"

SENDER: {sender_phone}

TASK: Process this request immediately. If it's a payment request, use your tools to:
1. Call resolve_contact_phone() if recipient is a name
2. Call send_instant_payment() with the details
3. Provide immediate feedback

DO NOT give generic responses. TAKE ACTION NOW."""
                    }
                ]
            },
            "streaming": False
        }
        
        logger.info(f"🔗 Calling ADK API with session: {session_id}")
        
        # Call the ADK API server
        adk_response = requests.post(
            "http://localhost:8000/run",
            json=adk_request,
            timeout=30
        )
        
        if adk_response.status_code == 200:
            events = adk_response.json()
            logger.info(f"📡 ADK API returned {len(events)} events")
            
            # Extract the agent's response from events
            agent_text = ""
            for i, event in enumerate(events):
                logger.info(f"   Event {i}: {list(event.keys())}")
                
                # Check if this event has content with parts
                if "content" in event:
                    content = event["content"]
                    logger.info(f"   Content keys: {list(content.keys())}")
                    
                    if "parts" in content:
                        for j, part in enumerate(content["parts"]):
                            logger.info(f"     Part {j}: {list(part.keys())}")
                            if "text" in part:
                                text_content = part["text"]
                                logger.info(f"     Text content: {text_content[:100]}...")
                                agent_text += text_content
            
            if agent_text:
                logger.info(f"🤖 AI Agent Response: {agent_text[:200]}...")

                # Clean up the response - remove generic acknowledgments
                cleaned_response = agent_text.strip()

                # Skip generic responses that don't actually process the request
                generic_phrases = [
                    "okay, i will handle the requests",
                    "i will prioritize using",
                    "as specified in the system instructions",
                    "i'm ready to handle",
                    "just tell me what to send"
                ]

                is_generic = any(phrase in cleaned_response.lower() for phrase in generic_phrases)

                if is_generic and len(cleaned_response) < 300:
                    logger.warning("AI agent gave generic response, falling back to basic processing")
                    return None  # This will trigger fallback processing

                # Return clean response without extra markers for actual processing
                return cleaned_response
            else:
                logger.warning("No text response found in agent events")
                logger.info(f"Full events structure: {json.dumps(events, indent=2)}")
                return "🤖 AI Agent processed your request but didn't return a text response.\n\n⚠️ Falling back to basic processing..."
        else:
            logger.error(f"ADK API error: {adk_response.status_code} - {adk_response.text}")
            return f"❌ AI Agent API Error: {adk_response.status_code}\n\n⚠️ Falling back to basic processing..."
        
    except Exception as e:
        logger.error(f"AI Agent error: {e}")
        return f"❌ AI Agent Error: {str(e)}\n\n⚠️ Falling back to basic processing..."

# Manual parsing removed - AI agent handles everything now

# ============================================================================
# WHATSAPP ENDPOINTS
# ============================================================================

@app.post('/whatsapp/webhook', response_class=PlainTextResponse)
async def whatsapp_webhook(
    request: Request,
    Body: str = Form(default=""),
    From: str = Form(default="")
):
    """Handle incoming WhatsApp messages"""
    try:
        incoming_msg = Body.strip()
        sender_phone = From.replace('whatsapp:+', '')

        logger.info(f"📱 WhatsApp message from {sender_phone}: {incoming_msg}")

        resp = MessagingResponse()

        if not incoming_msg:
            return str(resp)
        
        
        # 🤖 Use AI Agent for all other messages
        try:
            ai_response = process_with_ai_agent(incoming_msg, sender_phone)
            resp.message(ai_response)
            return str(resp)
            #     return str(resp)
        except Exception as e:
            logger.error(f"AI processing failed: {e}")
            resp.message(f"❌ Sorry, I'm having trouble processing your request: {str(e)}")
            return str(resp)
        
    except Exception as e:
        logger.error(f"WhatsApp webhook error: {e}")
        resp = MessagingResponse()
        resp.message("❌ Sorry, there was an error processing your request.")
        return str(resp)

# ============================================================================
# M-PESA CALLBACK ENDPOINTS
# ============================================================================

@app.post('/mpesa/callback', response_model=MPesaCallbackResponse)
async def mpesa_callback(request: Request):
    """Handle M-Pesa payment callbacks"""
    try:
        callback_data = await request.json()
        logger.info(f"💰 M-Pesa callback received: {json.dumps(callback_data, indent=2)}")
        
        # Extract callback information
        body = callback_data.get('Body', {})
        stk_callback = body.get('stkCallback', {})
        
        merchant_request_id = stk_callback.get('MerchantRequestID')
        checkout_request_id = stk_callback.get('CheckoutRequestID')
        result_code = stk_callback.get('ResultCode')
        result_desc = stk_callback.get('ResultDesc')
        
        # Process the callback
        if result_code == 0:
            # Payment successful
            callback_metadata = stk_callback.get('CallbackMetadata', {})
            items = callback_metadata.get('Item', [])
            
            # Extract payment details
            amount = None
            mpesa_receipt_number = None
            phone_number = None
            
            for item in items:
                name = item.get('Name')
                value = item.get('Value')
                
                if name == 'Amount':
                    amount = value
                elif name == 'MpesaReceiptNumber':
                    mpesa_receipt_number = value
                elif name == 'PhoneNumber':
                    phone_number = str(value)
            
            logger.info(f"✅ Payment successful: {amount} KSh from {phone_number}, Receipt: {mpesa_receipt_number}")
            
            # Send WhatsApp confirmation
            if phone_number:
                confirmation_message = f"✅ Payment completed successfully!\n\n💰 Amount: {amount} KSh\n🧾 Receipt: {mpesa_receipt_number}\n📱 Thank you for using our service!"
                send_whatsapp_message(phone_number, confirmation_message)
            
        else:
            # Payment failed
            logger.warning(f"❌ Payment failed: {result_desc}")
            
            # Try to extract phone number from tracking data
            phone_number = payment_tracking.get(checkout_request_id, {}).get('phone_number')
            
            if phone_number:
                failure_message = f"❌ Payment failed\n\n📝 Reason: {result_desc}\n💡 Please try again or check your M-Pesa balance."
                send_whatsapp_message(phone_number, failure_message)
        
        # Store callback data for tracking
        payment_tracking[checkout_request_id] = {
            'result_code': result_code,
            'result_desc': result_desc,
            'timestamp': datetime.now().isoformat(),
            'callback_data': callback_data
        }
        
        return MPesaCallbackResponse(ResultCode=0, ResultDesc="Success")

    except Exception as e:
        logger.error(f"M-Pesa callback error: {e}")
        return MPesaCallbackResponse(ResultCode=1, ResultDesc="Error processing callback")

@app.post('/mpesa/timeout', response_model=MPesaCallbackResponse)
async def mpesa_timeout(request: Request):
    """Handle M-Pesa payment timeouts"""
    try:
        timeout_data = await request.json()
        logger.warning(f"⏱️ M-Pesa timeout: {json.dumps(timeout_data, indent=2)}")

        return MPesaCallbackResponse(ResultCode=0, ResultDesc="Timeout received")

    except Exception as e:
        logger.error(f"M-Pesa timeout error: {e}")
        return MPesaCallbackResponse(ResultCode=1, ResultDesc="Error processing timeout")

# ============================================================================
# UTILITY ENDPOINTS
# ============================================================================

@app.get('/health', response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        service="Unified WhatsApp + M-Pesa Server (FastAPI)",
        status="healthy",
        twilio_configured=twilio_client is not None,
        mpesa_configured=bool(MPESA_CONSUMER_KEY and MPESA_CONSUMER_SECRET),
        endpoints={
            "whatsapp_webhook": "/whatsapp/webhook",
            "mpesa_callback": "/mpesa/callback",
            "mpesa_timeout": "/mpesa/timeout",
            "contacts": "/contacts",
            "health": "/health",
            "docs": "/docs",
            "redoc": "/redoc"
        }
    )

@app.get('/contacts', response_model=ContactsResponse)
async def get_contacts():
    """Get all available contacts"""
    return ContactsResponse(contacts=list_all_contacts())

@app.get('/payment/status/{checkout_request_id}', response_model=PaymentStatusResponse)
async def get_payment_status(checkout_request_id: str):
    """Get payment status by checkout request ID"""
    status = payment_tracking.get(checkout_request_id)
    if status:
        return PaymentStatusResponse(**status)
    else:
        raise HTTPException(status_code=404, detail="Payment not found")

if __name__ == '__main__':
    print("🚀 Starting Unified WhatsApp + M-Pesa Server (FastAPI)...")
    print("📱 WhatsApp webhook: /whatsapp/webhook")
    print("💰 M-Pesa callback: /mpesa/callback")
    print("⏱️ M-Pesa timeout: /mpesa/timeout")
    print("📊 Health check: /health")
    print("📋 Contacts: /contacts")
    print("� API Documentation: /docs")
    print("📖 ReDoc Documentation: /redoc")
    print("�🔗 Single ngrok tunnel needed: ngrok http 5000")

    uvicorn.run(
        "unified_server:app",
        host="0.0.0.0",
        port=5000,
        reload=True,
        log_level="info"
    )
