# Retail Twin MVP

A full-stack location intelligence prototype for retail expansion decisions. Configure a concept, test storefronts in SoHo, and watch a deterministic 30-day neighborhood simulation reveal the difference between foot traffic and purchase intent.

## Stack

- **Frontend:** React, TypeScript, Vite, Lucide icons, CSS design system
- **Backend:** Python 3.9+, FastAPI, Pydantic, WebSockets
- **Simulation:** seeded deterministic consumer cohort engine; 10,000 synthetic consumers represented by a performant visual sample

## Run locally

### 1. Start the API

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 2. Start the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

The Vite dev server proxies `/api` and `/ws` to FastAPI. The backend has interactive OpenAPI docs at <http://localhost:8000/docs>.

## MVP behavior

- Setup wizard validates a retail concept, operating strategy, test locations, and marketing channels.
- FastAPI validates scenarios with Pydantic and returns a deterministic simulation snapshot.
- WebSocket `/ws/simulation` streams movement, KPIs, consumer posts, and competitor events.
- The dashboard supports 1×, 10×, and 100× speed controls, pause/start/reset, location selection, and visual layers.
- Executive report turns the simulated results into a location recommendation.

## Optional AI provider integration

The backend now supports all five providers through a single server-side adapter:

- Groq — OpenAI-compatible chat completions
- OpenRouter — OpenAI-compatible chat completions
- NVIDIA NIM — OpenAI-compatible chat completions
- Gemini — `generateContent`
- Cohere — v2 chat

Copy `backend/.env.example` to `backend/.env` and fill in credentials locally. **Never put provider keys in React/Vite environment variables, source files, screenshots, commits, or a public GitHub repository.** The adapter supports the provider names from the request as migration aliases, but server-side variables such as `GROQ_API_KEY` are preferred.

The frontend shows whether the simulation is deterministic or AI-enabled through `/api/ai/status`. `/api/ai/generate` uses the configured provider automatically and falls back to deterministic insight when no key is configured or a provider request fails. A provider outage therefore cannot stop the simulation.

## Deployment

The React frontend is Vercel-ready: build with `npm run build` from `frontend`, and the included `vite.config.ts` handles local API proxying. The FastAPI service should be deployed separately to a WebSocket-capable host such as Railway, Render, Fly.io, or Cloud Run. Standard Vercel Serverless Functions are not a suitable host for the current long-lived simulation WebSocket.

For production frontend hosting, set the API origin and replace the local proxy/WebSocket URL construction in `frontend/src/api.ts` with your deployed backend URL. Keep AI keys only in the backend host’s secret manager.

## Security note

The credentials pasted into chat should be considered exposed. Rotate/revoke all five keys in their provider consoles before using them in production. This repository intentionally contains placeholders only.
