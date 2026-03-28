# Contributing to RedisAgent

Thank you for your interest in contributing! Here's how to get involved.

## Development Setup

```bash
git clone https://github.com/YOUR_USERNAME/redis-mcp-agent.git
cd redis-mcp-agent
cp .env.example .env   # fill in your GOOGLE_API_KEY and REDIS_URL
```

**Backend**
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --port 8001 --reload
```

**Frontend**
```bash
cd frontend
pip install -r requirements.txt
streamlit run app.py
```

## Project Structure

| File | Purpose |
|---|---|
| `backend/main.py` | FastAPI app, ADK runner, `/chat` and `/health` endpoints |
| `backend/server.py` | Redis MCP server — exposes `ping_redis`, `list_keys`, `get_key`, `set_key` |
| `backend/redis_dump.py` | Bulk JSON → Redis loader |
| `backend/utils.py` | SAP/enterprise API helpers and Redis caching layer |
| `frontend/app.py` | Streamlit chat UI |

## Adding a New MCP Tool

1. Open `backend/server.py`
2. Add a new `@mcp.tool()` decorated function
3. The ADK agent will discover and use it automatically on next startup

```python
@mcp.tool()
def delete_key(key: str) -> str:
    """Delete a single key from Redis."""
    try:
        r = _redis()
        count = r.delete(key)
        return json.dumps({"key": key, "deleted": bool(count)})
    except Exception as e:
        return json.dumps({"error": str(e)})
```

## Pull Request Guidelines

- Keep PRs focused — one feature or fix per PR
- Add a brief description of what changed and why
- Make sure `ruff check` passes on your changes
- Test against a live Redis instance before submitting

## Reporting Issues

Please include:
- Python version (`python --version`)
- Error message / traceback
- Steps to reproduce
- Whether ADK and Redis are both running (`GET /health`)
