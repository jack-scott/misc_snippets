from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import syncthing, tunnels, devices, provision, folders, sync
from backend.services import ssh as ssh_svc
from backend.services.st_client import close_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    ssh_svc.cleanup_all()
    await close_client()


app = FastAPI(title="Fleet Sync Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(syncthing.router)
app.include_router(tunnels.router)
app.include_router(devices.router)
app.include_router(provision.router)
app.include_router(folders.router)
app.include_router(sync.router)


@app.get("/health")
async def health():
    return {"ok": True}
