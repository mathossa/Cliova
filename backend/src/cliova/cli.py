import argparse

from cliova.simulation.engine import SimulationEngine
from cliova.simulation.types import WorldState


def main() -> None:
    parser = argparse.ArgumentParser(prog="cliova")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--years", type=int, default=1)
    args = parser.parse_args()

    engine = SimulationEngine()
    world = WorldState(seed=args.seed)
    world, _ = engine.run(world, years=args.years)
    print(f"World seed={world.seed} year={world.year}")


if __name__ == "__main__":
    main()
