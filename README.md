# AI M-Pesa Payment Agent

An AI-powered agent that can process M-Pesa payments through natural language commands using Google's ADK and Safaricom's Daraja API.

## Features

- **M-Pesa Integration**: Send payments, check transaction status, validate phone numbers
- **AI-Powered**: Uses Google Gemini 2.0 Flash for natural language understanding
- **Phone Validation**: Validates and formats Kenyan phone numbers
- **Transaction Tracking**: Check payment status and get account balance
- **Simple Tools**: Easy-to-use functions that integrate with the AI agent

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure M-Pesa Credentials

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Get your M-Pesa credentials from [Safaricom Developer Portal](https://developer.safaricom.co.ke/):
   - Consumer Key
   - Consumer Secret
   - Business Short Code
   - Passkey

3. Update `.env` with your credentials:
   ```env
   MPESA_CONSUMER_KEY=your_actual_consumer_key
   MPESA_CONSUMER_SECRET=your_actual_consumer_secret
   MPESA_BUSINESS_SHORT_CODE=your_shortcode
   MPESA_PASSKEY=your_passkey
   MPESA_CALLBACK_URL=https://your-domain.com/mpesa/callback
   MPESA_ENVIRONMENT=sandbox
   ```

### 3. Test the Integration

Run the test script to verify everything works:

```bash
python test_mpesa.py
```

### 4. Use the Agent

```python
from mpesa_agent.agent import root_agent

# The agent now has M-Pesa capabilities
# You can ask it things like:
# - "Send 100 KSh to 0712345678"
# - "Check the status of transaction ABC123"
# - "Validate this phone number: +254712345678"
```

## Available Tools

The agent includes these M-Pesa tools:

### `send_mpesa_payment(phone_number, amount, description)`
Initiates an STK Push payment request.

**Example:**
```python
result = send_mpesa_payment("254712345678", 100.0, "Payment for services")
```

### `check_mpesa_payment_status(checkout_request_id)`
Checks the status of a payment transaction.

**Example:**
```python
status = check_mpesa_payment_status("ws_CO_123456789")
```

### `validate_kenyan_phone(phone_number)`
Validates and formats Kenyan phone numbers.

**Example:**
```python
result = validate_kenyan_phone("0712345678")
# Returns: {"status": "success", "formatted_number": "254712345678"}
```

### `get_mpesa_balance()`
Gets the current business account balance.

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `MPESA_CONSUMER_KEY` | Your app's consumer key | Yes |
| `MPESA_CONSUMER_SECRET` | Your app's consumer secret | Yes |
| `MPESA_BUSINESS_SHORT_CODE` | Your business short code | Yes |
| `MPESA_PASSKEY` | Your app's passkey | Yes |
| `MPESA_CALLBACK_URL` | URL for M-Pesa callbacks | Yes |
| `MPESA_ENVIRONMENT` | `sandbox` or `production` | No (default: sandbox) |

## Security Notes

- Never commit your `.env` file to version control
- Use sandbox environment for testing
- Implement proper callback URL handling for production
- Consider implementing additional security measures for production use

## Next Steps

1. **Test with sandbox**: Use Safaricom's test credentials to test the integration
2. **Add callback handling**: Implement webhook endpoints to handle M-Pesa callbacks
3. **Add WhatsApp integration**: Connect with Twilio or similar service
4. **Enhance NLP**: Add more sophisticated command parsing
5. **Add contact resolution**: Implement contact name to phone number mapping

## Troubleshooting

### Common Issues

1. **"Failed to get M-Pesa access token"**
   - Check your consumer key and secret
   - Ensure you're using the correct environment (sandbox/production)

2. **"Invalid phone number"**
   - Ensure phone numbers are in Kenyan format
   - Use the validation tool to check format

3. **STK Push fails**
   - Verify your business short code and passkey
   - Check that callback URL is accessible (for production)

### Getting Help

- Check the [Safaricom Developer Documentation](https://developer.safaricom.co.ke/docs)
- Review the test script output for detailed error messages
- Ensure all environment variables are properly set
