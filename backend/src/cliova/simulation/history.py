"""Deterministic query helpers over authoritative simulation events.

``SimulationEvent`` remains the single authoritative history record.  This module
only indexes, filters and renders those records; it does not persist events or
create a second event-sourcing model.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from cliova.simulation.types import (
    EntityId,
    SimulationEvent,
    SimulationExplanation,
    SimulationRunResult,
    TickResult,
)


def _event_order(event: SimulationEvent) -> tuple[int, int, str]:
    """Return a stable total ordering for history reads and generated chronology."""

    return (event.time.tick, event.time.year, event.id.hex)


@dataclass(frozen=True, slots=True, init=False)
class EventHistory:
    """Read-only deterministic view over stored ``SimulationEvent`` records."""

    events: tuple[SimulationEvent, ...]

    def __init__(self, events: Iterable[SimulationEvent] = ()) -> None:
        ordered = tuple(sorted(events, key=_event_order))
        event_ids = [event.id for event in ordered]
        if len(set(event_ids)) != len(event_ids):
            raise ValueError("history contains duplicate event IDs")
        object.__setattr__(self, "events", ordered)

    @classmethod
    def from_ticks(cls, ticks: Iterable[TickResult]) -> "EventHistory":
        """Collect event records from completed ticks without retaining tick debug data."""

        return cls(event for tick in ticks for event in tick.events)

    @classmethod
    def from_run(cls, run: SimulationRunResult) -> "EventHistory":
        """Collect the authoritative events emitted by a completed headless run."""

        return cls.from_ticks(run.ticks)

    def query(
        self,
        *,
        year: int | None = None,
        start_year: int | None = None,
        end_year: int | None = None,
        subject: EntityId | None = None,
        event_type: str | None = None,
        source: str | None = None,
    ) -> tuple[SimulationEvent, ...]:
        """Filter history while preserving its deterministic canonical ordering."""

        if year is not None and (start_year is not None or end_year is not None):
            raise ValueError("year cannot be combined with start_year or end_year")
        if start_year is not None and end_year is not None and start_year > end_year:
            raise ValueError("start_year cannot be greater than end_year")

        def matches(event: SimulationEvent) -> bool:
            if year is not None and event.time.year != year:
                return False
            if start_year is not None and event.time.year < start_year:
                return False
            if end_year is not None and event.time.year > end_year:
                return False
            if subject is not None and subject not in event.subjects:
                return False
            if event_type is not None and event.kind != event_type:
                return False
            if source is not None and event.source != source:
                return False
            return True

        return tuple(event for event in self.events if matches(event))

    def causal_chain(
        self, event_id: UUID, *, include_target: bool = True
    ) -> tuple[SimulationEvent, ...]:
        """Return all stored causes in cause-first order, deduplicating shared ancestors.

        Parent ordering follows each event's authoritative ``cause_event_ids`` tuple.
        Missing references and cycles are rejected instead of silently producing an
        incomplete or misleading explanation.
        """

        events_by_id = {event.id: event for event in self.events}
        if event_id not in events_by_id:
            raise KeyError(f"history does not contain event {event_id}")

        visited: set[UUID] = set()
        active: set[UUID] = set()
        ordered: list[SimulationEvent] = []

        def visit(current_id: UUID) -> None:
            if current_id in visited:
                return
            if current_id in active:
                raise ValueError(f"causal cycle detected at event {current_id}")

            current = events_by_id.get(current_id)
            if current is None:
                raise KeyError(f"history is missing causal event {current_id}")

            active.add(current_id)
            for cause_id in current.cause_event_ids:
                visit(cause_id)
            active.remove(current_id)
            visited.add(current_id)
            ordered.append(current)

        visit(event_id)
        if not include_target:
            ordered.pop()
        return tuple(ordered)

    def why(self, event_id: UUID) -> tuple[SimulationExplanation, ...]:
        """Project a causal chain into the existing structured explanation model."""

        return tuple(
            SimulationExplanation(
                source=event.source,
                message=event.reason,
                event_id=event.id,
                cause_event_ids=event.cause_event_ids,
            )
            for event in self.causal_chain(event_id)
        )

    def chronology(
        self,
        *,
        year: int | None = None,
        start_year: int | None = None,
        end_year: int | None = None,
        subject: EntityId | None = None,
        event_type: str | None = None,
        source: str | None = None,
    ) -> tuple[str, ...]:
        """Generate concise non-authoritative prose from authoritative event fields."""

        events = self.query(
            year=year,
            start_year=start_year,
            end_year=end_year,
            subject=subject,
            event_type=event_type,
            source=source,
        )
        return tuple(
            f"Year {event.time.year}: {event.reason} ({event.kind}, {event.source})"
            for event in events
        )
