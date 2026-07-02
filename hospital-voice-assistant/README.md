# Hospital AI Voice Assistant

A production-ready, multilingual AI Voice Assistant built for hospital
patients.

The assistant listens to a patient's voice, understands the request in any
supported language, matches it against a predefined hospital service
catalog using semantic search, generates validated JSON, stores the
request, optionally forwards it to the Hospital Management System, and
replies using natural voice.

This project is designed as an **independent microservice** and can later
be integrated with any Hospital Management System without changing the
core AI logic.

---

# Features

- Streaming Voice Conversation
- LiveKit Voice Transport
- Deepgram Streaming Speech-to-Text (Nova-3)
- Automatic Language Detection
- Multilingual Intent Classification
- Semantic Search using BGE-M3 + FAISS
- Rule-Based Slot Extraction
- Groq LLM Fallback (only when confidence < 0.85)
- Cartesia Streaming Text-to-Speech (Sonic)
- PostgreSQL Persistence
- Redis Session Cache
- Docker Compose Deployment
- Hospital API Adapter Pattern
- Production Logging
- Health Checks
- Fully Async FastAPI Backend
- Angular 17 Frontend

---

# Technology Stack

| Component            | Technology                        |
|----------------------|-----------------------------------|
| Frontend             | Angular 17                        |
| Backend              | FastAPI (Async)                   |
| Voice Transport      | LiveKit                           |
| Speech-to-Text       | Deepgram Streaming Nova-3         |
| Language Detection   | Deepgram                          |
| Semantic Model       | BGE-M3                            |
| Vector Search        | FAISS                             |
| Rule Engine          | Python                            |
| LLM Fallback         | Groq `llama-3.3-70b-versatile`    |
| Text-to-Speech       | Cartesia Sonic                    |
| Database             | PostgreSQL 17                     |
| Cache                | Redis 7                           |
| Deployment           | Docker Compose                    |

---

# Architecture

```
Patient
   │
   ▼
LiveKit
   │
   ▼
Deepgram Streaming STT
   │
   ▼
Original Transcript
   │
   ▼
Language Detection
   │
   ▼
BGE-M3 Multilingual Embedding
   │
   ▼
FAISS Semantic Search
   │
   ▼
Top-K Candidate Services
   │
   ▼
Business Rule Engine
   • Room Number
   • Quantity
   • Time
   • Priority
   • Slot Extraction
   • Keyword Boost (optional)
   │
   ▼
Confidence Calculation
   │
   ▼
Confidence ≥ 0.85 ?
   ├── YES ──► Validated JSON
   └── NO  ──► Groq LLM Fallback
                    │
                    ▼
              JSON Validation
                    │
                    ▼
             Persist Request  (PostgreSQL)
                    │
                    ▼
             HospitalApiAdapter  (default: no-op)
                    │
                    ▼
             Cartesia Streaming TTS
                    │
                    ▼
                 Patient
```

---

# Design Principles

## Semantic Search First
The primary signal is semantic similarity using BGE-M3 embeddings.
The classifier does **not** rely on keywords. Keywords only provide a
small confidence boost (≤ +0.10).

## No Translation Required
BGE-M3 is multilingual. Patient requests remain in their original
language. Hindi, Spanish, French, German, Arabic, Japanese, Tamil,
Gujarati, Punjabi… all map directly to the same English hospital
service. Translation is optional and used only for audit logs, reporting,
and hospital ticket text — not for semantic matching. Toggle with
`TRANSLATE_FOR_AUDIT=true` in `.env`.

---

# Intent Classification Pipeline

```
Speech → Deepgram STT → Language Detection → BGE-M3 Embedding →
FAISS → Top-K Services → Business Rule Validation →
Confidence Score → JSON
```

---

# Rule Engine

The Rule Engine extracts structured information:

- Room Number
- Bed Number
- Quantity
- Time
- Priority
- Urgency

It also protects against semantically-similar but invalid matches. For
example, if a patient says *"I need coconut water"*, semantic search may
suggest `DRINKING_WATER`, but the top semantic score falls below
`MIN_SEMANTIC_THRESHOLD` (0.35 by default) or the LLM refuses to pick a
match — so the assistant returns `UNKNOWN_SERVICE`.

---

# LLM Fallback

The LLM is **not** used for every request. It is used **only** when
confidence < 0.85.

Model: **Groq `llama-3.3-70b-versatile`**

The LLM receives the hospital service catalog and MUST choose only from
existing services. It cannot invent categories or services.

---

# Unknown Services

If no service matches, the assistant returns:

```json
{ "status": "UNKNOWN_SERVICE" }
```

The original transcript is stored in the `unknown_requests` table for
later review. Hospital administrators can:

- List pending unknowns:
  `GET /api/v1/unknown-requests?status=pending`
- Mark an unknown as reviewed / added to catalog:
  `PATCH /api/v1/unknown-requests/{id}` with
  `{ "review_status": "added_to_catalog" }`

They can then add new services to the catalog and rebuild the index.

---

# Hospital Service Catalog

Stored in PostgreSQL. Each service contains:

- Category
- Service code
- Description
- Example utterances
- Priority
- Required slots

The FAISS index is built from this catalog on startup and whenever
`POST /api/v1/services/rebuild-index` is called.

---

# Hospital API Integration

The assistant works completely independently. No hospital-specific API is
hardcoded. Integration uses the **Adapter Pattern**.

```
HospitalApiAdapter          (abstract port)
   ├── NullHospitalApiAdapter   (default — no-op)
   └── HttpHospitalApiAdapter   (stub, wired but empty)
```

When the hospital provides its API, only
`HttpHospitalApiAdapter.forward()` needs implementation. No other code
changes are required.

---

# Project Structure

```
hospital-voice-assistant/
├── backend/
│   ├── app/
│   │   ├── api/                (v1 endpoints)
│   │   ├── core/               (logging, startup)
│   │   ├── db/                 (async SQLAlchemy)
│   │   ├── models/             (ORM)
│   │   ├── repositories/       (data access)
│   │   ├── schemas/            (Pydantic DTOs)
│   │   ├── services/           (classifier, embeddings, FAISS, rule, LLM,
│   │   │                        LiveKit, hospital_api/)
│   │   ├── worker/             (LiveKit voice agent)
│   │   └── seed/               (catalog seed + loader)
│   ├── alembic/                (migrations)
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/app/
│   ├── Dockerfile
│   └── package.json
├── infrastructure/livekit/livekit.yaml
├── docker-compose.yml
├── .env.example
└── README.md
```

---

# Database

## `service_requests`
Stores every confirmed request: raw transcript, language, category,
service, confidence, timestamps.

## `unknown_requests`
Stores utterances that could not be mapped: transcript, language,
confidence, `top_candidate_code`, `review_status`.

## `service_catalog` (`hospital_services` + `service_categories`)
Category, service code, description, example utterances, keywords,
priority, required slots.

## `voice_sessions`
LiveKit room name + patient identity + language + timestamps.

---

# Docker Services

Docker Compose starts:

- Angular (`frontend`)
- FastAPI (`backend`)
- PostgreSQL 17 (`postgres`)
- Redis 7 (`redis`)
- LiveKit (`livekit`)
- LiveKit voice-agent worker (`voice-agent`)

One command:

```bash
docker compose up --build
```

---

# Performance Targets

| Stage                | Target       |
|----------------------|--------------|
| Greeting             | < 500 ms     |
| Speech Recognition   | < 400 ms     |
| Intent Classification| < 150 ms     |
| Cartesia TTS         | < 400 ms     |
| End-to-End           | < 2 seconds  |

---

# Security

- JWT authentication (LiveKit access tokens)
- Input validation (Pydantic v2)
- Output validation (Pydantic v2 + LLM `response_format=json_object`)
- SQL injection protection (SQLAlchemy async ORM)
- Prompt injection protection (LLM constrained to catalog codes only)
- Environment variables only for secrets
- Structured JSON logging with latency spans

---

# Health Endpoints

`GET /api/v1/healthz` – process liveness.

`GET /api/v1/readyz` – checks PostgreSQL, Redis, embedding model,
FAISS index. Returns `503` when any dependency is not ready.

---

# Development

Clone:

```bash
git clone <repository>
cd hospital-voice-assistant
```

Configure:

```bash
cp .env.example .env
# → edit .env and paste your Deepgram / Cartesia / Groq API keys
```

Run:

```bash
docker compose up --build
```

Seed services:

```bash
docker compose exec backend python -m app.seed.seed_services
```

Rebuild the semantic index:

```
POST /api/v1/services/rebuild-index
```

---

# AI Principles

- Never hallucinate services.
- Never invent categories.
- Always validate JSON.
- Always preserve the original transcript.
- Always use semantic search before LLM.
- LLM is fallback only.
- Hospital API is optional.
- Business logic remains independent of hospital integrations.

---

# License

MIT
