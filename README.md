# ACL Agent — Run Guide

## 1. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 2. Install dependencies

```bash
pip install -r requirements.txt
```

## 3. Configure environment variables

Create '.env' file 

and add this info:
```bash
Application Settings
APP_NAME="ACL Surgery Patient Assistant"
APP_VERSION="0.1.0"
DEBUG=false

Server Settings
HOST=0.0.0.0
PORT=8000

Database Settings
DATABASE_URL=sqlite:///./acl_agent.db

Logging Settings
LOG_LEVEL=INFO

LLM Settings
OPENAI_API_KEY=your_openai_key_here
```



## 4. Initialize database schema

Use either method:

```bash
# Method A: migrations
alembic upgrade head
```

```bash
# Method B: app auto-creates tables on startup
# (no command needed)
```

## 5. (Optional) Seed demo patients

```bash
python tests/seed_demo.py
```

## 6. Run the app

### Streamlit UI

```bash
streamlit run app/streamlit_app.py
```

Open: `http://localhost:8501`

### FastAPI server

```bash
uvicorn api.main:app --reload --port 8000
```

Open:

- API docs: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/api/v1/health`
