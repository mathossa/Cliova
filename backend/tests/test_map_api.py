from collections.abc import AsyncIterator
from uuid import UUID

import httpx2
import pytest

from cliova.api.dependencies import get_repository
from cliova.infrastructure.persistence.postgres import WorldNotFoundError
from cliova.main import create_app
from cliova.simulation.domains.world.fixtures import create_starter_world
from cliova.simulation.types import WorldState


class MapReadRepository:
    def __init__(self, world: WorldState) -> None:
        self.world = world

    def load_world(self, world_id: UUID) -> WorldState:
        if self.world.id.value != world_id:
            raise WorldNotFoundError("missing world")
        return self.world


async def _client(world: WorldState) -> AsyncIterator[httpx2.AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: MapReadRepository(world)
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.anyio
async def test_generated_world_map_and_base_svg_are_exposed_without_domain_internals() -> None:
    world = WorldState.create(seed=77, world_key="map-api")
    async for client in _client(world):
        response = await client.get(f"/api/v1/worlds/{world.id.value}/map")
        base = await client.get(f"/api/v1/worlds/{world.id.value}/map/base.svg")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert len(payload["regions"]) == len(world.geography.regions)  # type: ignore[union-attr]
    assert payload["base_map_url"].endswith("strategic-svg-v1")
    assert "generation" not in payload
    assert "presentation" not in payload
    assert "runs" not in payload["regions"][0]

    assert base.status_code == 200
    assert base.headers["content-type"].startswith("image/svg+xml")
    assert base.headers["x-cliova-map-render-version"] == "strategic-svg-v1"
    assert base.headers["etag"]
    assert 'data-render-version="strategic-svg-v1"' in base.text


@pytest.mark.anyio
async def test_legacy_world_reports_map_unavailable_without_fake_geography() -> None:
    world = create_starter_world(seed=7, world_key="legacy-map-api")
    async for client in _client(world):
        response = await client.get(f"/api/v1/worlds/{world.id.value}/map")
        base = await client.get(f"/api/v1/worlds/{world.id.value}/map/base.svg")

    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["regions"] == []
    assert base.status_code == 404
    assert base.json()["error"]["code"] == "map_unavailable"
