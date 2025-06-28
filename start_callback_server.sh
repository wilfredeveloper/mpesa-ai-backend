#!/bin/bash

# M-Pesa Callback Server Startup Script
echo "🚀 Starting M-Pesa Callback Server with ngrok"
echo "=============================================="

# Check if virtual environment exists
if [ ! -d "env" ]; then
    echo "❌ Virtual environment not found. Please create one first:"
    echo "   python -m venv env"
    exit 1
fi

# Activate virtual environment
echo "📦 Activating virtual environment..."
source env/bin/activate

# Check if Flask is installed
if ! python -c "import flask" 2>/dev/null; then
    echo "📥 Installing Flask..."
    pip install flask
fi

# Start the callback server in background
echo "🌐 Starting callback server on port 8001..."
python callback_server.py &
SERVER_PID=$!

# Wait a moment for server to start
sleep 3

# Start ngrok to expose the server
echo "🔗 Starting ngrok tunnel..."
echo "📋 Your callback URL will be shown below..."
echo ""

# Start ngrok (this will run in foreground)
ngrok http 8001

# When ngrok stops, kill the server
echo "🛑 Stopping callback server..."
kill $SERVER_PID 2>/dev/null

echo "✅ Cleanup complete!"
