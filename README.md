# Alex: AI Loan-Recovery Voice Agents (LiveKit)

Each user creates one AI Loan-Recovery Agent, chooses its name and voice, and has it call borrowers. The agent
speaks from the details and notes given for each call. Calls happen in the browser today. Real phone calls through
Twilio are built in and switch on once the Twilio trunk is set up. Every call gets a live transcript and a structured
post-call summary, and the Dashboard shows how the calls are going.

Voice pipeline on LiveKit Cloud: Deepgram speech-to-text → Gemini → Deepgram text-to-speech.

## Status
| Phase | State |
|---|---|
| 1 Foundation | Done, verified (compose stack, migrations, tests) |
| 2 Core voice + Web UI | Working end to end (browser call, live transcript, post-call summary, chat titles) |
| 3–6 | Started |

Each reply's latency is recorded per turn (`call_turns.metrics_json`), and the Dashboard shows today's average.
Speech-to-text takes about 0.4 s and the voice starts about 0.15–0.3 s after the text. Gemini's time to its first
word dominates: about 2–9 s, depending on its load. The target is under 800 ms. Decisions are recorded in `docs/adr/`.

## Requirements

### System tools
| Tool | Version used | Needed for |
|---|---|---|
| Git | any recent | cloning |
| [uv](https://docs.astral.sh/uv/) | 0.13+ | Python envs and lockfiles (it can fetch Python 3.12+ itself) |
| Python | 3.12 or newer (Docker images use 3.12; developed on 3.14) | backend and agent (`livekit-agents` requires >=3.12) |
| Node.js + npm | 22 LTS or newer | frontend |
| Docker + Docker Compose | 29.x | Postgres, Redis, and the full containerised stack |
| `psql` (optional) | 16+ | inspecting the database |
| `make` | any | shortcuts in the `Makefile` |

### Accounts and API keys (put them in `.env`, never commit it)
| Service | Variable(s) | Used for |
|---|---|---|
| [LiveKit Cloud](https://cloud.livekit.io) | `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | real-time audio rooms, agent dispatch, noise cancellation, phone calls (SIP) |
| [Google AI Studio (Gemini)](https://aistudio.google.com) | `GEMINI_API_KEY` | the agent's replies and the call summaries |
| [Deepgram](https://deepgram.com) | `DEEPGRAM_API_KEY` | speech-to-text and the agent's voices |
| [Twilio](https://www.twilio.com) (optional) | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` | real phone calls (needs an upgraded account; see [docs/phone-calls.md](docs/phone-calls.md)) |

Also set `INTERNAL_API_TOKEN`, `WORKSPACE_COOKIE_SECRET` and `AUTH_JWT_SECRET` (random strings of 16+ characters,
each different). Gemini model names change often: check which ones your key can use, then set `GEMINI_TEXT_MODEL`,
`AGENT_LLM_MODEL` and `GEMINI_FALLBACK_MODELS` in `.env`.

### Backend (`backend/`, Python)
`fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `pydantic-settings`, `httpx`, `aiohttp`,
`certifi`, `livekit-api`, `google-genai`, `jsonschema`, `argon2-cffi`, `pyjwt`, `email-validator`, `itsdangerous`,
`slowapi`, `prometheus-client`, `redis`.
Dev: `pytest`, `pytest-asyncio`, `aiosqlite`, `ruff`, `mypy`, `types-jsonschema`.

### Agent worker (`agent/`, Python)
`livekit-agents` 1.8.x with plugins `livekit-plugins-silero` (VAD), `livekit-plugins-google` (Gemini),
`livekit-plugins-deepgram` (STT and TTS), `livekit-plugins-turn-detector`, `livekit-plugins-noise-cancellation`,
plus `livekit-api`, `httpx`, `jsonschema`, `pydantic`, `pydantic-settings`.
Dev: `pytest`, `pytest-asyncio`, `ruff`, `mypy`.

### Frontend (`frontend/`, JavaScript)
Runtime: `react` 18, `react-dom`, `react-router-dom` 7, `@reduxjs/toolkit` 2, `react-redux`, `livekit-client` 2,
`three` and `@react-three/fiber` 8 (the call sphere), and the fonts `@fontsource-variable/geist`, `geist-mono` and
`open-sans`.
Dev: `vite`, `@vitejs/plugin-react`, `vitest`, `jsdom`, `@testing-library/*`, `eslint`, `@eslint/js`,
`eslint-plugin-react-hooks`, `globals`, `prettier`, `@playwright/test`.

### Ports used
| Port | What |
|---|---|
| 5173 | frontend dev server |
| 8000 | backend API |
| 5443 | dev Postgres (container port 5432) |
| 6390 | dev Redis (container port 6379; started by compose, not used by the code yet) |
| 8080 | frontend in the full Docker stack |

### Install the system tools

**Ubuntu / Debian Linux**
```bash
sudo apt update && sudo apt install -y git make curl postgresql-client

# uv (Python package/env manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Node.js 22 via nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.bashrc && nvm install 22

# Docker Engine + Compose plugin
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER      # then log out and back in
```

**macOS (Homebrew)**
```bash
brew install git make uv node@22 libpq
brew install --cask docker          # Docker Desktop; open it once so the daemon starts
```

**Windows**: use WSL2 and follow the Ubuntu steps inside it (`wsl --install -d Ubuntu`, then install Docker
Desktop with the WSL2 backend). Native alternative:
```powershell
winget install Git.Git astral-sh.uv OpenJS.NodeJS.LTS Docker.DockerDesktop
```
(`make` is not available natively on Windows; run the commands from the `Makefile` by hand or use WSL.)

Check everything is installed:
```bash
git --version && uv --version && node -v && npm -v && docker --version && docker compose version && make --version
```
You do not need to install Python yourself: `uv sync` downloads Python 3.12+ if it is missing.

### Install the project
```bash
git clone <your-repo-url> voice-agent-platform
cd voice-agent-platform

# 1. Python dependencies (creates backend/.venv and agent/.venv from the lockfiles)
(cd backend && uv sync)
(cd agent && uv sync)

# 2. One-time download of the voice model weights (VAD + turn detector)
(cd agent && uv run python -m voice_agent.worker download-files)

# 3. Frontend dependencies
(cd frontend && npm ci)

# 4. Configuration: copy the template, then fill in your keys (see "Accounts and API keys")
cp .env.example .env
sed -i "s|^INTERNAL_API_TOKEN=.*|INTERNAL_API_TOKEN=$(openssl rand -hex 24)|; s|^WORKSPACE_COOKIE_SECRET=.*|WORKSPACE_COOKIE_SECRET=$(openssl rand -hex 24)|; s|^AUTH_JWT_SECRET=.*|AUTH_JWT_SECRET=$(openssl rand -hex 32)|" .env
#   then edit .env: LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, GEMINI_API_KEY, DEEPGRAM_API_KEY
ln -sf ../.env backend/.env && ln -sf ../.env agent/.env   # lets each service find the shared .env

# 5. Start Postgres + Redis (Docker) and create the database tables
make infra
(cd backend && uv run alembic upgrade head)
```
On macOS use `sed -i ''` instead of `sed -i`. Now continue with **Run** below.

## Run
1. Complete **Install the project** above (dependencies, `.env` with your keys, Postgres/Redis, migrations).
2. Everything in containers: `make up` → UI on http://localhost:8080.
   (In local dev set `BACKEND_INTERNAL_URL=http://localhost:8000`; compose overrides it to `http://backend:8000`.)
3. Or local dev: `make dev` (Postgres/Redis + migrations), then in three terminals:
   - `cd backend && uv run uvicorn app.main:create_app --factory --reload`
   - `cd agent && uv run python -m voice_agent.worker dev`
   - `cd frontend && npm run dev` → http://localhost:5173

Give each copy of the project its own `AGENT_NAME` in `.env`. LiveKit shares calls between all workers that register
with the same name on one LiveKit project, so another copy's worker could otherwise take your calls.

## Test
`make test` (backend + agent), `cd frontend && npm test -- --run && npm run lint`, `make lint` (backend + agent).

## Web app

### Pages
There are **8 pages**: 2 public and 6 for signed-in users. Every signed-in page shares the left navbar. It has the
"Alex" logo; links to Dashboard, Your agent, Bulk calling, Profile and Settings; "Calls", marked *Soon* (no call
history page yet); and, at the bottom, a card with your agent's name and whether it is Free or In a call.

| Route | Page (`frontend/src/pages/`) | What it does |
|---|---|---|
| `/home` | `Landing.jsx` | Public landing page (sections in `frontend/src/components/landing/`) |
| `/checkin` | `CheckinPage.jsx` | Sign in or create an account: email and password, or Google when it is configured |
| `/dashboard/:uid` | `Dashboard.jsx` | Greeting and today's date, and a "Live · mm:ss · Return to call" pill during a call. Four figures for today: calls (vs yesterday), promise-to-pay rate, average reply time (against a 2 s target) and calls that need a person. A bar chart of calls over the last 7 days, today highlighted. The 5 most recent calls (time, masked phone, pending amount, outcome, mood, length). Next actions from today's call summaries, with tick-boxes saved on the server. A "Start a call" card. Search is marked *Soon* |
| `/agent/:uid` | `YourAgent.jsx` | Your single agent. Create it with a name and a voice (Male or Female); its tile shows Free or In-Call. The details show its system prompt and voice, with Rename and Delete. **Call Agent** opens the Individual Call pop-up (phone number, pending amount, call context; once phone calls are set up, also "Call their phone" or "Try it in the browser") or the Bulk Call pop-up (the CSV queue; once phone calls are set up, it starts the calls and shows each person's progress, with Pause, Resume and Cancel) |
| `/call/:uid` | `CallPage.jsx` | The call in progress, opened when a call starts (no navbar link). It has the shape-shifting sphere, the live transcript, and Mute / End call (in the browser). For a phone call you listen in, with Calling / Ringing / On the phone. When the call ends, the summary opens on the right, with the reason if a phone call did not connect, plus "Call again" |
| `/bulk-calling/:uid` | `BulkCalling.jsx` | Upload a CSV of people to call. Every row is checked and previewed, and a sample file and the file format are offered. The uploaded file is the queue used by Bulk Call |
| `/profile/:uid` | `ProfilePage.jsx` | Profile picture upload, username, email, number of agents, a weekly screen-time chart, and Log out |
| `/settings/:uid` | `Settings.jsx` | Dark or light theme, theme colour (presets or a custom colour), font size and font family |

Any other address goes to `/home`. A signed-in page with someone else's `:uid` goes to your own Dashboard.

### Your agent
**One agent per user.** Every agent is a Loan-Recovery Agent with the same system prompt
(`backend/app/services/collections_prompt.py::build_recovery_prompt`); only its name differs. Each call gets its own
copy of the prompt with that borrower's details and the call context typed by the user. The **voice** is chosen at
creation and used on every call: Male → `aura-2-draco-en`, Female → `aura-2-pandora-en` (both British English).
Deleting an agent marks it `DELETED` (its past calls stay linked), after which a new one can be created. A partial
unique index enforces at most one `ACTIVE` agent per user. The Manager and the simulated payment step were removed
(migration `0004`).

### Voice pipeline and summaries
By default (`AGENT_VOICE_MODE=pipeline`) the agent hears with Deepgram `nova-3`, thinks with Gemini
(`AGENT_LLM_MODEL`, default `gemini-3.5-flash-lite`), and speaks with Deepgram Aura-2, using semantic turn
detection. A Gemini Live speech-to-speech mode (`AGENT_VOICE_MODE=realtime`) also exists, but it is off: on this
project's long prompt it dropped greetings and misheard noise. After each call, Gemini writes a structured summary:
outcome, mood, whether a person is needed, whether the borrower promised to pay, and next actions. If the agent cannot
deliver it, the backend writes one from the saved transcript.

### Phone calls (Twilio)
Real phone calls go LiveKit → Twilio Elastic SIP trunk → the borrower's phone. The agent rings the number and
speaks only once the person answers. A call that does not connect is recorded as busy, no answer, declined,
invalid number or failed. Bulk calls phone the CSV's valid rows **one at a time**. The full number is kept only
until the call ends; only its last 4 digits are stored after that. All of this stays **switched off until
`SIP_OUTBOUND_TRUNK_ID` is set**. Set it up with `cd backend && uv run python -m app.scripts.setup_phone_calls --country IN`
(this needs an upgraded Twilio account and a voice number). See [docs/phone-calls.md](docs/phone-calls.md).

### Bulk Calling CSV
Header row required. Columns (case and punctuation ignored; common aliases such as "Mobile Number", "Due Date",
"Bank" are accepted): `name`, `phone` (with country code), `amount_due`, `deadline` are required; `lender`,
`currency` (default INR), `loan_reference`, `notes` are optional. Dates are ISO (`2026-12-05`) or day-first
(`05/12/2026`). Up to 1 MB / 1,000 rows. The page offers a sample file.

### API
All under `/api/v1`, with cookie auth and `X-CSRF-Token` on writes.

| Area | Endpoints |
|---|---|
| Auth | `GET /auth/config` (Google and phone calls available?), `POST /auth/register`, `POST /auth/login`, `GET /auth/me`, `POST /auth/logout`, `GET /auth/google/start`, `GET /auth/google/callback` |
| User | `GET /users/{uid}`, `PUT /users/{uid}/avatar`, `GET /users/{uid}/avatar`, `GET /users/{uid}/screen-time`, `POST /users/{uid}/screen-time/heartbeat` |
| Agent | `GET\|POST\|PUT\|DELETE /users/{uid}/agent` (create takes `name` and `voice`) |
| Calls | `POST /users/{uid}/collections/calls` (individual call, `mode`: `web` or `phone`), `GET /calls/{id}`, `POST /calls/{id}/end` |
| Bulk calls | `POST /users/{uid}/bulk-calls/preview` and `POST /users/{uid}/bulk-calls` (raw CSV body), `GET /users/{uid}/bulk-calls/current`, `POST /users/{uid}/bulk-calls/{job_id}/pause\|resume\|cancel` |
| Dashboard | `GET /users/{uid}/dashboard?tz=`, `PUT /users/{uid}/dashboard/next-actions/{call_id}/{index}`, `GET /users/{uid}/stats/calls-per-day?tz=` |

The agent worker uses `/internal/calls/...` (context, turns, events, summary), protected by `INTERNAL_API_TOKEN` and
never exposed through the public proxy.

Auth: email + password (argon2) and Google. The session is an httpOnly JWT cookie plus a CSRF cookie echoed in `X-CSRF-Token`.
Set `AUTH_JWT_SECRET` in `.env`. Google sign-in stays disabled until `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` are set; create a
Web OAuth client in Google Cloud Console and add `${APP_ORIGIN}/api/v1/auth/google/callback` as an authorised redirect URI.

Run order: `make infra`, `cd backend && uv run alembic upgrade head` (migrations `0001`–`0008`), then backend, agent and
frontend as above.

## Deployment
The app runs on [Railway](https://railway.com) as four services built from `infra/docker/`: `frontend` (nginx;
serves the app and forwards `/api` to the backend over Railway's private network), `backend` (runs the migrations
on start; keeps profile pictures on a volume), `agent` (the LiveKit worker), and Railway Postgres. Only the frontend
is public.

Deploy a service from the repository root with `railway up --service <frontend|backend|agent>`. The Railway project
is **not** connected to GitHub, so pushing does not deploy. Each service's settings live in Railway's variables. The
backend needs `ENV=prod`, `APP_ORIGIN`, `DATABASE_URL` (asyncpg form), `HOST=::`, `PORT=8000` and
`FORWARDED_ALLOW_IPS=*`. The frontend needs `BACKEND_UPSTREAM`. On a 1 GB plan, set `AGENT_IDLE_PROCESSES=0` on the
agent so that only one call process exists at a time.
