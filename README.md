# Anthos AI Server

An intelligent, multi-agent email categorization, summarization, and priority scoring engine built with **FastAPI**, **LangGraph**, **LangChain**, and **PostgreSQL/Supabase**.

Anthos AI analyzes incoming email batches using an automated state machine featuring pre-processing, regex-based fast routing, multi-provider LLM categorization, supervisor verification with iterative self-correction, and real-time WebSocket progress streaming to the frontend.

---

## Table of Contents

1. [Architecture & Workflow](#architecture--workflow)
2. [Key Features](#key-features)
3. [Project Structure](#project-structure)
4. [Prerequisites](#prerequisites)
5. [Environment Variables](#environment-variables)
6. [Installation & Setup](#installation--setup)
7. [Running the Server](#running-the-server)
8. [API Reference & Protocol](#api-reference--protocol)
   - [WS /analyse (Real-Time WebSocket)](#ws-analyse-real-time-websocket)
   - [POST /analyse (HTTP Fallback)](#post-analyse-http-fallback)
   - [GET /health](#get-health)
   - [GET /time](#get-time)
9. [Frontend WebSocket Integration Example](#frontend-websocket-integration-example)
10. [Supported LLM Providers](#supported-llm-providers)
11. [Database Models](#database-models)
12. [Deployment](#deployment)

---

## Architecture & Workflow

The core intelligence layer is implemented as a **LangGraph StateGraph** state machine (`app/services/src/graph.py`):

```
                       [Incoming Email]
                              │
                              ▼
                 [pre_processing_raw_emails]
           (HTML stripping via html2text & normalization)
                              │
                              ▼
                [regex_email_categorization]
                              │
               Is promotional / newsletter?
                  /                       \
             [YES]                         [NO]
               │                             │
               ▼                             ▼
       Tag as "Others"              [llm_categorization]
      (confidence = 1.0)        (Structured output: category,
               │                priority, confidence, summary)
               │                             │
               │                             ▼
               │                     [llm_supervisor]
               │                (Verifies classification)
               │                             │
               │                   Supervisor approved?
               │                      /              \
               │                 [YES]                [NO]
               │                   │                    │
               │                   │            Retry count < 2?
               │                   │              /          \
               │                   │         [YES]            [NO]
               │                   │           │                │
               │                   │           ▼                ▼
               │                   │  [retry_and_versioning]  Accept
               │                   │   (Increment retry,      result
               │                   │    append version,
               │                   │    feedback loop)
               │                   │           │
               │                   │           ▼
               │                   │  (Re-enter LLM node)
               │                   │
               ▼                   ▼
              =======================
                    END (Output)
              =======================
```

### Workflow Steps:
1. **Pre-processing**: HTML emails are stripped to plain text using `html2text` with surrogate error handling and normalized whitespace.
2. **Regex Fast Routing**: Automatically classifies newsletters and promotional emails (`unsubscribe`, `newsletter` pattern matching) as `"Others"` with `1.0` confidence, bypassing the LLM to minimize latency and token consumption.
3. **Dynamic User Categories**: Injects user-defined categories (pulled from PostgreSQL or provided in payload) with descriptions and examples into the LLM system prompt.
4. **LLM Categorization**: Uses LangChain's unified `init_chat_model` with structured output (`CategorizeEmailOutput`) throttled via an `asyncio.Semaphore(2)` to generate category, confidence score (0–1), priority score (0–10), and a concise 50-word summary.
5. **Supervisor Verification**: A secondary LLM agent (`gemini-3.5-flash-lite` or default model) reviews the classification against category descriptions and either approves or provides specific corrective feedback.
6. **Self-Correction & Versioning**: If rejected by the supervisor and max retries (2) have not been reached, the system creates a new version, feeds the supervisor's feedback back into the categorization agent, and re-classifies.
7. **Concurrency & Throttling**: Batches are processed concurrently using `asyncio.gather` bounded by a semaphore (`MAX_CONCURRENT_EMAILS = 10`).

---

## Key Features

- **Real-Time WebSocket Streaming (`/analyse`)**: Replaced blocking HTTP request/response on `/analyse` with bidirectional WebSocket streaming.
  - **Immediate Confirmation**: Instantly acknowledges receipt of requests from `ANTHOSWEB_URL`.
  - **Console-Level Live Progress**: Captures and streams all console log entries (cleaning, regex classification, LLM calls, supervisor checks, retries) to the frontend as they happen.
  - **Completed Payload**: Emits full structured analysis results upon completion.
- **Strict Origin Security**: Verifies incoming WebSocket connections against `ANTHOSWEB_URL` (`cors_origins`), rejecting unauthorized origins with status `1008 (Policy Violation)`.
- **Multi-Provider LLM Flexibility**: Supports Google Gemini, OpenAI, Anthropic, AWS Bedrock, OpenRouter, Perplexity, NVIDIA, Groq, Ollama, and DeepSeek.
- **Relational Persistence (SQLAlchemy/PostgreSQL)**: Integrates directly with Supabase/PostgreSQL to read user categories, model API keys, and settings.
- **Context-Isolated Logging**: Thread/task-safe log streaming via `contextvars.ContextVar`, ensuring simultaneous client connections only receive their own relevant logs without leaking or duplicating data.

---

## Project Structure

```
anthos.ai/
├── app/
│   ├── __init__.py                # Package root
│   ├── main.py                    # FastAPI application initialization & CORS config
│   ├── settings.py                # Environment configuration using pydantic-settings
│   ├── schemas.py                 # Pydantic schemas (requests, responses, models)
│   ├── logging_config.py          # Unified logger & WebSocketLogHandler
│   ├── database/
│   │   ├── __init__.py
│   │   ├── db.py                  # Database engine & sessionmaker (get_db)
│   │   └── models.py              # SQLAlchemy ORM models (User, Category, Model, etc.)
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── health.py              # GET /health
│   │   ├── time.py                # GET /time
│   │   └── analyse.py             # WS /analyse & HTTP POST fallback
│   └── services/
│       ├── __init__.py
│       └── src/
│           ├── agents.py          # Multi-provider LLM factory (Agent)
│           ├── graph.py           # LangGraph StateGraph definition & compilation
│           ├── nodes.py           # Graph nodes (EmailCleaner, Nodes class)
│           ├── prompt_template.py # System prompts & few-shot categorization templates
│           ├── state.py           # LangGraph state definitions & Pydantic models
│           └── workflow.py        # EmailWorkflow orchestrator (concurrency, gather)
├── main.py                        # Root runner for uvicorn
├── requirements.txt               # Pinned Python package dependencies
├── render.yaml                    # Deployment configuration for Render
└── README.md                      # Project documentation
```

---

## Prerequisites

- **Python**: 3.10 or higher (compatible with Python 3.10 – 3.14)
- **pip**: Package installer for Python
- **PostgreSQL / Supabase**: For persistent user settings, categories, and models
- **Google Gemini API Key**: For default categorization and supervisor models

---

## Environment Variables

Create a `.env` file in the project root (see `.env.sample`):

```env
# Required for default Gemini models and supervisor agent
GOOGLE_API_KEY="your-google-api-key"

# PostgreSQL connection string (Supabase / local PostgreSQL)
DATABASE_URL="postgresql://postgres:password@db.example.com:5432/postgres"

# Frontend origin URL(s) for CORS and WebSocket origin verification (comma-separated if multiple)
ANTHOSWEB_URL="https://anthos-opensource.vercel.app,http://localhost:3000"

# Optional server port (defaults to 8000)
PORT=8000
```

---

## Installation & Setup

```bash
# 1. Clone repository
git clone https://github.com/your-org/anthos.ai.git
cd anthos.ai

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate      # On Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

---

## Running the Server

### Development Mode

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Or execute directly:

```bash
python main.py
```

Server endpoints will be live at `http://127.0.0.1:8000`.

Interactive Swagger documentation is available at:
- **Swagger UI**: `http://127.0.0.1:8000/docs`
- **ReDoc**: `http://127.0.0.1:8000/redoc`

---

## API Reference & Protocol

### WS `/analyse` (Real-Time WebSocket)

The primary interface for email analysis. Connect via WebSocket at `ws://127.0.0.1:8000/analyse` (or `wss://...` in production).

#### 1. Handshake & Origin Verification
The browser client initiates connection. The server validates that `Origin` matches `ANTHOSWEB_URL`. If unauthorized, the connection is rejected with code `1008 (WS_1008_POLICY_VIOLATION)`.

#### 2. Client Request Frame (JSON)
The client sends a JSON message containing the email batch and model configuration:

```json
{
  "emails": [
    {
      "id": "msg_001",
      "subject": "Q3 Budget Review",
      "body": "Hi team, please find attached the revised financial forecasts for Q3.",
      "sender": "finance@company.com",
      "threadId": "thread_abc123"
    }
  ],
  "model": {
    "id": "model_gemini_2_flash",
    "name": "gemini-2.0-flash",
    "provider": "google",
    "default": true
  }
}
```

#### 3. Server Immediate Confirmation Frame
Immediately after validating the payload, the server sends:

```json
{
  "type": "confirmation",
  "status": "confirmed",
  "message": "Analysis request confirmed for 1 email(s). Processing started.",
  "email_count": 1,
  "model_name": "gemini-2.0-flash"
}
```

#### 4. Real-Time Log / Progress Frames
As processing progresses through the LangGraph pipeline, the exact log entries printed to the console are streamed to the frontend:

```json
{
  "type": "log",
  "status": "processing",
  "level": "INFO",
  "name": "app.services.src.nodes",
  "message": "Cleaning email msg_001",
  "timestamp": "2026-09-09T14:30:00.123456Z"
}
```

```json
{
  "type": "log",
  "status": "processing",
  "level": "INFO",
  "name": "app.services.src.nodes",
  "message": "Running LLM categorization for email msg_001 (retry_counter=0)",
  "timestamp": "2026-09-09T14:30:01.456789Z"
}
```

```json
{
  "type": "log",
  "status": "processing",
  "level": "INFO",
  "name": "app.services.src.nodes",
  "message": "Supervisor approved email msg_001 |",
  "timestamp": "2026-09-09T14:30:02.789012Z"
}
```

#### 5. Server Completion Frame
When the batch analysis is complete:

```json
{
  "type": "complete",
  "status": "completed",
  "results": [
    {
      "id": "msg_001",
      "threadId": "thread_abc123",
      "summary": "Financial forecasts and budget adjustments for Q3 requiring review.",
      "category": "Finance",
      "priority_score": 2.0,
      "confidence_score": 0.96,
      "versions": [1],
      "retry_count": 0
    }
  ]
}
```

#### 6. Error Frame (if an error occurs)
```json
{
  "type": "error",
  "status": "error",
  "message": "Failed to analyze emails",
  "detail": "Detailed error explanation"
}
```

---

### POST `/analyse` (HTTP Fallback)

Backward-compatible HTTP endpoint for non-WebSocket clients or testing.

- **URL**: `/analyse`
- **Method**: `POST`
- **Headers**: `Content-Type: application/json`
- **Body**: Same structure as the WebSocket request frame (`AnalyseRequest`).
- **Response**:
```json
{
  "results": [
    {
      "id": "msg_001",
      "threadId": "thread_abc123",
      "summary": "Financial forecasts and budget adjustments for Q3 requiring review.",
      "category": "Finance",
      "priority_score": 2.0,
      "confidence_score": 0.96,
      "versions": [1],
      "retry_count": 0
    }
  ]
}
```

---

### GET `/health`

Liveness probe for load balancers and deployment services (Render, Railway, Kubernetes).

- **Response — 200 OK**:
```json
{
  "status": "ok"
}
```

---

### GET `/time`

Returns current server UTC time in ISO-8601 format to detect client-server clock skew.

- **Response — 200 OK**:
```json
{
  "utc_time": "2026-09-09T09:15:00+00:00"
}
```

---

## Frontend WebSocket Integration Example

Here is a ready-to-use JavaScript/TypeScript integration example for connecting from `ANTHOSWEB_URL`:

```javascript
// Anthos AI WebSocket Client
const socket = new WebSocket("ws://localhost:8000/analyse");

socket.onopen = () => {
  console.log("Connected to Anthos AI analysis stream");

  // Send email batch for analysis
  const requestPayload = {
    emails: [
      {
        id: "email_101",
        subject: "Contract Agreement Draft",
        body: "Please review the updated vendor contract terms attached.",
        sender: "legal@vendor.com",
        threadId: "th_101"
      }
    ],
    model: {
      id: "model_default",
      name: "gemini-2.0-flash",
      provider: "google",
      default: true
    }
  };

  socket.send(JSON.stringify(requestPayload));
};

socket.onmessage = (event) => {
  const data = JSON.parse(event.data);

  switch (data.type) {
    case "confirmation":
      // 1. Immediate confirmation received
      console.log(`[CONFIRMED] ${data.message} (${data.email_count} emails)`);
      break;

    case "log":
      // 2. Real-time console log streamed from backend
      console.log(`[STATUS - ${data.level}] ${data.message}`);
      // Update your UI progress indicator or terminal window here
      break;

    case "complete":
      // 3. Analysis finished with complete results
      console.log("[COMPLETED] Final Results:", data.results);
      break;

    case "error":
      // Error handling
      console.error("[ERROR]", data.message, data.detail);
      break;
  }
};

socket.onerror = (err) => {
  console.error("WebSocket Error:", err);
};

socket.onclose = (event) => {
  console.log(`WebSocket closed: code=${event.code}, reason=${event.reason}`);
};
```

---

## Supported LLM Providers

Anthos AI dynamically configures models through `init_chat_model` using provider credentials:

| Provider | Key in Config | Provider Library |
|---|---|---|
| **Google** | `google` | `langchain-google-genai` / `langchain-google-vertexai` |
| **OpenAI** | `openai` | `langchain-openai` |
| **Anthropic** | `anthropic` | `langchain-anthropic` |
| **Amazon Bedrock** | `amazon bedrock` | `langchain-aws` |
| **OpenRouter** | `openrouter` | `langchain-openrouter` |
| **Perplexity** | `perplexity` | `langchain-perplexity` |
| **NVIDIA** | `nvidia` | `langchain-nvidia-ai-endpoints` |
| **Groq** | `groq` | `langchain-groq` |
| **Ollama** | `ollama` | `langchain-ollama` |
| **DeepSeek** | `deepseek` | `langchain-deepseek` |

---

## Database Models

The database models in `app/database/models.py` map directly to PostgreSQL:

- **`User`**: User accounts, emails, verification state, relationships to settings and mails.
- **`EncryptedMail`**: Stored user emails with encrypted ciphertext, category tags (`ARRAY(Text)`), priority array (`ARRAY(Numeric)`), and version history.
- **`Category`**: User or system defined categories with name, description, and few-shot examples (`JSONB`).
- **`Settings`**: User model preferences and available model lists.
- **`Model`**: Saved model configurations (`id`, `name`, `provider`, `api_key`, `setting_id`).
- **`Session`**, **`Account`**, **`Verification`**: Auth sessions and credential management.

---

## Deployment

The application is configured for deployment on **Render** using `render.yaml`:

```yaml
services:
  - type: web
    name: anthos-ai
    runtime: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Ensure the following environment variables are set in the deployment dashboard:
- `GOOGLE_API_KEY`
- `DATABASE_URL`
- `ANTHOSWEB_URL`
