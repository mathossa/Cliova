"""HTTP v1 routes for the Cliova 0.1 development vertical slice."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from cliova.api.dependencies import get_repository
from cliova.api.errors import ApiError
from cliova.api.v1.models import (
    AttentionItemsResponse,
    CreateDevelopmentWorldRequest,
    DecisionOpportunityListResponse,
    DecisionOpportunityStatusDto,
    DirectiveListResponse,
    DirectiveSubmissionRequest,
    EntityKindDto,
    HistoryResponse,
    ManualTickRequest,
    ManualTickResponse,
    QueuedDirective,
    RegionStatusResponse,
    SocietyStatusResponse,
    WorldListResponse,
    WorldSummary,
)
from cliova.api.v1.projections import (
    attention_item,
    authoritative_directives,
    decision_opportunity,
    history_event,
    queued_directive,
    region_statuses,
    society_summaries,
    world_list_item,
    world_summary,
)
from cliova.application.attention import DecisionResponseError
from cliova.application.development import create_development_world, create_simulation_engine
from cliova.application.scheduling import ScheduledTickService
from cliova.application.worlds import WorldRepository
from cliova.simulation.domains.directives import directive_input
from cliova.simulation.types import EntityId

router = APIRouter(prefix="/api/v1")
RepositoryDependency = Annotated[WorldRepository, Depends(get_repository)]


@router.post(
    "/dev/worlds",
    response_model=WorldSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_world(
    request: CreateDevelopmentWorldRequest,
    repository: RepositoryDependency,
) -> WorldSummary:
    world = create_development_world(seed=request.seed, world_key=request.world_key)
    repository.create_world(world)
    return world_summary(world)


@router.get("/worlds", response_model=WorldListResponse)
def list_worlds(repository: RepositoryDependency) -> WorldListResponse:
    return WorldListResponse(
        worlds=tuple(world_list_item(world) for world in repository.list_worlds())
    )


@router.get("/worlds/{world_id}", response_model=WorldSummary)
def get_world(world_id: UUID, repository: RepositoryDependency) -> WorldSummary:
    return world_summary(repository.load_world(world_id))


@router.get("/worlds/{world_id}/regions", response_model=RegionStatusResponse)
def get_regions(world_id: UUID, repository: RepositoryDependency) -> RegionStatusResponse:
    world = repository.load_world(world_id)
    return RegionStatusResponse(
        world_id=world.id.value,
        tick=world.time.tick,
        regions=region_statuses(world),
    )


@router.get("/worlds/{world_id}/societies", response_model=SocietyStatusResponse)
def get_societies(world_id: UUID, repository: RepositoryDependency) -> SocietyStatusResponse:
    world = repository.load_world(world_id)
    return SocietyStatusResponse(
        world_id=world.id.value,
        tick=world.time.tick,
        societies=society_summaries(world),
    )


@router.get("/worlds/{world_id}/history", response_model=HistoryResponse)
def get_history(
    world_id: UUID,
    request: Request,
    repository: RepositoryDependency,
    year: int | None = None,
    start_year: int | None = None,
    end_year: int | None = None,
    start_tick: Annotated[int | None, Query(ge=0)] = None,
    end_tick: Annotated[int | None, Query(ge=0)] = None,
    subject_kind: EntityKindDto | None = None,
    subject_id: UUID | None = None,
    kind: Annotated[str | None, Query(min_length=1)] = None,
    source: Annotated[str | None, Query(min_length=1)] = None,
) -> HistoryResponse:
    allowed_parameters = {
        "year",
        "start_year",
        "end_year",
        "start_tick",
        "end_tick",
        "subject_kind",
        "subject_id",
        "kind",
        "source",
    }
    unsupported = sorted(set(request.query_params.keys()) - allowed_parameters)
    if unsupported:
        raise ApiError(
            422,
            "invalid_query",
            f"Unsupported query parameter(s): {', '.join(unsupported)}.",
        )
    if (subject_kind is None) != (subject_id is None):
        raise ApiError(
            422,
            "invalid_query",
            "subject_kind and subject_id must be supplied together.",
        )
    if start_tick is not None and end_tick is not None and start_tick > end_tick:
        raise ApiError(422, "invalid_query", "start_tick cannot be greater than end_tick.")

    subject = (
        EntityId(kind=subject_kind, value=subject_id)
        if subject_kind is not None and subject_id is not None
        else None
    )
    history = repository.load_history(world_id)
    try:
        events = history.query(
            year=year,
            start_year=start_year,
            end_year=end_year,
            subject=subject,
            event_type=kind,
            source=source,
        )
    except ValueError as exc:
        raise ApiError(422, "invalid_query", str(exc)) from exc

    events = tuple(
        event
        for event in events
        if (start_tick is None or event.time.tick >= start_tick)
        and (end_tick is None or event.time.tick <= end_tick)
    )
    return HistoryResponse(
        world_id=world_id,
        events=tuple(history_event(event) for event in events),
    )


@router.get("/worlds/{world_id}/attention-items", response_model=AttentionItemsResponse)
def get_attention_items(world_id: UUID, repository: RepositoryDependency) -> AttentionItemsResponse:
    return AttentionItemsResponse(
        world_id=world_id,
        items=tuple(attention_item(item) for item in repository.list_attention_items(world_id)),
    )


@router.get(
    "/worlds/{world_id}/decision-opportunities",
    response_model=DecisionOpportunityListResponse,
)
def get_decision_opportunities(
    world_id: UUID,
    repository: RepositoryDependency,
    status_filter: Annotated[DecisionOpportunityStatusDto | None, Query(alias="status")] = "open",
) -> DecisionOpportunityListResponse:
    opportunities = repository.list_decision_opportunities(world_id)
    if status_filter is not None:
        opportunities = tuple(
            opportunity
            for opportunity in opportunities
            if opportunity.status.value == status_filter
        )
    return DecisionOpportunityListResponse(
        world_id=world_id,
        opportunities=tuple(decision_opportunity(item) for item in opportunities),
    )


@router.get("/worlds/{world_id}/directives", response_model=DirectiveListResponse)
def get_directives(world_id: UUID, repository: RepositoryDependency) -> DirectiveListResponse:
    world = repository.load_world(world_id)
    pending = tuple(
        projection
        for item in repository.load_pending_inputs(world_id)
        if (projection := queued_directive(item)) is not None
    )
    return DirectiveListResponse(
        world_id=world.id.value,
        pending=pending,
        directives=authoritative_directives(world),
    )


@router.post(
    "/worlds/{world_id}/directives",
    response_model=QueuedDirective,
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_directive(
    world_id: UUID,
    request: DirectiveSubmissionRequest,
    repository: RepositoryDependency,
) -> QueuedDirective:
    world = repository.load_world(world_id)
    target = EntityId(kind=request.target.kind, value=request.target.id)
    if not any(state.subject_id == target for state in world.governance):
        raise ApiError(
            422,
            "invalid_directive",
            "Directive target is not an active society/polity.",
        )

    try:
        value = directive_input(
            author=request.author,
            target_subject=target,
            intent=request.intent,
            priority=request.priority,
        )
        queued = (
            repository.queue_decision_response(
                world_id,
                opportunity_id=request.decision_opportunity_id,
                value=value,
            )
            if request.decision_opportunity_id is not None
            else repository.queue_input(world_id, value)
        )
    except DecisionResponseError as exc:
        conflict_codes = {
            "decision_opportunity_expired",
            "decision_opportunity_already_responded",
        }
        raise ApiError(
            409 if exc.code in conflict_codes else 422,
            exc.code,
            str(exc),
        ) from exc
    except ValueError as exc:
        raise ApiError(422, "invalid_directive", str(exc)) from exc

    projection = queued_directive(queued)
    if projection is None:
        raise RuntimeError("authoritative directive input could not be projected")
    return projection


@router.post(
    "/dev/worlds/{world_id}/ticks",
    response_model=ManualTickResponse,
)
def advance_development_tick(
    world_id: UUID,
    request: ManualTickRequest,
    repository: RepositoryDependency,
) -> ManualTickResponse:
    result = ScheduledTickService(create_simulation_engine(), repository).advance_manual(
        world_id,
        expected_tick=request.expected_tick,
    )
    return ManualTickResponse(
        world=world_summary(result.world),
        event_ids=tuple(event.id for event in result.events),
    )
