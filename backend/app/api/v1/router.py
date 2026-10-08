from fastapi import APIRouter
from app.api.v1.endpoints import adaptations, analysis, documents, health, test_ai

api_router = APIRouter()
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(test_ai.router, prefix="/ai", tags=["AI Integration"])
api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])
api_router.include_router(analysis.router, prefix="/analysis", tags=["Accessibility Analysis"])
api_router.include_router(adaptations.router, prefix="/adaptations", tags=["AI Adaptations"])
