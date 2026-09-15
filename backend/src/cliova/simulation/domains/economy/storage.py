"""Deterministic aggregate food storage, preservation and spoilage rules."""

from dataclasses import dataclass

from cliova.simulation.types import FoodReserveState, ResourceEconomyState


@dataclass(frozen=True, slots=True)
class FoodStorageConfig:
    """Centralized tunables for aggregate food reserve behavior."""

    perishable_retention: float = 0.65
    durable_retention: float = 0.95
    preservation_fraction: float = 0.25
    significant_flow_ratio: float = 0.10
    significant_flow_change_ratio: float = 0.25

    def __post_init__(self) -> None:
        for name in ("perishable_retention", "durable_retention", "preservation_fraction"):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        for name in ("significant_flow_ratio", "significant_flow_change_ratio"):
            if float(getattr(self, name)) < 0.0:
                raise ValueError(f"{name} cannot be negative")
        if self.durable_retention < self.perishable_retention:
            raise ValueError("durable retention must not be lower than perishable retention")


DEFAULT_FOOD_STORAGE_CONFIG = FoodStorageConfig()


@dataclass(frozen=True, slots=True)
class FoodStorageBalance:
    consumed: float
    stockpile: float
    deficit: float
    shortage_severity: float
    reserves: FoodReserveState


def balance_food_storage(
    current: ResourceEconomyState,
    *,
    production: float,
    demand: float,
    preservation_modifier: float,
    config: FoodStorageConfig = DEFAULT_FOOD_STORAGE_CONFIG,
) -> FoodStorageBalance:
    """Consume fresh/perishable/durable food, then preserve and apply storage loss.

    Draw order is explicit and stable: current production first, then prior perishable
    reserves, then prior durable reserves. Remaining fresh/perishable food may be
    converted to the durable pool before retention is applied to both reserve classes.
    """
    if current.resource != "food":
        raise ValueError("food storage accounting requires the aggregate food resource")
    if production < 0.0 or demand < 0.0:
        raise ValueError("food production and demand cannot be negative")
    if preservation_modifier <= 0.0:
        raise ValueError("preservation modifier must be positive")

    prior_perishable, prior_durable = reserve_pools(current)
    remaining_demand = _quantity(demand)

    consumed_from_production = _quantity(min(production, remaining_demand))
    remaining_demand = _quantity(remaining_demand - consumed_from_production)
    fresh_remaining = _quantity(production - consumed_from_production)

    consumed_from_perishable = _quantity(min(prior_perishable, remaining_demand))
    remaining_demand = _quantity(remaining_demand - consumed_from_perishable)
    perishable_remaining = _quantity(prior_perishable - consumed_from_perishable)

    consumed_from_durable = _quantity(min(prior_durable, remaining_demand))
    remaining_demand = _quantity(remaining_demand - consumed_from_durable)
    durable_remaining = _quantity(prior_durable - consumed_from_durable)

    preservable = _quantity(fresh_remaining + perishable_remaining)
    preservation_fraction = min(1.0, config.preservation_fraction * preservation_modifier)
    preserved = _quantity(preservable * preservation_fraction)
    perishable_before_loss = _quantity(preservable - preserved)
    durable_before_loss = _quantity(durable_remaining + preserved)

    ending_perishable = _quantity(perishable_before_loss * config.perishable_retention)
    ending_durable = _quantity(durable_before_loss * config.durable_retention)
    perishable_spoilage = _quantity(perishable_before_loss - ending_perishable)
    durable_spoilage = _quantity(durable_before_loss - ending_durable)

    consumed = _quantity(
        consumed_from_production + consumed_from_perishable + consumed_from_durable
    )
    deficit = _quantity(remaining_demand)
    shortage_severity = _quantity(deficit / demand) if demand > 0.0 else 0.0
    reserves = FoodReserveState(
        perishable=ending_perishable,
        durable=ending_durable,
        consumed_from_production=consumed_from_production,
        consumed_from_perishable=consumed_from_perishable,
        consumed_from_durable=consumed_from_durable,
        preserved=preserved,
        perishable_spoilage=perishable_spoilage,
        durable_spoilage=durable_spoilage,
        preservation_modifier=preservation_modifier,
    )
    return FoodStorageBalance(
        consumed=consumed,
        stockpile=reserves.total,
        deficit=deficit,
        shortage_severity=min(1.0, shortage_severity),
        reserves=reserves,
    )


def reserve_pools(current: ResourceEconomyState) -> tuple[float, float]:
    """Return authoritative reserve pools, treating legacy aggregate reserves as perishable."""
    if current.resource != "food":
        raise ValueError("reserve pools exist only for aggregate food")
    if current.food_reserves is None:
        return _quantity(current.stockpile), 0.0
    if abs(current.food_reserves.total - current.stockpile) > 1e-6:
        raise ValueError("aggregate food stockpile does not match reserve pools")
    return current.food_reserves.perishable, current.food_reserves.durable


def adjust_aggregate_food_reserves(
    current: ResourceEconomyState,
    *,
    new_stockpile: float,
) -> FoodReserveState:
    """Map an existing aggregate stockpile input onto reserve classes deterministically."""
    if new_stockpile < 0.0:
        raise ValueError("food stockpile cannot become negative")
    perishable, durable = reserve_pools(current)
    delta = _quantity(new_stockpile - current.stockpile)
    if delta >= 0.0:
        perishable = _quantity(perishable + delta)
    else:
        removal = -delta
        from_perishable = min(perishable, removal)
        perishable = _quantity(perishable - from_perishable)
        removal = _quantity(removal - from_perishable)
        durable = _quantity(max(0.0, durable - removal))
    return FoodReserveState(perishable=perishable, durable=durable)


def _quantity(value: float) -> float:
    return round(max(0.0, value), 6)
