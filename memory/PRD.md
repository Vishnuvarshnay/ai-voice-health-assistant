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

## Delivered updates (session 3, 2026-02-01)
- **Hospital API adapter pattern** — no hardcoded URLs, no invented contract.
  - `app/services/hospital_api/base.py` → `HospitalApiAdapter` ABC (single `forward(payload)` port)
  - `null_adapter.py` → default: logs and returns (used when `HOSPITAL_API_URL` empty)
  - `http_adapter.py` → **stub** with call-site wired; `forward()` intentionally empty until the hospital API contract is defined
  - `__init__.py::get_adapter()` picks the right adapter from env
  - `voice_agent.py` and `POST /api/v1/requests` call the adapter, never a concrete client
- **Semantic-primary classifier** — keywords demoted from co-equal to optional boost.
  - Semantic (BGE-M3 + FAISS) is now weight 1.0 and IS the base confidence
  - Rule engine still extracts slots (room, time, qty) and provides at most a `+0.10` keyword boost
  - Boosted score capped at 0.99 so the system never claims perfect certainty
- **Tests** — 6/6 pass, including new `test_intent_scoring.py` and `test_hospital_api_adapter.py`
- **Docs** — README pipeline diagram + adapter section rewritten; `.env.example` documents the plug-in flow

## Standalone guarantee
The app is fully functional today with `HOSPITAL_API_URL` empty:
- LiveKit voice session runs
- BGE-M3 + FAISS classify intent semantically
- Validated JSON is persisted to Postgres (`service_requests` table)
- JSON is returned to the frontend and spoken back via Cartesia
- `NullHospitalApiAdapter` logs the skip; nothing else happens

When the hospital API becomes available, only two things change:
1. `.env` gets `HOSPITAL_API_URL` (+ optional `HOSPITAL_API_KEY`)
2. `HttpHospitalApiAdapter.forward()` gets its body filled in per the real contract
No changes to business logic.

## Delivered updates (session 5, 2026-02-01)
- **Classifier rewritten as `HybridIntentClassifier` class** (`app/services/intent_classifier.py`).
  - Explicit `FaissPort`, `RuleEnginePort`, `LlmFallbackPort` protocols → trivially unit-testable with fakes; production still uses the real singletons via default DI.
  - Pipeline stages are private methods (`_semantic_search`, `_score_candidates`, `_try_llm_fallback`, `_validate_in_catalog`, `_matched`, `_unknown`).
  - **Anti-hallucination gates** at every boundary:
    1. FAISS hit → re-fetched via `ServiceRepo.get_by_id` (deleted services silently dropped)
    2. LLM answer → must be in the top-K allow-list AND resolvable via `ServiceRepo.get_by_code`
    3. LLM confidence must ≥ semantic hybrid confidence to override
  - Semantic-primary scoring: `min(semantic + boost, 0.99)` with boost ≤ 0.10
  - Groq LLM triggered ONLY when confidence < `CONFIDENCE_THRESHOLD` (0.85)
  - Hard floor `MIN_SEMANTIC_THRESHOLD` (0.35) → returns `UNKNOWN_SERVICE` before the LLM is even consulted
- **6 new behaviour tests** (`tests/test_intent_classifier.py`) with mocked ports asserting:
  * High-confidence semantic path never calls LLM
  * Below-min-threshold path never calls LLM
  * LLM-invented codes outside top-K are rejected → UNKNOWN
  * LLM null/refusal → UNKNOWN
  * LLM promotion of borderline semantic candidates works
  * Deleted-service FAISS hits are ignored gracefully
- Backward-compat module-level `classify()` facade unchanged so all existing callers (`voice_agent`, REST endpoints) work without edits.

**Test suite: 12/12 pass** · ruff clean

## Delivered updates (session 4, 2026-02-01)
- **Deepgram model** bumped to `nova-3` (was `nova-2-general`)
- **No blocking translation** — BGE-M3 handles multilingual directly. FAISS runs on the ORIGINAL transcript. Translation is now controlled by `TRANSLATE_FOR_AUDIT=false` (default off) and only used to enrich audit fields, never blocks the pipeline.
- **UNKNOWN_SERVICE status** — new response field `status: "MATCHED" | "UNKNOWN_SERVICE"` on `/api/v1/intent/classify` and in the voice worker path. Reject conditions: top semantic < `MIN_SEMANTIC_THRESHOLD=0.35`, or LLM refuses to pick a catalog code.
- **New table `unknown_requests`** with `raw_transcript`, `detected_language`, `top_semantic_score`, `top_candidate_code`, `review_status`. Alembic migration updated.
- **Admin endpoints** — `GET /api/v1/unknown-requests?status=pending` and `PATCH /api/v1/unknown-requests/{id}` to update review status.
- **Health endpoints renamed** — `/api/v1/healthz` (liveness) and `/api/v1/readyz` (checks Postgres, Redis, embedding model, FAISS index; returns 503 when not ready).
- **Voice worker** persists unknown utterances into `unknown_requests` and replies with a graceful "noted for review" message.
- **DTO** — added `status` and `raw_transcript` to `IntentClassifyOut`. Frontend `IntentResult` type updated in sync.
- **README** replaced with the user-provided spec.

## Standalone guarantee (unchanged)
Every validated JSON is still persisted to Postgres and returned to the frontend.
Hospital API remains an adapter port. No hardcoded URLs.

## Delivered in this session (2026-02-01)
### Root
- `docker-compose.yml` (postgres, redis, livekit, backend, voice-agent, frontend)
- `.env.example` with all keys as placeholders (+ optional `HOSPITAL_API_URL`)
- `README.md` with quickstart, seed instructions, hospital-API forwarder docs
- `infrastructure/livekit/livekit.yaml` (self-hosted config)

### Backend (`/backend`)
- Full clean-architecture layout (config, db, models, schemas, repositories, services, api, core, worker, seed)
- Hybrid intent classifier: BGE-M3 embeddings → FAISS cosine → rule engine (keyword + slot) → Groq `llama-3.3-70b-versatile` fallback below 0.85
- LiveKit `AgentSession` worker: Deepgram STT (`multi`) + Cartesia (`sonic-2`) TTS + Silero VAD, greets in <500 ms, persists every request
- Optional webhook `hospital_api.forward` — POSTs the confirmed JSON to `HOSPITAL_API_URL` (user's hospital management API) with retry/backoff
- REST surface: `/api/v1/{health,ready,services,intent/classify,voice/token,requests}` + `POST /services/rebuild-index`
- Alembic initial migration
- Real catalog seeded (44 services, 9 categories exactly as user provided)
- `tests/test_rule_engine.py` (passes)

### Frontend (`/frontend`) — Angular 17 standalone
- LiveKit-client 2.5.7, dark themed panel: join room, live transcript, direct intent-test panel with pretty JSON

## Delivered updates (session 2, 2026-02-01)
- **Real service catalog**: replaced defaults with the 44 services provided by the user (Cleaning 4 · AC 4 · TV 4 · Laundry 4 · Electrical 4 · Maintenance 6 · Patient Support 4 · Patient Diet 7 · Service Complaint 7)
- **Hospital API webhook**: `HOSPITAL_API_URL` + `HOSPITAL_API_KEY` in `.env` → every confirmed request forwarded as JSON with tenacity retry
- README documents the forwarder + payload shape

## Validation
- `python -m pytest tests/ -v` → 2/2 passing
- `ruff` → zero errors
- `tsc --noEmit` (strict) → clean
- 39 backend Python files parse OK; 44 seed services, all codes unique

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
