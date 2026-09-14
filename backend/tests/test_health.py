import httpx2
import pytest

from cliova.main import app


@pytest.mark.anyio
async def test_health_without_database() -> None:
    transport = httpx2.ASGITransport(app=app)

    async with httpx2.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "cliova"}
