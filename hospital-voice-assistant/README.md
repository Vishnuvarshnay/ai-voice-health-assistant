# Hospital AI Voice Assistant

Production-ready voice microservice for hospital service requests.
Patient speaks → LiveKit transport → Deepgram Streaming STT → Hybrid Intent
Classifier (BGE-M3 + FAISS + Rule Engine) → validated JSON service request →
Cartesia Streaming TTS confirmation.

- **Greeting SLA**: < 500 ms after room join
- **Multilingual input** (auto language detection), **English** normalized JSON output
- **LLM fallback** (Groq `llama-3.3-70b-versatile`) when hybrid confidence < 0.85
- **Stack**: Angular 17 · FastAPI (async) · PostgreSQL 17 · Redis 7 · LiveKit · Docker Compose

---

## 1. Prerequisites
- Docker Desktop / Docker Engine 24+ with Docker Compose v2
- 8 GB RAM minimum (BGE-M3 embedding model is ~2.3 GB)
- API keys:
  - [Deepgram](https://console.deepgram.com/) — Streaming STT
  - [Cartesia](https://play.cartesia.ai/) — Streaming TTS
  - [Groq](https://console.groq.com/) — LLM fallback
  - LiveKit self-hosted (already bundled in docker-compose)

## 2. Quick start

```bash
git clone <this-repo>
cd hospital-voice-assistant
cp .env.example .env
# → edit .env and paste your Deepgram / Cartesia / Groq API keys

docker compose up --build
```

On first boot the backend downloads the **BGE-M3** embedding model (~2 GB).
Subsequent boots reuse the cached model volume.

Once up:
- Frontend UI: http://localhost:4200
- Backend API docs: http://localhost:8000/docs
- LiveKit server: ws://localhost:7880
- Postgres: `localhost:5432` (user/pass from `.env`)
- Redis: `localhost:6379`

## 3. First run – seed the service catalog

The catalog ships with **44 real hospital services across 9 categories**
(Cleaning, AC, TV, Laundry, Electrical, Maintenance, Patient Support,
Patient Diet, Service Complaint) in `backend/app/seed/default_services.json`.

Load it into Postgres and build the FAISS index:

```bash
docker compose exec backend python -m app.seed.seed_services
```

To customize, edit `backend/app/seed/default_services.json` (each row has
`code`, `name`, `description`, `example_utterances`, `keywords`,
`required_slots`, `priority`) and re-run the seeder — or POST to
`/api/v1/services` and then `POST /api/v1/services/rebuild-index`.

### Forward to your own hospital API (adapter pattern, plug-in later)

The core voice assistant works **standalone**. Every validated JSON is
persisted to Postgres and returned to the frontend regardless of any
external system.

When the hospital's own API is ready, plug it in via the adapter interface —
**no change to the business logic is required**.

The contract lives in
`backend/app/services/hospital_api/base.py`:

```python
class HospitalApiAdapter(ABC):
    async def forward(self, payload: dict) -> None: ...
```

Two adapters ship out of the box:

| Adapter | When it's used | What it does |
|---|---|---|
| `NullHospitalApiAdapter` | `HOSPITAL_API_URL` is empty (default) | Logs and returns |
| `HttpHospitalApiAdapter` | `HOSPITAL_API_URL` is set | **Stub** — call site is wired, but `forward()` is intentionally empty because the hospital API contract is not yet defined. Fill it in when the contract is available. |

To activate later:
1. Set `HOSPITAL_API_URL` (+ optional `HOSPITAL_API_KEY`) in `.env`.
2. Implement `HttpHospitalApiAdapter.forward()` in
   `backend/app/services/hospital_api/http_adapter.py` per your API's
   contract (or add a new adapter class and register it in
   `hospital_api/__init__.py::get_adapter`).
3. Restart the `backend` and `voice-agent` containers. Done.

The core app (`intent_classifier`, `voice_agent`, REST endpoints) does not
change. No hospital-specific URLs, paths, methods, or payload assumptions
exist anywhere in the core code.

## 4. Try it

1. Open http://localhost:4200
2. Click **Join Room** — LiveKit will connect and you should hear the
   English greeting within 500 ms.
3. Speak a request in any language (e.g. Spanish, Hindi, Mandarin).
4. The right panel shows the normalized English service-request JSON.

## 5. Project layout

```
hospital-voice-assistant/
├── docker-compose.yml
├── .env.example
├── README.md
├── backend/                        # FastAPI + async SQLAlchemy + LiveKit worker
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic/                    # DB migrations
│   └── app/
│       ├── main.py                 # FastAPI entrypoint + startup lifecycle
│       ├── config.py               # Settings (env-driven)
│       ├── api/v1/                 # REST endpoints
│       ├── core/                   # logging, startup, dependencies
│       ├── db/                     # async SQLAlchemy session + base
│       ├── models/                 # ORM tables
│       ├── schemas/                # Pydantic DTOs
│       ├── repositories/           # data-access layer
│       ├── services/               # intent classifier, STT, TTS, LLM
│       ├── worker/                 # LiveKit voice agent process
│       └── seed/                   # service-catalog seed data + loader
├── frontend/                       # Angular 17 SPA + LiveKit client SDK
│   ├── Dockerfile
│   ├── package.json
│   └── src/app/
└── infrastructure/
    └── livekit/livekit.yaml        # Self-hosted LiveKit config
```

## 6. Intent classification pipeline (semantic-primary)

Semantic similarity is the **base confidence signal**. Keywords are a small
tie-breaker / boost only — they cannot single-handedly pick a service, and
they cannot beat a semantically stronger candidate.

```
speech ─► Deepgram STT (multi) ─► transcript
                                     │
                                     ▼
                       (if non-English) Groq translate → English
                                     │
                                     ▼
                              BGE-M3 embedding
                                     │
                                     ▼
                          FAISS top-K nearest services      ← primary signal
                                     │
                                     ▼
                   Rule engine  → extract slots (room, time, qty)
                                → optional +0.10 keyword boost
                                     │
                                     ▼
                     confidence = min(semantic + boost, 0.99)
                                     │
                        ┌────────────┴────────────┐
                     ≥ 0.85                     < 0.85
                        │                         │
                        ▼                         ▼
              Return JSON directly       Groq LLM fallback
                                        (structured output;
                                         chooses ONLY from catalog)
                                                  │
                                                  ▼
                                       Return validated JSON
                                                  │
                                                  ▼
                              Persist to Postgres · reply via Cartesia TTS ·
                              hand off to `HospitalApiAdapter` (no-op by default)
```

The service catalog lives in Postgres. Bootstrap from
`backend/app/seed/default_services.json` or manage via
`POST /api/v1/services` — either way the classifier reads from the DB and
the FAISS index is rebuilt on demand via `POST /api/v1/services/rebuild-index`.

## 7. API surface (selected)

| Method | Path | Purpose |
|--------|------|---------|
| GET  | `/api/v1/health`                | Liveness / readiness |
| GET  | `/api/v1/services`              | List service catalog |
| POST | `/api/v1/services`              | Create a service |
| POST | `/api/v1/services/rebuild-index`| Rebuild FAISS index |
| POST | `/api/v1/intent/classify`       | Classify a text utterance |
| POST | `/api/v1/voice/token`           | Mint LiveKit access token |
| POST | `/api/v1/requests`              | Persist a confirmed service request |

## 8. Development commands

```bash
# tail backend logs
docker compose logs -f backend

# apply a new migration
docker compose exec backend alembic upgrade head

# run backend tests
docker compose exec backend pytest -q

# rebuild the FAISS index after editing the catalog
curl -X POST http://localhost:8000/api/v1/services/rebuild-index
```

## 9. Stopping

```bash
docker compose down          # keep data
docker compose down -v       # wipe volumes (postgres, redis, model cache)
```

## 10. Notes on portability

Everything runs from Docker Compose. No external dependency other than the
API keys in `.env`. You can copy this directory to any machine with Docker
installed and it will work identically.
