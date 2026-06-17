from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.health import router as health_router
from app.api.v1.org import router as org_router
from app.api.v1.workspace import router as workspace_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(org_router)
api_router.include_router(chat_router)
api_router.include_router(workspace_router)
