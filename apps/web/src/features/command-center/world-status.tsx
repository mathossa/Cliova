import type { WorldSnapshot } from "./command-center.types";

export function WorldStatus({ world }: { world: WorldSnapshot }) {
  return (
        <div className="status-cluster" aria-label="World status placeholders">
          <StatusCell label="World" value={world.worldName} />
          <StatusCell label="Year" value={`${world.year} · ${world.season}`} />
          <StatusCell label="Next tick" value={world.nextTick} accent />
          <StatusCell label="Treasury" value={world.treasury} />
          <StatusCell label="Status" value={world.worldStatus} warning />
        </div>
  );
}

function StatusCell({
  label,
  value,
  accent = false,
  warning = false,
}: {
  label: string;
  value: string;
  accent?: boolean;
  warning?: boolean;
}) {
  return (
    <div className="status-cell">
      <span>{label}</span>
      <strong className={warning ? "warning" : accent ? "accent" : undefined}>{value}</strong>
    </div>
  );
}

