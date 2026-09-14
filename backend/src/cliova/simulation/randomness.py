"""Explicit deterministic RNG dependency; no process/global random state."""

import hashlib
import json
from typing import Protocol

from numpy.random import PCG64

from cliova.simulation.types import RNG_ALGORITHM


class RandomSource(Protocol):
    def random(self) -> float:
        """Return a value in [0, 1)."""
        ...


class SeededRandom:
    """Thin adapter over NumPy's stable PCG64 raw integer stream."""

    def __init__(self, *, seed: int, tick: int, domain: str) -> None:
        if type(seed) is not int or type(tick) is not int or tick < 0:
            raise ValueError("seed must be an integer and tick a non-negative integer")
        if not isinstance(domain, str) or not domain:
            raise ValueError("domain must be a non-empty string")
        material = json.dumps(
            [RNG_ALGORITHM, seed, tick, domain], ensure_ascii=True, separators=(",", ":")
        ).encode("utf-8")
        entropy = int.from_bytes(hashlib.sha256(material).digest(), "big")
        self._generator = PCG64(entropy)

    def random(self) -> float:
        # Fixed 53-bit conversion avoids depending on Generator distribution changes.
        return (int(self._generator.random_raw()) >> 11) / (1 << 53)


def random_for(seed: int, tick: int, domain: str) -> RandomSource:
    """Create one stream per domain/tick; reuse it for all draws within that step."""
    return SeededRandom(seed=seed, tick=tick, domain=domain)
