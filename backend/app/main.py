from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from afu_shared.settings import settings
from app.api.router import api_router

app = FastAPI(title="AFU RTM Helpdesk API")

origins = [o.strip() for o in settings.backend_cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(
    "/media/employees",
    StaticFiles(directory=f"{settings.storage_root}/employees", check_dir=False),
    name="employee-media",
)

app.include_router(api_router, prefix="/api")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
