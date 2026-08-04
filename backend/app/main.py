from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .ai import ai_service
from .models import AIRequest, AIResponse, ScenarioConfig, SimulationCommand
from .simulation import RetailTwinSimulation


simulation = RetailTwinSimulation()


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    simulation.stop()


app = FastAPI(title="Retail Twin API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "retail-twin", "simulation": simulation.running}


@app.get("/api/ai/status")
async def ai_status():
    return ai_service.status()


@app.post("/api/ai/generate", response_model=AIResponse)
async def ai_generate(request: AIRequest):
    result = await ai_service.generate(request.prompt, request.provider, request.model)
    return result.__dict__


@app.get("/api/scenario")
async def get_scenario():
    return simulation.config.model_dump()


@app.post("/api/scenario")
async def configure_scenario(config: ScenarioConfig):
    simulation.configure(config)
    return simulation.snapshot()


@app.get("/api/snapshot")
async def get_snapshot():
    return simulation.snapshot()


@app.post("/api/simulation/start")
async def start_simulation(command: SimulationCommand = SimulationCommand()):
    simulation.start(command.speed)
    return simulation.snapshot()


@app.post("/api/simulation/stop")
async def stop_simulation():
    simulation.stop()
    return simulation.snapshot()


@app.post("/api/simulation/reset")
async def reset_simulation():
    simulation.reset()
    return simulation.snapshot()


@app.post("/api/simulation/speed")
async def change_speed(command: SimulationCommand):
    simulation.set_speed(command.speed)
    return simulation.snapshot()


@app.websocket("/ws/simulation")
async def simulation_stream(websocket: WebSocket):
    await websocket.accept()
    try:
        await websocket.send_json(simulation.snapshot())
        while True:
            if simulation.running:
                simulation.step(1)
            await websocket.send_json(simulation.snapshot())
            await asyncio.sleep(0.95 if simulation.speed == 1 else 0.28 if simulation.speed == 10 else 0.08)
    except WebSocketDisconnect:
        return
