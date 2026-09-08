# Anthos API

A simple, modular **FastAPI** server that exposes three HTTP endpoints:
`/health`, `/time`, and `/analyse`. Written in plain Python with no magic —
easy to read, easy to extend.

---

## Table of Contents

1. [Project Structure](#project-structure)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Running the Server](#running-the-server)
5. [Endpoints](#endpoints)
   - [GET /health](#get-health)
   - [GET /time](#get-time)
   - [POST /analyse](#post-analyse)
6. [Configuration](#configuration)
7. [Testing](#testing)
8. [Design Decisions](#design-decisions)
9. [Extending the Project](#extending-the-project)

---

## Project Structure

```
anthos.ai/
├── app/
│   ├── __init__.py            # marks `app` as a Python package
│   ├── main.py                # FastAPI app instance + router registration
│   ├── schemas.py             # all Pydantic request/response models
│   ├── routes/
│   │   ├── __init__.py        # marks `routes` as a sub-package
│   │   ├── health.py          # GET /health
│   │   ├── time.py            # GET /time
│   │   └── analyse.py         # POST /analyse (imports from services/)
│   └── services/
│       ├── __init__.py        # marks `services` as a sub-package
│       └── analyser.py        # pure-Python email analysis logic
├── requirements.txt           # pinned runtime dependencies
└── README.md                  # this file
```

### Why this layout?

| Layer | Responsibility |
|---|---|
| `main.py` | Creates the FastAPI app and mounts routers. Nothing else. |
| `routes/` | One file per endpoint. Each file owns only its HTTP contract. |
| `services/` | Business logic with zero FastAPI imports. Easily unit-tested. |
| `schemas.py` | Single source of truth for every request/response shape. |

---

## Prerequisites

| Tool | Minimum version |
|---|---|
| Python | 3.10 |
| pip | 22.x |

No Docker, no databases, no environment variables are required to run the
server locally.

---

## Installation

```bash
# 1. Clone or enter the project directory
cd anthos.ai

# 2. Create and activate a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

---

## Running the Server

```bash
# From the project root (the directory that contains `app/`)
uvicorn app.main:app --reload
```

The `--reload` flag restarts the server automatically whenever a source file
changes — handy during development.

Default address: **http://127.0.0.1:8000**

### Interactive API docs

FastAPI generates interactive documentation automatically:

| UI | URL |
|---|---|
| Swagger UI | http://127.0.0.1:8000/docs |
| ReDoc | http://127.0.0.1:8000/redoc |

---

## Endpoints

### GET /health

**Purpose:** Liveness probe. Returns immediately with a status of `"ok"`.
Use this with load-balancers, container orchestrators (Kubernetes, Railway,
Render, Fly.io), or uptime monitors.

**Request**

```
GET /health HTTP/1.1
Host: 127.0.0.1:8000
```

**Response — 200 OK**

```json
{
  "status": "ok"
}
```

**cURL example**

```bash
curl http://127.0.0.1:8000/health
```

---

### GET /time

**Purpose:** Returns the current server time in UTC, formatted as an
ISO-8601 string. Clients can use this to detect clock-skew or simply
to sanity-check connectivity.

**Request**

```
GET /time HTTP/1.1
Host: 127.0.0.1:8000
```

**Response — 200 OK**

```json
{
  "utc_time": "2026-08-12T18:00:00+00:00"
}
```

The timestamp always includes the `+00:00` UTC offset so there is no
ambiguity about the timezone.

**cURL example**

```bash
curl http://127.0.0.1:8000/time
```

---

### POST /analyse

**Purpose:** Accepts an email (subject + body) and returns basic analytical
metadata — word count, sentiment, intent, and any email addresses found in
the body.

**Request body** (`application/json`)

| Field | Type | Required | Description |
|---|---|---|---|
| `subject` | string | No | Email subject line. Improves intent detection. |
| `body` | string | **Yes** | Full email body (plain text or HTML). |

```json
{
  "subject": "Re: Invoice #1234",
  "body": "Hi, please find the attached invoice. Contact billing@example.com if you have questions. Thanks!"
}
```

**Response — 200 OK**

| Field | Type | Description |
|---|---|---|
| `word_count` | integer | Number of whitespace-delimited words in the body. |
| `sentiment` | string | "positive" · "neutral" · "negative" |
| `intent` | string | "question" · "request" · "informational" |
| `emails_found` | array of strings | Email addresses detected via regex, deduplicated. |

```json
{
  "word_count": 16,
  "sentiment": "positive",
  "intent": "request",
  "emails_found": ["billing@example.com"]
}
```

**cURL example**

```bash
curl -X POST http://127.0.0.1:8000/analyse \
     -H "Content-Type: application/json" \
     -d '{"subject":"Quick question","body":"Can you please send me the report? Thanks!"}'
```

**How analysis works**

The analysis is entirely rule-based (no external ML libraries) and lives
in `app/services/analyser.py`:

- **Word count** — `str.split()` on the body.
- **Sentiment** — counts overlapping keywords against curated positive/negative
  word lists. Whichever side scores higher wins; ties resolve to `"neutral"`.
- **Intent** — searches for question markers (`?`, `how`, `what`, …) first,
  then request markers (`please`, `kindly`, `could you`, …), defaulting to
  `"informational"`.
- **Email extraction** — standard RFC-5321-ish regex, deduplicated in
  first-seen order.

---

## Configuration

There are no required environment variables. The server runs with its
defaults out of the box.

If you want to customise the host/port/log-level, pass flags to `uvicorn`:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080 --log-level info
```

---

## Testing

The service layer has no FastAPI dependency, so you can test it with plain
`pytest` without spinning up a server:

```bash
pip install pytest
pytest
```

For HTTP-level tests, use FastAPI's built-in TestClient:

```python
# tests/test_health.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

```python
# tests/test_analyser.py
from app.services.analyser import analyse_email

def test_word_count():
    result = analyse_email(subject=None, body="hello world foo")
    assert result.word_count == 3

def test_sentiment_positive():
    result = analyse_email(subject=None, body="This is great, thank you!")
    assert result.sentiment == "positive"

def test_email_extraction():
    result = analyse_email(subject=None, body="reach me at foo@bar.com")
    assert "foo@bar.com" in result.emails_found
```

---

## Design Decisions

| Decision | Rationale |
|---|---|
| Separate `routes/` and `services/` | Routes own HTTP concerns; services own logic. This makes the analyser testable without an HTTP server. |
| All schemas in one `schemas.py` | Single place to look up any request/response shape. Avoids scattered Pydantic models. |
| No external NLP library | Keeps the dependency footprint tiny and installation fast. Replace `analyser.py` internals with spaCy/HuggingFace calls when needed. |
| `uvicorn[standard]` | Includes `uvloop` and `httptools` for better async performance with no extra config. |

---

## Extending the Project

- **Add a new endpoint** — create a new file in `app/routes/`, define an
  `APIRouter`, and `include_router` it in `app/main.py`.
- **Swap in ML sentiment analysis** — edit only `_detect_sentiment()` in
  `app/services/analyser.py`. The route and schema are unaffected.
- **Add a database** — introduce `app/db.py` for connection management and
  import it from whichever service needs it. Routes stay clean.
- **Authentication** — add a FastAPI `Depends` dependency to any route that
  needs it without touching the service layer.
