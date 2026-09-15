"use client";

import { useEffect, useState } from "react";

import { cliovaApi, describeApiError, type LocalMapRequest } from "../../lib/api";
import { generateLocalMap, type LocalMapResult } from "./local-map-generator";
import { LocalMapView } from "./local-map-view";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; request: LocalMapRequest; result: LocalMapResult }
  | { status: "error"; message: string };

export function LocalMapLoader({ worldId, settlementId }: { worldId: string; settlementId: string }) {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    cliovaApi.getSettlementMap(worldId, settlementId).then(
      (request) => {
        if (cancelled) return;
        try {
          setState({ status: "ready", request, result: generateLocalMap(request) });
        } catch (error) {
          setState({ status: "error", message: describeApiError(error) });
        }
      },
      (error) => {
        if (!cancelled) setState({ status: "error", message: describeApiError(error) });
      },
    );
    return () => { cancelled = true; };
  }, [worldId, settlementId]);

  if (state.status === "ready") {
    return (
      <LocalMapView
        result={state.result}
        worldId={worldId}
        settlementName={state.request.settlement.name}
      />
    );
  }

  return (
    <main style={{ minHeight: "100vh", padding: "36px", background: "#131310", color: "#eee9dc" }}>
      <section role={state.status === "error" ? "alert" : "status"}>
        <p style={{ textTransform: "uppercase", opacity: 0.65, letterSpacing: "0.12em" }}>Cliova · Local map</p>
        <h1>{state.status === "loading" ? "Generating settlement…" : "Local map unavailable"}</h1>
        {state.status === "error" && <p>{state.message}</p>}
        <a href="/" style={{ color: "inherit" }}>← Back to world context</a>
      </section>
    </main>
  );
}
