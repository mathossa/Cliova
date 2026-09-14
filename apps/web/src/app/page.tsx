const sampleLines = [
  "> status",
  "World: not loaded",
  "Year: —",
  "",
  "> help",
  "create-world  Create a seeded simulation",
  "run <years>   Advance the simulation",
  "inspect       Inspect world state",
  "why           Explain a change",
];

export default function Home() {
  return (
    <main className="shell">
      <header className="topbar">
        <strong>CLIOVA</strong>
        <span>Simulation Lab · baseline</span>
      </header>
      <section className="workspace">
        <div className="terminal" aria-label="Simulation terminal placeholder">
          {sampleLines.map((line, index) => (
            <div key={`${index}-${line}`} className={line.startsWith(">") ? "prompt" : undefined}>
              {line || "\u00a0"}
            </div>
          ))}
          <div className="cursorline"><span>&gt;</span><span className="cursor" /></div>
        </div>
        <aside className="sidebar">
          <h2>World</h2>
          <dl>
            <dt>Status</dt><dd>Offline</dd>
            <dt>API</dt><dd>localhost:8000</dd>
            <dt>Tick</dt><dd>Manual</dd>
          </dl>
          <p>This deliberately minimal interface will become the first simulation/debug UX.</p>
        </aside>
      </section>
    </main>
  );
}
