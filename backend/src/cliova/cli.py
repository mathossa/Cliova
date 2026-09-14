import argparse

from cliova.simulation.engine import SimulationEngine
from cliova.simulation.types import WorldState


def main() -> None:
    parser = argparse.ArgumentParser(prog="cliova")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--years", type=int, default=1)
    args = parser.parse_args()

    result = SimulationEngine().run(WorldState.create(seed=args.seed), years=args.years)
    print(f"World seed={result.world.seed} year={result.world.year}")


if __name__ == "__main__":
    main()
