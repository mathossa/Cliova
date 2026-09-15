from fastapi import APIRouter

from cliova.api.v1.router import router as v1_router

router = APIRouter()
router.include_router(v1_router)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "cliova"}
