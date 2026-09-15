import type { ReactNode } from "react";
import type { ModuleId } from "./command-center.data";
import type { WorldSnapshot } from "./command-center.types";

export function LiveStatusPanel({ moduleId, world }: { moduleId: ModuleId; world: WorldSnapshot }) {
  if (moduleId === "world") {
    return (
      <LivePanel eyebrow="API v1 · world" title="Regions">
        {world.regions.length === 0 ? <Empty text="No region status available." /> : (
          <ul className="live-list">
            {world.regions.map((region) => (
              <li key={region.id}>
                <strong>{region.label}</strong>
                <span>{region.terrain} · {region.biome}</span>
                <small>population {region.population} · habitability {region.habitability} · water {region.waterAccess}</small>
              </li>
            ))}
          </ul>
        )}
      </LivePanel>
    );
  }

  if (moduleId === "society") {
    return (
      <LivePanel eyebrow="API v1 · society" title="Population status">
        <p className="module-description compact-description">
          Society names are not part of API v1 yet, so the interface uses each society&apos;s home region as its readable label.
        </p>
        {world.societies.length === 0 ? <Empty text="No society summaries available." /> : (
          <ul className="live-list">
            {world.societies.map((society) => (
              <li key={society.id}>
                <strong>{society.label}</strong>
                <span>population {society.population}</span>
                <small>home region {society.regionLabel} · technical ID {shortId(society.id)}</small>
              </li>
            ))}
          </ul>
        )}
      </LivePanel>
    );
  }

  if (moduleId === "economy") {
    return (
      <LivePanel eyebrow="API v1 · stable projection" title="Food condition">
        <p className="module-description">
          These are high-level public food DTOs. Internal cultivation, preservation and mobility mechanics remain authoritative backend concerns.
        </p>
        {world.societies.length === 0 ? <Empty text="No society food status available." /> : (
          <div className="status-card-grid">
            {world.societies.map((society) => (
              <article className="status-card" key={society.id}>
                <strong>{society.label}</strong>
                <StatusRow label="Food security" value={society.food.foodSecurity} />
                <StatusRow label="Production" value={society.food.production} />
                <StatusRow label="Demand" value={society.food.demand} />
                <StatusRow label="Stockpile" value={society.food.stockpile} />
                <StatusRow label="Deficit" value={society.food.deficit} />
                <StatusRow label="Shortage" value={society.food.shortageSeverity} />
              </article>
            ))}
          </div>
        )}
      </LivePanel>
    );
  }

  if (moduleId === "state") {
    return (
      <LivePanel eyebrow="API v1 · governance" title="Governance condition">
        {world.societies.length === 0 ? <Empty text="No governance summaries available." /> : (
          <div className="status-card-grid">
            {world.societies.map((society) => (
              <article className="status-card" key={society.id}>
                <strong>{society.label}</strong>
                <StatusRow label="Legitimacy" value={society.governance.legitimacy} />
                <StatusRow label="Execution capacity" value={society.governance.executionCapacity} />
                <StatusRow label="Internal resistance" value={society.governance.internalResistance} />
              </article>
            ))}
          </div>
        )}
      </LivePanel>
    );
  }

  if (moduleId === "scenarios") {
    return (
      <LivePanel eyebrow="API v1 · pressures" title="Active pressures">
        {world.pressures.length === 0 ? <Empty text="No active pressures." /> : (
          <ul className="live-list">
            {world.pressures.map((pressure) => (
              <li key={pressure.id} data-pressure-id={pressure.id}>
                <strong>{pressure.label}</strong>
                <span>{pressure.milestone} · intensity {pressure.intensity}</span>
                <small>
                  {pressure.regionLabel} · age {pressure.ageTicks} ticks · {pressure.causeCount} causal reference{pressure.causeCount === 1 ? "" : "s"}
                </small>
              </li>
            ))}
          </ul>
        )}
      </LivePanel>
    );
  }

  return null;
}

function LivePanel({ eyebrow, title, children }: { eyebrow: string; title: string; children: ReactNode }) {
  return (
    <section className="panel live-status-panel">
      <div className="panel-heading compact">
        <div>
          <span className="eyebrow">{eyebrow}</span>
          <h1>{title}</h1>
        </div>
        <span className="live-badge">live</span>
      </div>
      <div className="live-panel-body">{children}</div>
    </section>
  );
}

function StatusRow({ label, value }: { label: string; value: string }) {
  return <div className="status-row"><span>{label}</span><strong>{value}</strong></div>;
}

function Empty({ text }: { text: string }) {
  return <p className="empty-copy">{text}</p>;
}

function shortId(value: string): string {
  return value.slice(0, 8);
}
