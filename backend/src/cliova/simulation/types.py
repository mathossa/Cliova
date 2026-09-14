from dataclasses import dataclass, field


@dataclass(slots=True)
class WorldState:
    """Minimal authoritative state used while the real world model is introduced."""

    seed: int
    year: int = 0
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SimulationChange:
    """A simulation result together with the reason that produced it."""

    source: str
    key: str
    delta: float
    reason: str
