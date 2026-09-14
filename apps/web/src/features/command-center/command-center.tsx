"use client";

import { FormEvent, useState } from "react";

import {
  assetPaths,
  mockWorld,
  modules,
  type CommandCenterModule,
  type ModuleId,
} from "./command-center.data";

const terminalHelp = "Available UI commands: help · status · inspect <entity> · why <event>. Simulation execution is not connected yet.";

export function CommandCenter() {
  const [activeModule, setActiveModule] = useState<ModuleId>("terminal");
  const [command, setCommand] = useState("");
  const [terminalLines, setTerminalLines] = useState<string[]>([
    "> status",
    `${mockWorld.connection}. Showing presentation placeholders.`,
  ]);
  const [selectedMarker, setSelectedMarker] = useState("northreach");

  const activeDefinition = modules.find((module) => module.id === activeModule) ?? modules[0];
  const marker = mockWorld.mapMarkers.find((item) => item.id === selectedMarker);

  function submitCommand(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = command.trim();
    if (!normalized) return;

    let response = "Command captured by the UI scaffold. The authoritative command/directive API is not connected yet.";
    if (normalized === "help") response = terminalHelp;
    if (normalized === "status") response = `${mockWorld.connection}. Mock snapshot year: ${mockWorld.year}.`;
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

        <div className="status-cluster" aria-label="World status placeholders">
          <StatusCell label="World" value={mockWorld.worldName} />
          <StatusCell label="Year" value={`${mockWorld.year} · ${mockWorld.season}`} />
          <StatusCell label="Next tick" value={mockWorld.nextTick} accent />
          <StatusCell label="Treasury" value={mockWorld.treasury} />
          <StatusCell label="Status" value={mockWorld.worldStatus} warning />
        </div>
        <button className="icon-button" type="button" aria-label="Settings placeholder">⚙</button>
      </header>

      <nav className="module-nav" aria-label="Cliova modules">
        {modules.map((module) => (
          <button
            key={module.id}
            type="button"
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
              command={command}
              setCommand={setCommand}
              terminalLines={terminalLines}
              submitCommand={submitCommand}
              selectedLabel={marker?.label ?? mockWorld.selectedRegion.name}
            />
          ) : (
            <ModulePlaceholder module={activeDefinition} />
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
                <button type="button">Layers</button>
                <button type="button">Filter</button>
                <button type="button" aria-label="Zoom in">+</button>
                <button type="button" aria-label="Zoom out">−</button>
              </div>
            </div>

            <div
              className="map-canvas"
              style={{
                backgroundImage: `linear-gradient(180deg, rgba(8, 14, 19, .08), rgba(8, 14, 19, .28)), url(${assetPaths.worldMap})`,
              }}
            >
              <div className="map-fallback-grid" aria-hidden="true" />
              {mockWorld.mapMarkers.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`map-marker ${item.kind} ${selectedMarker === item.id ? "selected" : ""}`}
                  style={{ left: `${item.x}%`, top: `${item.y}%` }}
                  onClick={() => setSelectedMarker(item.id)}
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
                <strong>{marker?.label ?? "Northreach"}</strong>
                <small>MapLibre/data adapter placeholder</small>
              </div>
            </div>
          </div>

          <div className="dashboard-row">
            <div className="metrics-grid">
              {mockWorld.metrics.map((metric, index) => (
                <article className="metric-card panel" key={metric.label}>
                  <span className="eyebrow">{metric.label}</span>
                  <div className="metric-value-row">
                    <strong>{metric.value}</strong>
                    <span className={`tone-${metric.tone}`}>{metric.delta}</span>
                  </div>
                  <div className="sparkline" aria-hidden="true">
                    {[34, 47, 41, 60, 55, 72, 68].map((height, point) => (
                      <i key={point} style={{ height: `${Math.max(18, height - index * 3)}%` }} />
                    ))}
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
                {mockWorld.pressures.map((pressure) => (
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
        <span>Presentation scaffold · no simulation rules run in the browser</span>
        <span>API: {mockWorld.connection}</span>
      </footer>
    </main>
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

function TerminalWorkspace({
  command,
  setCommand,
  terminalLines,
  submitCommand,
  selectedLabel,
}: {
  command: string;
  setCommand: (value: string) => void;
  terminalLines: string[];
  submitCommand: (event: FormEvent<HTMLFormElement>) => void;
  selectedLabel: string;
}) {
  return (
    <div className="terminal-workspace">
      <section className="panel feed-panel">
        <div className="panel-heading compact">
          <div>
            <span className="eyebrow">Terminal / intel</span>
            <h2>World feed</h2>
          </div>
          <div className="feed-filters" aria-label="Feed filters placeholders">
            <button type="button" className="selected">All</button>
            <button type="button">State</button>
            <button type="button">Economy</button>
            <button type="button">Events</button>
          </div>
        </div>
        <div className="feed-list">
          {mockWorld.feed.map((item) => (
            <div className="feed-line" key={`${item.time}-${item.text}`}>
              <time>[{item.time}]</time>
              <span className={`tone-${item.tone}`}>{item.text}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="panel region-panel">
        <div className="panel-heading compact">
          <div>
            <span className="eyebrow">Selected context</span>
            <h2>{selectedLabel}</h2>
          </div>
          <span className="placeholder-badge">mock data</span>
        </div>
        <div className="region-summary">
          <div
            className="region-image"
            role="img"
            aria-label="Region artwork placeholder"
            style={{
              backgroundImage: `linear-gradient(180deg, rgba(8, 14, 19, .08), rgba(8, 14, 19, .2)), url(${assetPaths.regionPreview})`,
            }}
          >
            <span>asset placeholder</span>
          </div>
          <p>{mockWorld.selectedRegion.description}</p>
        </div>
        <dl className="region-stats">
          <div><dt>Population</dt><dd>{mockWorld.selectedRegion.population}</dd></div>
          <div><dt>Primary resource</dt><dd>{mockWorld.selectedRegion.primaryResource}</dd></div>
          <div><dt>Administration</dt><dd>{mockWorld.selectedRegion.administration}</dd></div>
          <div><dt>Stability</dt><dd>{mockWorld.selectedRegion.stability}</dd></div>
          <div><dt>Conditions</dt><dd>{mockWorld.selectedRegion.conditions}</dd></div>
        </dl>
      </section>

      <section className="terminal-console panel" aria-label="Terminal command placeholder">
        <div className="console-history">
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
              <small>Authoritative data adapter pending</small>
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
        <strong>Integration boundary</strong>
        <p>The final component should render contracts returned by FastAPI/application services. Do not recreate domain calculations in this module.</p>
      </div>
    </div>
  );
}
