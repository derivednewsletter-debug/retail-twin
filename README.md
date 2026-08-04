# Retail Twin MVP

A full-stack location intelligence prototype for retail expansion decisions. Configure a concept, test storefronts in SoHo, and watch a deterministic 30-day neighborhood simulation reveal the difference between foot traffic and purchase intent.

## Stack

- **Frontend:** React, TypeScript, Vite, Lucide icons, CSS design system
- **Backend:** Python 3.13+, FastAPI, Pydantic (runs as Vercel serverless functions)
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

Open http://localhost:5173.

The Vite dev server proxies /api and /ws to FastAPI. The backend has interactive OpenAPI docs at http://localhost:8000/docs.

## MVP behavior

- Setup wizard validates a retail concept, operating strategy, test locations, and marketing channels.
- FastAPI validates scenarios with Pydantic and returns a deterministic simulation snapshot.
- The dashboard supports 1x, 10x, and 100x speed controls, pause/start/reset, location selection, and visual layers.
- Executive report turns the simulated results into a location recommendation.

## Optional AI provider integration

The backend supports all five providers through a single server-side adapter:

- Groq -- OpenAI-compatible chat completions
- OpenRouter -- OpenAI-compatible chat completions
- NVIDIA NIM -- OpenAI-compatible chat completions
- Gemini -- generateContent
- Cohere -- v2 chat

The frontend shows whether the simulation is deterministic or AI-enabled through /api/ai/status. /api/ai/generate uses the configured provider automatically and falls back to deterministic insight when no key is configured or a provider request fails.

## Vercel deployment

Everything runs on Vercel. The frontend is a React SPA served as static files. The backend is a Python FastAPI serverless function in `api/main.py`.

### Setup

1. Push this repository to GitHub
2. Import the project in Vercel (https://vercel.com/new)
3. Vercel will auto-detect the configuration from `vercel.json`
4. Add these environment variables in Vercel:

```
EXPO_PUBLIC_GROQ_API_KEY=gsk_...
EXPO_PUBLIC_OPENROUTER_API_KEY=sk-or-...
EXPO_PUBLIC_GEMINI_API_KEY=AQ...
EXPO_PUBLIC_NVIDIA_NIM_API_KEY=nvapi-...
EXPO_PUBLIC_COHERE_API_KEY=cohere_...
```

5. Deploy

### Environment variables

All API keys live in Vercel environment variables. The `EXPO_PUBLIC_*` prefix ensures they are available to the serverless Python functions. The backend reads both `EXPO_PUBLIC_GROQ_API_KEY` and `GROQ_API_KEY` forms, so either naming convention works.

### How it works

- `vercel.json` configures the build and routing
- `api/main.py` is a Python serverless function that handles all /api/* routes
- `frontend/` is built as a React SPA and served as static files
- The simulation uses HTTP polling (GET /api/snapshot) instead of WebSocket, since Vercel serverless functions do not support long-lived connections

### Local development

For local development, the `backend/` directory contains a standalone FastAPI app with WebSocket support. The `api/` directory is the Vercel-optimized version.

```bash
# Backend (local)
cd backend && uvicorn app.main:app --reload --port 8000

# Frontend (local)
cd frontend && npm run dev
```

The frontend `api.ts` uses `VITE_API_BASE_URL` to set the API origin. For local development, leave it empty and use the Vite proxy. For Vercel production, set it to your Vercel deployment URL.

## Security note

Never commit API keys to git. Use Vercel environment variables for all provider credentials.
