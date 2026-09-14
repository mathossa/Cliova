"use client";

import { useEffect, useState } from "react";
import { CommandCenter } from "./command-center";
import { previewWorldClient } from "./command-center.client";
import type { WorldClient, WorldSnapshot } from "./command-center.types";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; world: WorldSnapshot }
  | { status: "empty" }
  | { status: "unavailable" };

export function CommandCenterLoader({ client = previewWorldClient }: { client?: WorldClient }) {
  const [attempt, setAttempt] = useState(0);
  return <LoadAttempt key={attempt} client={client} retry={() => setAttempt((value) => value + 1)} />;
}

function LoadAttempt({ client, retry }: { client: WorldClient; retry: () => void }) {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const world = await client.load();
        if (!cancelled) setState(world === null ? { status: "empty" } : { status: "ready", world });
      } catch {
        if (!cancelled) setState({ status: "unavailable" });
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [client]);

  if (state.status === "ready") return <CommandCenter world={state.world} />;
  return <WorldLoadStatus status={state.status} retry={retry} />;
}

export function WorldLoadStatus({ status, retry }: {
  status: "loading" | "empty" | "unavailable";
  retry?: () => void;
}) {
  const messages = {
    loading: ["Loading world", "Retrieving the world overview…"],
    empty: ["No world available", "There is no world snapshot to display yet."],
    unavailable: ["World unavailable", "The world could not be loaded. Try again in a moment."],
  };
  return (
    <main className="world-load-screen" aria-busy={status === "loading"}>
      <section className="panel" role={status === "unavailable" ? "alert" : "status"}>
        <span className="eyebrow">Cliova · Simulation Lab</span>
        <h1>{messages[status][0]}</h1>
        <p>{messages[status][1]}</p>
        {status !== "loading" && retry && <button type="button" onClick={retry}>Try again</button>}
      </section>
    </main>
  );
}
