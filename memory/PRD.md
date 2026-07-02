# Hospital AI Voice Assistant — PRD

## Original Problem Statement
Build a production-ready AI Health Voice Assistant as an independent microservice
for hospital service requests. The app must establish a LiveKit voice session,
greet the patient in <500 ms, run Deepgram Streaming STT, automatically detect
language, and use a Hybrid Intent Classifier (BGE-M3 Embeddings + FAISS Vector
Search + Rule Engine) to map requests to predefined services without
hallucinating. It generates validated JSON and replies via Cartesia Streaming
TTS. If confidence < 0.85, it uses an LLM fallback.

**User constraint**: Fully portable — the user downloads the folder and runs it
locally via `docker compose up`.

## Confirmed choices
| Concern | Decision |
|---|---|
| Frontend | **Angular 17** (standalone components) |
| Backend | Python **FastAPI** (async) |
| Database | **PostgreSQL 17** (docker) |
| Cache | **Redis 7** (docker) |
| Voice transport | **LiveKit** (self-hosted in docker) |
| STT | **Deepgram** (multilingual, `nova-2-general`) |
| TTS | **Cartesia** (`sonic-2`) |
| LLM fallback | **Groq** `llama-3.3-70b-versatile` |
| Language | Auto-detect input · normalize JSON to **English** |
| API keys | Placeholders in `.env.example`, user supplies at run-time |
| Hospital services | Reasonable defaults seeded; user will provide custom list later |

## Architecture (all containerized)
```
angular (4200)  ─►  fastapi (8000)  ─►  postgres (5432)
                          │              redis    (6379)
                          │
                    livekit-agent worker  ─►  livekit (7880)
                              ├── Deepgram (STT)
                              ├── Cartesia (TTS)
                              ├── BGE-M3 + FAISS  (in-process)
                              └── Groq LLM fallback
```

## Delivered in this session (2026-02-01)
### Root
- `docker-compose.yml` (postgres, redis, livekit, backend, voice-agent, frontend)
- `.env.example` with all keys as placeholders
- `README.md` with quickstart, seed instructions, API surface, layout
- `infrastructure/livekit/livekit.yaml` (self-hosted config)

### Backend (`/backend`)
- `Dockerfile`, `requirements.txt`
- `app/config.py` — pydantic-settings, env-driven
- `app/db/session.py` — async SQLAlchemy engine + `Base`
- `app/models/orm.py` — `ServiceCategory`, `HospitalService`, `VoiceSession`, `ServiceRequest`
- `app/schemas/dto.py` — Pydantic v2 DTOs
- `app/repositories/service_repo.py`, `request_repo.py`
- `app/services/embedding_service.py` — BGE-M3 async wrapper
- `app/services/faiss_index.py` — cosine-IP FAISS index over utterances
- `app/services/rule_engine.py` — keyword scoring + slot extraction (room/time/qty)
- `app/services/llm_fallback.py` — Groq JSON mode + translation helper
- `app/services/intent_classifier.py` — hybrid scoring (0.6·semantic + 0.4·rule) + LLM fallback under 0.85
- `app/services/livekit_service.py` — token mint
- `app/api/v1/` — `/health`, `/ready`, `/services`, `/services/rebuild-index`, `/intent/classify`, `/voice/token`, `/requests`
- `app/core/logging.py` — structlog JSON + latency context manager
- `app/core/startup.py` — loads BGE-M3 + FAISS on FastAPI startup
- `app/main.py` — FastAPI + lifespan
- `app/worker/voice_agent.py` — LiveKit `AgentSession` with Deepgram STT, Cartesia TTS, Silero VAD; classifies each final transcript and speaks confirmation; greets in <500 ms
- `app/seed/default_services.json` — 11 default hospital services across 6 categories
- `app/seed/seed_services.py` — CLI that seeds DB and rebuilds FAISS
- `alembic/` — initial migration `0001_initial`
- `tests/test_rule_engine.py` — passes (`2 passed`)

### Frontend (`/frontend`) — Angular 17 standalone
- `Dockerfile`, `package.json` (livekit-client 2.5.7)
- `angular.json`, `tsconfig*.json`
- `src/app/services/api.service.ts` — token mint + intent classification
- `src/app/services/livekit.service.ts` — Room lifecycle + mic publish + attached remote audio
- `src/app/app.component.{ts,html,css}` — dark themed panel: join room, live transcript, direct intent test, JSON output

## Validation
- `python -m pytest tests/ -v` → 2/2 passing
- `ruff` (via lint agent) → zero errors
- `tsc --noEmit` (strict) → clean
- All 38 backend Python files parse OK

## Known caveats (all safe to defer)
- BGE-M3 model download (~2 GB) happens on first backend container boot;
  cached via `model_cache` volume.
- LiveKit config in `livekit.yaml` uses a dev key/secret (`devkey`); user should
  rotate before production.
- Voice-agent worker relies on `livekit-agents 1.6.4`; if the API surface
  changes upstream, `voice_agent.py` may need adjustment.

## Roadmap / P1 backlog
- Alembic autogenerate script for future schema changes
- WebSocket data-channel push of live JSON to frontend during voice sessions
  (currently only via REST test-classify)
- Session history endpoint on `/api/v1/requests?session_id=...`
- Prometheus `/metrics` endpoint alongside structlog logs
- CI workflow (GitHub Actions) running `pytest` + `ng build`

## P2 backlog
- Role-based auth for API endpoints
- Hospital service admin UI (Angular) for CRUD on catalog
- Multi-tenant DB schema for multiple hospitals
- Analytics dashboard: latency, fallback rate, top requests

## Deployment
Not deployed to Emergent preview — this is a **standalone, portable** project
built to be downloaded and run via Docker Compose on the user's own machine.
