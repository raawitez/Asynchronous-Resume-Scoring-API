# AI Resume Processing Backend

An asynchronous, event-driven microservice system built with FastAPI, RabbitMQ, Redis, and PostgreSQL for ingesting, parsing, scoring, and caching resume evaluations.

---

## Architecture Overview

```
[ Client ]
    │ (PDF Upload + JWT)
    ▼
[ FastAPI Server ] 
    │  ├─► Enforces MIME / Size limits & Saves File (Local Disk / AWS S3)
    │  ├─► Inserts DB record (status = "uploaded")
    │  └─► Publishes 'resume_uploaded' event
    ▼
[ RabbitMQ Message Broker ] (Queue: resume_processing, Durable)
    │
    ▼
[ Background Worker (Consumer) ]
    ├─► Fair dispatch (prefetch_count = 1)
    ├─► Updates DB (status = "processing")
    ├─► Extracts text via PyPDF2
    ├─► Calculates weighted score (0–100) & actionable feedback
    ├─► Updates DB (status = "scored")
    └─► Caches result in Redis (resume_score:{id}, TTL = 1h)
```

---

## Tech Stack & Components

| Component | Technology | Role |
|---|---|---|
| API Framework | FastAPI (Python 3.11+) | Async REST API, route handlers, OpenAPI specs |
| Authentication | Native bcrypt + python-jose | JWT Token generation and verification |
| Message Broker | RabbitMQ (pika) | Asynchronous job dispatching and queue management |
| Background Worker | Python Consumer Process | Decoupled parsing, NLP scoring, and DB synchronization |
| Database | PostgreSQL / SQLite (SQLAlchemy 2.0) | Persistent resume records, statuses, and audit timestamps |
| Cache Tier | Redis (redis-py) | Sub-millisecond cached score lookups with 1-hour TTL |
| Storage | Local Disk / AWS S3 (boto3) | Configurable PDF storage via USE_S3 feature toggle |
| Observability | Loguru & Custom Middleware | Structured JSON request logs, K8s liveness/readiness probes |

---

## Scoring Matrix Breakdown

The rule-based analysis engine scores candidates on a 100-point scale:

- **Technical Skills (40%):** Evaluates languages, backend/frontend frameworks, databases, cloud, and DevOps keywords.
- **Resume Structure (30%):** Detects industry-standard ATS headers (Experience, Education, Projects, Skills, Certifications).
- **Action Verbs (20%):** Identifies impact verbs (Built, Architected, Optimized, Scaled, Implemented).
- **Contact Details (10%):** Verifies email syntax, phone numbers, and profile links (GitHub, LinkedIn).

---

## Project Structure

```
AI-Resume-Processing-Backend/
├── resume-api/
│   ├── app/
│   │   ├── auth/               # Password hashing & JWT logic
│   │   ├── cache/              # Redis client wrapper & fail-open handlers
│   │   ├── core/               # File validators, metrics, S3 client, logging
│   │   ├── messaging/          # RabbitMQ client & event schema contracts
│   │   ├── middleware/         # Request timing & structured logging middleware
│   │   ├── models/             # SQLAlchemy ORM definitions
│   │   ├── routers/            # Auth, Resume, Health, and Metrics routes
│   │   ├── schemas/            # Pydantic request/response schemas
│   │   ├── services/           # Business logic & cache-aside orchestration
│   │   ├── database.py         # DB connection pool engine & session setup
│   │   ├── dependencies.py     # FastAPI dependency injectors (Auth, DB)
│   │   └── main.py             # FastAPI entry point & lifespan manager
│   ├── processing/
│   │   ├── parser.py           # PyPDF2 extraction with error boundary
│   │   └── scorer.py           # Multi-category weighted scoring engine
│   ├── docker-compose.yml     # Local orchestration (API + RabbitMQ + Redis + DB)
│   ├── Dockerfile             # Container build for API
│   ├── requirements.txt       # Project dependencies
│   ├── start.sh               # Production runner script (Worker + API)
│   └── worker.py              # Background consumer process
└── render.yaml                # Cloud deployment blueprint
```

---

## Getting Started (Local Setup)

### 1. Prerequisites
- Python 3.11+
- Redis & RabbitMQ instances (or running via Docker)

### 2. Environment Configuration
Create a `.env` file inside `resume-api/`:

```env
# Application & Security
SECRET_KEY=your-super-secret-jwt-key
TOKEN_EXPIRE_MINUTES=60

# Database (PostgreSQL or SQLite fallback)
DATABASE_URL=sqlite:///./resume.db

# Message Broker
RABBITMQ_URL=amqp://guest:guest@localhost:5672/

# Cache
REDIS_URL=redis://localhost:6379/0

# Storage (Set to true to use AWS S3)
USE_S3=false
S3_BUCKET_NAME=your-bucket-name
AWS_REGION=ap-south-1
```

### 3. Installation

```powershell
# Navigate into api folder
cd resume-api

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Running the Application

Open two terminal windows:

**Terminal 1 — Background Worker:**
```powershell
python worker.py
```

**Terminal 2 — FastAPI Server:**
```powershell
uvicorn app.main:app --reload --port 8000
```

---

## API Endpoints

### Authentication
- `POST /auth/register` — Register a new user account.
- `POST /auth/login` — Authenticate and obtain a JWT access token.

### Resume Processing (Requires Bearer Token)
- `POST /resume/upload` — Upload a PDF resume (`multipart/form-data`). Returns `202 Accepted` with `resume_id`.
- `GET /resume/{resume_id}/status` — Check processing status (`uploaded`, `processing`, `scored`, `failed`).
- `GET /resume/{resume_id}/score` — Retrieve full analysis score, letter grade, breakdown, and feedback.

### Health & Observability
- `GET /health/live` — Liveness probe.
- `GET /health/ready` — Readiness probe checking database connectivity.
- `GET /health` — Full diagnostic check across PostgreSQL, Redis, and RabbitMQ.
- `GET /metrics` — Operational summary metrics.
- `GET /docs` — Interactive Swagger UI documentation.