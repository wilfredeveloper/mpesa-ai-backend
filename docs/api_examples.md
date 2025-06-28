# Mpesa Agent API Examples

## 1. Health Check
```bash
curl http://localhost:8000/health
```

## 2. Create a Session
```bash
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user",
    "app_name": "mpesa_agent"
  }'
```

## 3. List Sessions
```bash
curl "http://localhost:8000/sessions?user_id=test_user&app_name=mpesa_agent"
```

## 4. Get Specific Session
```bash
curl "http://localhost:8000/sessions/{session_id}?user_id=test_user&app_name=mpesa_agent"
```

## 5. Send Message to Agent
```bash
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user",
    "session_id": "your_session_id",
    "app_name": "mpesa_agent",
    "message": "Hello, send 100 KSh to 0712345678"
  }'
```

## 6. Delete Session
```bash
curl -X DELETE "http://localhost:8000/sessions/{session_id}?user_id=test_user&app_name=mpesa_agent"
```

## Running Options

### CLI Mode
```bash
python app/main.py cli
```

### Server Mode (default)
```bash
python app/main.py
```

The server will start on http://localhost:8000 with auto-reload enabled.
