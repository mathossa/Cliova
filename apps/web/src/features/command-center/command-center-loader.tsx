"use client";

import { FormEvent, useEffect, useState } from "react";
import { describeApiError, type DirectiveSubmissionRequest } from "../../lib/api";
import { CommandCenter } from "./command-center";
import {
  liveCommandCenterClient,
  type CommandCenterClient,
  type CommandCenterLoadResult,
} from "./command-center.client";
import type { CommandCenterProps } from "./command-center.types";
import { toWorldSnapshot } from "./command-center.view";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; props: Omit<CommandCenterProps, "actions"> }
  | { status: "empty" }
  | { status: "missing"; worldId: string }
  | { status: "unavailable"; message: string };

export function CommandCenterLoader({ client = liveCommandCenterClient }: { client?: CommandCenterClient }) {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    client.load().then(
      (result) => { if (!cancelled) setState(resolveLoadResult(result)); },
      (error) => {
        if (!cancelled) setState({ status: "unavailable", message: describeApiError(error) });
      },
    );
    return () => { cancelled = true; };
  }, [client]);

  async function selectWorld(worldId: string) {
    setState({ status: "loading" });
    try {
      setState(resolveLoadResult(await client.load(worldId)));
    } catch (error) {
      setState({ status: "unavailable", message: describeApiError(error) });
    }
  }

  async function retry() {
    setState({ status: "loading" });
    try {
      setState(resolveLoadResult(await client.load()));
    } catch (error) {
      setState({ status: "unavailable", message: describeApiError(error) });
    }
  }

  async function createWorld(seed: number) {
    const result = await client.createWorld({ seed });
    setState(resolveLoadResult(result));
  }

  if (state.status === "ready") {
    const worldId = state.props.world.id;
    const actions: CommandCenterProps["actions"] = {
      selectWorld,
      refresh: async () => {
        const result = await client.load(worldId);
        setState(resolveLoadResult(result));
      },
      submitDirective: async (request: DirectiveSubmissionRequest) => {
        const result = await client.submitDirective(worldId, request);
        setState(resolveLoadResult(result));
      },
      advanceDevelopmentTick: async () => {
        const result = await client.advanceDevelopmentTick(worldId, state.props.world.tick);
        setState(resolveLoadResult(result));
      },
    };
    return <CommandCenter {...state.props} actions={actions} />;
  }

  return (
    <WorldLoadStatus
      status={state.status}
      message={state.status === "unavailable" ? state.message : undefined}
      missingWorldId={state.status === "missing" ? state.worldId : undefined}
      retry={state.status === "loading" ? undefined : retry}
      createWorld={state.status === "empty" ? createWorld : undefined}
    />
  );
}

export function resolveLoadResult(result: CommandCenterLoadResult): LoadState {
  if (result.kind === "empty") return { status: "empty" };
  if (result.kind === "missing") return { status: "missing", worldId: result.worldId };
  return {
    status: "ready",
    props: {
      world: toWorldSnapshot(result.data),
      worlds: result.worlds,
    },
  };
}

export function WorldLoadStatus({
  status,
  message,
  missingWorldId,
  retry,
  createWorld,
}: {
  status: "loading" | "empty" | "missing" | "unavailable";
  message?: string;
  missingWorldId?: string;
  retry?: () => void | Promise<void>;
  createWorld?: (seed: number) => Promise<void>;
}) {
  const [seed, setSeed] = useState("1");
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const messages = {
    loading: ["Loading world", "Retrieving authoritative simulation status…"],
    empty: ["No development world", "Create a seeded development world to start the Simulation Lab."],
    missing: ["World missing", `The selected world ${missingWorldId ?? ""} is no longer available.`],
    unavailable: ["Backend unavailable", message ?? "The Cliova API could not be reached."],
  } as const;

  async function submitCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsedSeed = Number(seed);
    if (!Number.isInteger(parsedSeed)) {
      setCreateError("Seed must be an integer.");
      return;
    }
    if (!createWorld) return;
    setCreateError(null);
    setCreating(true);
    try {
      await createWorld(parsedSeed);
    } catch (error) {
      setCreateError(describeApiError(error));
    } finally {
      setCreating(false);
    }
  }

  return (
    <main className="world-load-screen" aria-busy={status === "loading"}>
      <section className="panel" role={status === "unavailable" ? "alert" : "status"}>
        <span className="eyebrow">Cliova · Simulation Lab</span>
        <h1>{messages[status][0]}</h1>
        <p>{messages[status][1]}</p>
        {status === "empty" && createWorld && (
          <form className="create-world-form" onSubmit={submitCreate}>
            <label>
              Development seed
              <input value={seed} onChange={(event) => setSeed(event.target.value)} inputMode="numeric" />
            </label>
            <button type="submit" disabled={creating}>{creating ? "Creating…" : "Create world"}</button>
          </form>
        )}
        {createError && <p className="action-error" role="alert">{createError}</p>}
        {status !== "loading" && retry && <button type="button" onClick={() => void retry()}>Try again</button>}
      </section>
    </main>
  );
}
