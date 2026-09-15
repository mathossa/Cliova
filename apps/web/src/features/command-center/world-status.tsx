import type { WorldSnapshot } from "./command-center.types";

export function WorldStatus({ world }: { world: WorldSnapshot }) {
  return (
    <div className="status-cluster" aria-label="Authoritative world status">
      <StatusCell label="World" value={world.label} />
      <StatusCell label="Year" value={String(world.year)} />
      <StatusCell label="Tick" value={String(world.tick)} accent />
      <StatusCell label="Population" value={world.population} />
      <StatusCell label="Food shortage" value={world.foodShortageSeverity} />
    </div>
  );
}

function StatusCell({
  label,
  value,
  accent = false,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="status-cell">
      <span>{label}</span>
      <strong className={accent ? "accent" : undefined}>{value}</strong>
    </div>
  );
}
