import random

import numpy as np
import pytest
from numpy.random import PCG64

from cliova.simulation.randomness import SeededRandom


def draws(seed: int = 42, tick: int = 1, domain: str = "world") -> list[float]:
    rng = SeededRandom(seed=seed, tick=tick, domain=domain)
    return [rng.random() for _ in range(8)]


def test_seeded_stream_is_reproducible_and_in_range() -> None:
    values = draws()
    assert values == draws()
    assert all(0 <= value < 1 for value in values)
    assert len(set(values)) > 1
    assert values != draws(seed=43)
    assert values != draws(tick=2)
    assert values != draws(domain="population")


def test_streams_are_isolated_and_do_not_touch_global_rng() -> None:
    python_state = random.getstate()
    numpy_state = np.random.get_state()
    expected = draws()
    unrelated = SeededRandom(seed=42, tick=1, domain="unrelated")
    for _ in range(50):
        unrelated.random()
    assert draws() == expected
    assert random.getstate() == python_state
    after = np.random.get_state()
    assert after[0] == numpy_state[0]
    assert np.array_equal(after[1], numpy_state[1])
    assert after[2:] == numpy_state[2:]


def test_fixed_raw_to_float_conversion(monkeypatch: pytest.MonkeyPatch) -> None:
    class FixedRaw:
        def random_raw(self) -> int:
            return (1 << 64) - 1

    rng = SeededRandom(seed=0, tick=0, domain="world")
    monkeypatch.setattr(rng, "_generator", FixedRaw())
    assert rng.random() == 1 - 2**-53


def test_upstream_pcg64_reference_vector() -> None:
    # NumPy PCG64 seed=42 reference guards accidental bit-generator replacement.
    assert int(PCG64(42).random_raw()) == 14276969152011380360


@pytest.mark.parametrize("seed", [0, -42, 2**128])
def test_full_integer_seed_support(seed: int) -> None:
    assert draws(seed=seed) == draws(seed=seed)


def test_invalid_stream_context_is_rejected() -> None:
    with pytest.raises(ValueError):
        SeededRandom(seed=42, tick=-1, domain="world")
    with pytest.raises(ValueError):
        SeededRandom(seed=42, tick=True, domain="world")
    with pytest.raises(ValueError):
        SeededRandom(seed=True, tick=0, domain="world")
    with pytest.raises(ValueError):
        SeededRandom(seed=42, tick=0, domain="")
