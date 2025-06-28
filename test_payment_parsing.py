#!/usr/bin/env python3
"""
Test script for payment request parsing
"""

import re

def test_payment_parsing():
    """Test the payment parsing logic"""
    
    # Test messages
    test_messages = [
        "Send 1000 to 0714025354",
        "send 500 to 0712345678",
        "Pay 200 to 254712345678",
        "Transfer 1500 to +254712345678",
        "Send 300",
        "pay 150",
        "1000 to 0712345678",
        "Hello, how are you?",  # Should not match
        "Check my balance",     # Should not match
        "Send money",          # Should not match (no amount)
    ]
    
    # Payment patterns (same as in callback_server.py)
    payment_patterns = [
        r'(?:send|pay|transfer)\s+(\d+)\s+(?:to|for)\s+(\d+)',  # "send 1000 to 0714025354"
        r'(?:send|pay|transfer)\s+(\d+)',  # "send 1000" (simplified)
        r'(\d+)\s+(?:to|for)\s+(\d+)',  # "1000 to 0714025354" (no verb)
    ]
    
    print("🧪 Testing Payment Request Parsing")
    print("=" * 50)
    
    for message in test_messages:
        message_lower = message.lower().strip()
        amount = None
        recipient_number = None
        matched_pattern = None
        
        # Try to match payment patterns
        for i, pattern in enumerate(payment_patterns):
            match = re.search(pattern, message_lower)
            if match:
                amount = int(match.group(1))
                if len(match.groups()) > 1:
                    recipient_number = match.group(2)
                matched_pattern = i + 1
                break
        
        # Print results
        if amount:
            print(f"✅ '{message}'")
            print(f"   Amount: {amount} KSh")
            print(f"   Recipient: {recipient_number or 'None (sender pays)'}")
            print(f"   Pattern: {matched_pattern}")
        else:
            print(f"❌ '{message}' - No payment detected")
        print()

if __name__ == "__main__":
    test_payment_parsing()
