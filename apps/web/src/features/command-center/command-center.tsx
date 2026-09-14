"use client";

import { FormEvent, useState } from "react";
import type { WorldSnapshot } from "./command-center.types";
import { HistoryFeed } from "./history-feed";
import { RegionOverview } from "./region-overview";
import { WorldStatus } from "./world-status";

import {
  assetPaths,
  previewSparkline,
  modules,
  type CommandCenterModule,
  type ModuleId,
} from "./command-center.data";

const terminalHelp = "Available UI commands: help · status · inspect <entity> · why <event>. Simulation execution is not connected yet.";

export function CommandCenter({ world }: { world: WorldSnapshot }) {
  const [activeModule, setActiveModule] = useState<ModuleId>("terminal");
  const [command, setCommand] = useState("");
  const [terminalLines, setTerminalLines] = useState<string[]>([
    "> status",
    `${world.connection}. Showing presentation placeholders.`,
  ]);
  const [selectedMarker, setSelectedMarker] = useState(world.mapMarkers[0]?.id ?? "");

  const activeDefinition = modules.find((module) => module.id === activeModule) ?? modules[0];
  const marker = world.mapMarkers.find((item) => item.id === selectedMarker);

  function submitCommand(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = command.trim();
    if (!normalized) return;

    let response = "Command captured by the UI scaffold. The authoritative command/directive API is not connected yet.";
    if (normalized === "help") response = terminalHelp;
    if (normalized === "status") response = `${world.connection}. Mock snapshot year: ${world.year}.`;
    if (normalized.startsWith("inspect")) response = "Inspection UI is ready; entity lookup will be delegated to the API rather than implemented in TypeScript.";
    if (normalized.startsWith("why")) response = "Explainability placeholder: causes will be rendered from backend changes/events when available.";

    setTerminalLines((current) => [...current.slice(-5), `> ${normalized}`, response]);
    setCommand("");
  }

  return (
    <main className="command-center">
      <header className="cc-topbar">
        <div className="brand-block">
          <div className="brand-mark" aria-hidden="true">△</div>
          <div>
            <strong>CLIOVA</strong>
            <span>WORLD COMMAND</span>
          </div>
        </div>

        <WorldStatus world={world} />
        <button className="icon-button" type="button" disabled aria-label="Settings (not available yet)">⚙</button>
      </header>

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
          {activeModule === "terminal" ? (
            <TerminalWorkspace
              world={world}
              selectedId={selectedMarker}
              command={command}
              setCommand={setCommand}
              terminalLines={terminalLines}
              submitCommand={submitCommand}
              selectedLabel={marker?.label ?? "No region selected"}
            />
          ) : (
            activeModule === "history" ? <HistoryFeed feed={world.feed} /> : <ModulePlaceholder module={activeDefinition} />
          )}
        </section>

        <section className="data-column" aria-label="Map and data workspace">
          <div className="map-panel panel">
            <div className="panel-heading map-heading">
              <div>
                <span className="eyebrow">World / regional view</span>
                <h2>Operational map</h2>
              </div>
              <div className="map-toolbar" aria-label="Map controls placeholders">
                <button type="button" disabled>Layers</button>
                <button type="button" disabled>Filter</button>
                <button type="button" disabled aria-label="Zoom in">+</button>
                <button type="button" disabled aria-label="Zoom out">−</button>
              </div>
            </div>

            <div
              className="map-canvas"
              style={{
                backgroundImage: `linear-gradient(180deg, rgba(8, 14, 19, .08), rgba(8, 14, 19, .28)), url(${assetPaths.worldMap})`,
              }}
            >
              <div className="map-fallback-grid" aria-hidden="true" />
              {world.mapMarkers.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`map-marker ${item.kind} ${selectedMarker === item.id ? "selected" : ""}`}
                  style={{ left: `${item.x}%`, top: `${item.y}%` }}
                  onClick={() => setSelectedMarker(item.id)}
                  aria-pressed={selectedMarker === item.id}
                  aria-label={`Inspect ${item.label}`}
                >
                  <span className="marker-dot" />
                  <span>{item.label}</span>
                </button>
              ))}
              <div className="map-legend">
                <span><i className="legend-dot" /> settlement</span>
                <span><i className="legend-square" /> resource</span>
                <span><i className="legend-line" /> route / relation</span>
              </div>
              <div className="map-selection">
                <span>Selected</span>
                <strong>{marker?.label ?? "No map location selected"}</strong>
                <small>Illustrative map · preview</small>
              </div>
            </div>
          </div>

          <div className="dashboard-row">
            <div className="metrics-grid">
              {world.metrics.length === 0 && <p>No metrics available.</p>}
              {world.metrics.map((metric) => (
                <article className="metric-card panel" key={metric.label}>
                  <span className="eyebrow">{metric.label}</span>
                  <div className="metric-value-row">
                    <strong>{metric.value}</strong>
                    <span className={`tone-${metric.tone}`}>{metric.delta}</span>
                  </div>
                  <div className="sparkline" aria-hidden="true">
                    {previewSparkline.map((height, point) => <i key={point} style={{ height: `${height}%` }} />)}
                  </div>
                  <small>{metric.detail}</small>
                </article>
              ))}
            </div>

            <aside className="pressures panel">
              <div className="panel-heading compact">
                <div>
                  <span className="eyebrow">Scenarios</span>
                  <h2>Current pressures</h2>
                </div>
                <span className="placeholder-badge">placeholder</span>
              </div>
              <div className="pressure-list">
                {world.pressures.length === 0 && <p>No pressure data available.</p>}
                {world.pressures.map((pressure) => (
                  <button type="button" key={pressure.label} onClick={() => setActiveModule("scenarios")}>
                    <span>{pressure.label}</span>
                    <strong className={`severity-${pressure.severity.toLowerCase()}`}>{pressure.severity}</strong>
                  </button>
                ))}
              </div>
            </aside>
          </div>
        </section>
      </section>

      <footer className="cc-footer">
        <span>Simulation Lab · presentation preview</span>
        <span>API: {world.connection}</span>
      </footer>
    </main>
  );
}

function TerminalWorkspace({
  world,
  selectedId,
  command,
  setCommand,
  terminalLines,
  submitCommand,
  selectedLabel,
}: {
  world: WorldSnapshot;
  selectedId: string;
  command: string;
  setCommand: (value: string) => void;
  terminalLines: string[];
  submitCommand: (event: FormEvent<HTMLFormElement>) => void;
  selectedLabel: string;
}) {
  return (
    <div className="terminal-workspace">
      <HistoryFeed feed={world.feed} />

      <RegionOverview region={world.selectedRegion?.id === selectedId ? world.selectedRegion : null} selectedLabel={selectedLabel} />

      <section className="terminal-console panel" aria-label="Terminal command placeholder">
        <div className="console-history" role="log" aria-label="Command responses">
          {terminalLines.map((line, index) => (
            <div key={`${index}-${line}`} className={line.startsWith(">") ? "console-command" : "console-response"}>
              {line}
            </div>
          ))}
        </div>
        <form onSubmit={submitCommand}>
          <span aria-hidden="true">›</span>
          <input
            value={command}
            onChange={(event) => setCommand(event.target.value)}
            placeholder="inspect northreach"
            aria-label="Cliova command"
          />
          <button type="submit">Run</button>
        </form>
        <small>Try <code>help</code>. Commands currently affect UI state only.</small>
      </section>
    </div>
  );
}

function ModulePlaceholder({ module }: { module: CommandCenterModule }) {
  return (
    <div className="module-placeholder panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">Module scaffold</span>
          <h1>{module.label}</h1>
        </div>
        <span className="placeholder-badge">not connected</span>
      </div>
      <p className="module-description">{module.description}</p>

      <div className="placeholder-section">
        <span className="eyebrow">Planned views</span>
        <div className="placeholder-grid">
          {module.plannedViews.map((view) => (
            <div className="placeholder-card" key={view}>
              <span>{view}</span>
              <small>Not available yet</small>
            </div>
          ))}
        </div>
      </div>

      <div className="placeholder-section">
        <span className="eyebrow">Planned controls</span>
        <div className="planned-actions">
          {module.plannedActions.map((action) => (
            <button type="button" disabled key={action}>{action}</button>
          ))}
        </div>
      </div>

      <div className="integration-note">
        <strong>Preview module</strong>
        <p>This module is a preview. Its controls will become available when connected to the simulation.</p>
      </div>
    </div>
  );
}
