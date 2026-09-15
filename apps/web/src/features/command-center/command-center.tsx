"use client";

import { FormEvent, useState } from "react";
import { describeApiError } from "../../lib/api";
import { DirectivesPanel } from "./directives-panel";
import { HistoryFeed } from "./history-feed";
import { LiveStatusPanel } from "./live-status-panels";
import { RegionOverview } from "./region-overview";
import { StrategicMap } from "./strategic-map";
import { WorldStatus } from "./world-status";
import {
  modules,
  type CommandCenterModule,
  type ModuleId,
} from "./command-center.data";
import type { CommandCenterProps, WorldSnapshot } from "./command-center.types";

const liveStatusModules = new Set<ModuleId>(["world", "society", "economy", "state", "scenarios"]);
const terminalHelp = "Available read-only commands: help · status · inspect · history. Submit simulation inputs from the Directives module.";

export function CommandCenter({ world, worlds, actions }: CommandCenterProps) {
  const [activeModule, setActiveModule] = useState<ModuleId>("terminal");
  const [command, setCommand] = useState("");
  const [terminalLines, setTerminalLines] = useState<string[]>([
    "> status",
    `Connected to ${world.connection}. World ${world.id.slice(0, 8)} is at year ${world.year}, tick ${world.tick}.`,
  ]);
  const [selectedRegion, setSelectedRegion] = useState(world.regions[0]?.id ?? "");
  const [actionError, setActionError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [ticking, setTicking] = useState(false);
  const [showCreateWorld, setShowCreateWorld] = useState(false);
  const [newWorldSeed, setNewWorldSeed] = useState("1");
  const [creatingWorld, setCreatingWorld] = useState(false);
  const [newWorldError, setNewWorldError] = useState<string | null>(null);

  const activeDefinition = modules.find((module) => module.id === activeModule) ?? modules[0]!;
  const selectedRegionView = world.regions.find((region) => region.id === selectedRegion) ?? world.regions[0] ?? null;
  const selectedRegionId = selectedRegionView?.id ?? "";

  function submitCommand(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = command.trim().toLowerCase();
    if (!normalized) return;

    let response = "Unknown UI command. Try help.";
    if (normalized === "help") response = terminalHelp;
    if (normalized === "status") {
      response = `Year ${world.year}, tick ${world.tick}, population ${world.population}, food shortage ${world.foodShortageSeverity}.`;
    }
    if (normalized.startsWith("inspect")) {
      response = selectedRegionView
        ? `${selectedRegionView.label}: population ${selectedRegionView.population}, ${selectedRegionView.terrain} / ${selectedRegionView.biome}.`
        : "No authoritative region is available to inspect.";
    }
    if (normalized === "history") response = `${world.feed.length} recent authoritative history event(s) loaded.`;

    setTerminalLines((current) => [...current.slice(-7), `> ${command.trim()}`, response]);
    setCommand("");
  }

  async function refresh() {
    setActionError(null);
    setRefreshing(true);
    try {
      await actions.refresh();
    } catch (error) {
      setActionError(describeApiError(error));
    } finally {
      setRefreshing(false);
    }
  }

  async function advanceTick() {
    setActionError(null);
    setTicking(true);
    try {
      await actions.advanceDevelopmentTick();
    } catch (error) {
      setActionError(describeApiError(error));
    } finally {
      setTicking(false);
    }
  }

  async function createDevelopmentWorld(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const seed = Number(newWorldSeed);
    if (!Number.isInteger(seed)) {
      setNewWorldError("Seed must be an integer.");
      return;
    }

    setNewWorldError(null);
    setCreatingWorld(true);
    try {
      await actions.createWorld(seed);
      setShowCreateWorld(false);
    } catch (error) {
      setNewWorldError(describeApiError(error));
    } finally {
      setCreatingWorld(false);
    }
  }

  return (
    <main className="command-center">
      <header className="cc-topbar">
        <div className="brand-block">
          <div className="brand-mark" aria-hidden="true">△</div>
          <div>
            <strong>CLIOVA</strong>
            <span>SIMULATION LAB</span>
          </div>
        </div>

        <div className="operator-context" title="Development mode has world-wide access; player-to-society ownership is not active yet.">
          <span>YOUR ROLE</span>
          <strong>Development operator</strong>
          <small>World-wide access · no society assignment</small>
        </div>

        <WorldStatus world={world} />
        <div className="live-actions">
          <label>
            <span>Development world</span>
            <select
              aria-label="Development world"
              value={world.id}
              onChange={(event) => void actions.selectWorld(event.target.value)}
              disabled={worlds.length <= 1}
            >
              {worlds.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.id.slice(0, 8)} · Y{item.year} · T{item.tick}
                </option>
              ))}
            </select>
          </label>
          <button type="button" onClick={() => setShowCreateWorld(true)} disabled={refreshing || ticking}>
            + New world
          </button>
          <button type="button" onClick={() => void refresh()} disabled={refreshing || ticking}>
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
          <button
            type="button"
            className="dev-tick-button"
            onClick={() => void advanceTick()}
            disabled={refreshing || ticking}
            title="Development/debug operation: advance the authoritative simulation by one manual tick"
          >
            {ticking ? "Advancing…" : "Dev +1 tick"}
          </button>
        </div>
      </header>

      {actionError && (
        <div className="global-action-error" role="alert">
          <strong>Operation failed.</strong> {actionError} The displayed snapshot remains the last successfully loaded authoritative state.
        </div>
      )}

      <nav className="module-nav" aria-label="Cliova modules">
        {modules.map((module) => (
          <button
            key={module.id}
            type="button"
            aria-pressed={module.id === activeModule}
            className={module.id === activeModule ? "module-tab active" : "module-tab"}
            onClick={() => setActiveModule(module.id)}
          >
            {module.label}
          </button>
        ))}
      </nav>

      <section className="cc-workspace">
        <section className="control-column" aria-label="Command and module workspace">
          {activeModule === "terminal" && (
            <TerminalWorkspace
              world={world}
              selectedRegion={selectedRegionId}
              setSelectedRegion={setSelectedRegion}
              command={command}
              setCommand={setCommand}
              terminalLines={terminalLines}
              submitCommand={submitCommand}
            />
          )}
          {activeModule === "history" && <HistoryFeed feed={world.feed} />}
          {activeModule === "directives" && <DirectivesPanel world={world} onSubmit={actions.submitDirective} />}
          {liveStatusModules.has(activeModule) && <LiveStatusPanel moduleId={activeModule} world={world} />}
          {activeModule !== "terminal"
            && activeModule !== "history"
            && activeModule !== "directives"
            && !liveStatusModules.has(activeModule)
            && <ModulePlaceholder module={activeDefinition} />}
        </section>

        <section className="data-column" aria-label="Map and data workspace">
          <div className="map-panel panel">
            <div className="panel-heading map-heading">
              <div>
                <span className="eyebrow">Generated strategic geography</span>
                <h2>World / region map</h2>
              </div>
              <span className={world.map.available ? "live-badge" : "placeholder-badge"}>
                {world.map.available ? "interactive" : "unavailable"}
              </span>
            </div>
            <StrategicMap
              world={world}
              selectedRegionId={selectedRegionId}
              onSelectRegion={setSelectedRegion}
            />
          </div>

          <div className="dashboard-row">
            <div className="metrics-grid">
              {world.metrics.map((metric) => (
                <article className="metric-card panel" key={metric.label}>
                  <span className="eyebrow">{metric.label}</span>
                  <div className="metric-value-row">
                    <strong>{metric.value}</strong>
                  </div>
                  <small>{metric.detail}</small>
                </article>
              ))}
            </div>

            <aside className="pressures panel">
              <div className="panel-heading compact">
                <div>
                  <span className="eyebrow">Authoritative scenarios</span>
                  <h2>Active tensions</h2>
                </div>
                <span className="live-badge">live</span>
              </div>
              <div className="pressure-list">
                {world.pressures.length === 0 && <p className="empty-copy">No active tensions.</p>}
                {world.pressures.map((pressure) => (
                  <button type="button" key={pressure.id} onClick={() => setActiveModule("scenarios")}>
                    <span>{pressure.label}</span>
                    <strong>{pressure.milestone}</strong>
                  </button>
                ))}
              </div>
            </aside>
          </div>
        </section>
      </section>

      <footer className="cc-footer">
        <span>Simulation Lab · live API v1 · contract {world.contractVersion}</span>
        <span>Explicit refresh · development manual tick · no realtime polling</span>
      </footer>

      {showCreateWorld && (
        <div className="new-world-backdrop" role="presentation">
          <section className="panel new-world-dialog" role="dialog" aria-modal="true" aria-labelledby="new-world-title">
            <div className="panel-heading compact">
              <div>
                <span className="eyebrow">Generated development world</span>
                <h2 id="new-world-title">Create new world</h2>
              </div>
              <button type="button" className="dialog-close" onClick={() => setShowCreateWorld(false)} disabled={creatingWorld} aria-label="Close create world dialog">×</button>
            </div>
            <form className="new-world-form" onSubmit={createDevelopmentWorld}>
              <p>Create a persisted #59-generated development world. It will become the active world immediately.</p>
              <label>
                Seed
                <input value={newWorldSeed} onChange={(event) => setNewWorldSeed(event.target.value)} inputMode="numeric" autoFocus />
              </label>
              {newWorldError && <p className="action-error" role="alert">{newWorldError}</p>}
              <div className="dialog-actions">
                <button type="button" onClick={() => setShowCreateWorld(false)} disabled={creatingWorld}>Cancel</button>
                <button type="submit" disabled={creatingWorld}>{creatingWorld ? "Creating…" : "Create generated world"}</button>
              </div>
            </form>
          </section>
        </div>
      )}
    </main>
  );
}

function TerminalWorkspace({
  world,
  selectedRegion,
  setSelectedRegion,
  command,
  setCommand,
  terminalLines,
  submitCommand,
}: {
  world: WorldSnapshot;
  selectedRegion: string;
  setSelectedRegion: (value: string) => void;
  command: string;
  setCommand: (value: string) => void;
  terminalLines: string[];
  submitCommand: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <div className="terminal-workspace">
      <section className="terminal-console panel" aria-label="Read-only terminal">
        <div className="console-history" role="log" aria-label="Command responses">
          {terminalLines.map((line, index) => (
            <div key={`${index}-${line}`} className={line.startsWith(">") ? "console-command" : "console-response"}>
              {line}
            </div>
          ))}
        </div>
        <small>Read-only inspection only. Simulation inputs belong in <code>Directives</code>.</small>
        <form onSubmit={submitCommand}>
          <span aria-hidden="true">›</span>
          <input
            value={command}
            onChange={(event) => setCommand(event.target.value)}
            placeholder="status"
            aria-label="Cliova read-only command"
          />
          <button type="submit">Run</button>
        </form>
      </section>
      <RegionOverview regions={world.regions} selectedId={selectedRegion} onSelect={setSelectedRegion} />
      <HistoryFeed feed={world.feed} />
    </div>
  );
}

function ModulePlaceholder({ module }: { module: CommandCenterModule }) {
  return (
    <div className="module-placeholder panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">API v1 boundary</span>
          <h1>{module.label}</h1>
        </div>
        <span className="placeholder-badge">not modeled</span>
      </div>
      <p className="module-description">{module.description}</p>
      <div className="placeholder-section">
        <span className="eyebrow">Future views</span>
        <div className="placeholder-grid">
          {module.plannedViews.map((view) => (
            <div className="placeholder-card" key={view}>
              <span>{view}</span>
              <small>Not exposed by API v1</small>
            </div>
          ))}
        </div>
      </div>
      <div className="integration-note">
        <strong>No demo fallback</strong>
        <p>This area intentionally shows no simulated value until a stable public API contract exposes it.</p>
      </div>
    </div>
  );
}
