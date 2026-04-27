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

```bash
cp .env.example .env
```

Edit `.env` and set:

```env
OPENAI_API_KEY=sk-...
```

Optional (only needed for real Twilio SMS):

```env
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=+1...
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
