from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx2
import pytest

from cliova.api.dependencies import get_repository
from cliova.application.persistence import QueuedSimulationInput, TickResolver
from cliova.application.scheduling import TickRunClaim, TickRunTrigger
from cliova.infrastructure.persistence.postgres import TickConflictError, WorldNotFoundError
from cliova.infrastructure.persistence.worlds import WorldAlreadyExistsError
from cliova.main import create_app
from cliova.simulation.history import EventHistory
from cliova.simulation.types import SimulationInput, TickResult, WorldState


class InMemoryWorldRepository:
    def __init__(self) -> None:
        self.worlds: dict[UUID, WorldState] = {}
        self.snapshots: dict[tuple[UUID, int], WorldState] = {}
        self.pending: dict[UUID, list[QueuedSimulationInput]] = {}
        self.histories: dict[UUID, EventHistory] = {}
        self.next_queue_id = 1

    def create_world(self, world: WorldState) -> None:
        world_id = world.id.value
        if world_id in self.worlds:
            raise WorldAlreadyExistsError("duplicate world")
        self.worlds[world_id] = world
        self.snapshots[(world_id, world.time.tick)] = world
        self.pending[world_id] = []
        self.histories[world_id] = EventHistory()

    def list_worlds(self) -> tuple[WorldState, ...]:
        return tuple(self.worlds[key] for key in sorted(self.worlds, key=lambda value: value.hex))

    def load_world(self, world_id: UUID) -> WorldState:
        try:
            return self.worlds[world_id]
        except KeyError as exc:
            raise WorldNotFoundError("missing world") from exc

    def load_snapshot(self, world_id: UUID, tick: int) -> WorldState:
        try:
            return self.snapshots[(world_id, tick)]
        except KeyError as exc:
            raise WorldNotFoundError("missing snapshot") from exc

    def queue_input(self, world_id: UUID, value: SimulationInput) -> QueuedSimulationInput:
        world = self.load_world(world_id)
        queued = QueuedSimulationInput(
            queue_id=self.next_queue_id,
            submitted_tick=world.time.tick + 1,
            value=value,
        )
        self.next_queue_id += 1
        self.pending[world_id].append(queued)
        return queued

    def load_pending_inputs(self, world_id: UUID) -> tuple[QueuedSimulationInput, ...]:
        self.load_world(world_id)
        return tuple(self.pending[world_id])

    def execute_tick(
        self,
        world_id: UUID,
        *,
        expected_tick: int,
        resolver: TickResolver,
    ) -> TickResult:
        world = self.load_world(world_id)
        if world.time.tick != expected_tick:
            raise TickConflictError("stale tick")
        submitted_tick = expected_tick + 1
        queued = tuple(
            item for item in self.pending[world_id] if item.submitted_tick == submitted_tick
        )
        result = resolver(world, tuple(item.value for item in queued))
        self.worlds[world_id] = result.world
        self.snapshots[(world_id, result.world.time.tick)] = result.world
        consumed_ids = {item.queue_id for item in queued}
        self.pending[world_id] = [
            item for item in self.pending[world_id] if item.queue_id not in consumed_ids
        ]
        current = self.histories[world_id]
        self.histories[world_id] = EventHistory((*current.events, *result.events))
        return result

    def claim_manual_tick(
        self,
        world_id: UUID,
        *,
        expected_tick: int,
        now: datetime,
    ) -> TickRunClaim:
        world = self.load_world(world_id)
        if world.time.tick != expected_tick:
            raise TickConflictError("stale tick")
        return TickRunClaim(
            run_id=uuid4(),
            world_id=world_id,
            target_tick=expected_tick + 1,
            trigger=TickRunTrigger.MANUAL,
            claim_token=uuid4(),
            started_at=now.astimezone(UTC),
            attempt_count=1,
        )

    def execute_claimed_tick(
        self,
        claim: TickRunClaim,
        *,
        resolver: TickResolver,
        next_eligible_at: datetime,
    ) -> TickResult:
        del next_eligible_at
        return self.execute_tick(
            claim.world_id,
            expected_tick=claim.target_tick - 1,
            resolver=resolver,
        )

    def load_history(self, world_id: UUID) -> EventHistory:
        self.load_world(world_id)
        return self.histories[world_id]


@pytest.fixture
async def client() -> AsyncIterator[httpx2.AsyncClient]:
    repository = InMemoryWorldRepository()
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repository
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as value:
        yield value


async def _create_world(client: httpx2.AsyncClient) -> dict[str, object]:
    response = await client.post(
        "/api/v1/dev/worlds",
        json={"seed": 41, "world_key": "api-test"},
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.anyio
async def test_create_list_load_and_status_use_public_dtos(
    client: httpx2.AsyncClient,
) -> None:
    created = await _create_world(client)
    world_id = created["id"]

    listed = await client.get("/api/v1/worlds")
    loaded = await client.get(f"/api/v1/worlds/{world_id}")
    regions = await client.get(f"/api/v1/worlds/{world_id}/regions")
    societies = await client.get(f"/api/v1/worlds/{world_id}/societies")

    assert listed.status_code == loaded.status_code == 200
    assert listed.json()["worlds"][0]["id"] == world_id
    assert loaded.json() == created
    assert regions.status_code == societies.status_code == 200
    assert len(regions.json()["regions"]) == 4
    assert len(societies.json()["societies"]) == 1

    raw_world_fields = {
        "seed",
        "metadata",
        "geography",
        "population",
        "economy",
        "knowledge",
        "governance",
        "directives",
    }
    assert raw_world_fields.isdisjoint(created)
    assert "resources" not in regions.json()["regions"][0]
    assert "institution" not in societies.json()["societies"][0]["governance"]
    assert created["versions"]["contract_version"] == "v1"


@pytest.mark.anyio
async def test_directive_queue_tick_lifecycle_and_history(
    client: httpx2.AsyncClient,
) -> None:
    created = await _create_world(client)
    world_id = created["id"]
    target = created["societies"][0]["subject"]

    submitted = await client.post(
        f"/api/v1/worlds/{world_id}/directives",
        json={
            "author": "player:one",
            "target": target,
            "intent": "strengthen_food_reserves",
            "priority": "normal",
        },
    )
    assert submitted.status_code == 202
    assert submitted.json()["submitted_tick"] == 1

    queued = await client.get(f"/api/v1/worlds/{world_id}/directives")
    assert len(queued.json()["pending"]) == 1
    assert queued.json()["directives"] == []

    advanced = await client.post(
        f"/api/v1/dev/worlds/{world_id}/ticks",
        json={"expected_tick": 0},
    )
    assert advanced.status_code == 200
    assert advanced.json()["world"]["tick"] == 1

    visible = await client.get(f"/api/v1/worlds/{world_id}/directives")
    assert visible.json()["pending"] == []
    assert visible.json()["directives"][0]["status"] == "queued"

    history = await client.get(
        f"/api/v1/worlds/{world_id}/history",
        params={"start_tick": 1, "end_tick": 1},
    )
    assert history.status_code == 200
    events = history.json()["events"]
    submitted_event = next(event for event in events if event["kind"] == "directive-submitted")
    queued_event = next(event for event in events if event["kind"] == "directive-queued")
    assert queued_event["cause_event_ids"] == [submitted_event["id"]]

    filtered = await client.get(
        f"/api/v1/worlds/{world_id}/history",
        params={
            "kind": "directive-queued",
            "subject_id": target["id"],
            "subject_kind": "society",
        },
    )
    assert filtered.status_code == 200
    assert [event["id"] for event in filtered.json()["events"]] == [queued_event["id"]]


@pytest.mark.anyio
async def test_missing_world_and_invalid_requests_are_normalized(
    client: httpx2.AsyncClient,
) -> None:
    missing_id = uuid4()
    missing = await client.get(f"/api/v1/worlds/{missing_id}")
    invalid_request = await client.post(
        "/api/v1/dev/worlds",
        json={"seed": "not-an-integer"},
    )

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "world_not_found"
    assert invalid_request.status_code == 422
    assert invalid_request.json()["error"]["code"] == "invalid_request"


@pytest.mark.anyio
async def test_invalid_directive_and_history_query_are_normalized(
    client: httpx2.AsyncClient,
) -> None:
    created = await _create_world(client)
    world_id = created["id"]

    directive = await client.post(
        f"/api/v1/worlds/{world_id}/directives",
        json={
            "author": "player:one",
            "target": {"kind": "society", "id": str(uuid4())},
        },
    )
    unsupported_query = await client.get(
        f"/api/v1/worlds/{world_id}/history",
        params={"unsupported": "value"},
    )
    invalid_range = await client.get(
        f"/api/v1/worlds/{world_id}/history",
        params={"start_tick": 2, "end_tick": 1},
    )

    assert directive.status_code == 422
    assert directive.json()["error"]["code"] == "invalid_directive"
    assert unsupported_query.status_code == 422
    assert unsupported_query.json()["error"]["code"] == "invalid_query"
    assert invalid_range.status_code == 422
    assert invalid_range.json()["error"]["code"] == "invalid_query"


@pytest.mark.anyio
async def test_manual_tick_rejects_stale_expected_tick(
    client: httpx2.AsyncClient,
) -> None:
    created = await _create_world(client)
    world_id = created["id"]

    first = await client.post(
        f"/api/v1/dev/worlds/{world_id}/ticks",
        json={"expected_tick": 0},
    )
    stale = await client.post(
        f"/api/v1/dev/worlds/{world_id}/ticks",
        json={"expected_tick": 0},
    )

    assert first.status_code == 200
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "tick_conflict"
