import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import type {
  CliovaApi,
  DirectiveListResponse,
  DirectiveSubmissionRequest,
  HistoryResponse,
  ManualTickResponse,
  QueuedDirective,
  RegionStatusResponse,
  WorldListResponse,
  WorldSummary,
} from "../../lib/api";
import { CommandCenter } from "./command-center";
import { LiveCommandCenterClient } from "./command-center.client";
import { WorldLoadStatus } from "./command-center-loader";
import { DirectivesPanel } from "./directives-panel";
import { toWorldSnapshot, type CommandCenterBundle } from "./command-center.view";

const WORLD_ID = "11111111-1111-4111-8111-111111111111";
const REGION_ID = "22222222-2222-4222-8222-222222222222";
const SOCIETY_ID = "33333333-3333-4333-8333-333333333333";
const EVENT_ID = "44444444-4444-4444-8444-444444444444";
const CAUSE_ID = "55555555-5555-4555-8555-555555555555";
const DIRECTIVE_ID = "66666666-6666-4666-8666-666666666666";

const summary: WorldSummary = {
  id: WORLD_ID,
  tick: 7,
  year: 1207,
  versions: {
    contract_version: "v1",
    world_schema_version: 1,
    simulation_version: 1,
    rng_algorithm: "pcg64",
  },
  region_count: 1,
  population_total: 4200,
  food_shortage_severity: 0.25,
  societies: [
    {
      subject: { kind: "society", id: SOCIETY_ID },
      region_id: REGION_ID,
      population: 4200,
      food: {
        food_security: 0.72,
        production: 3900,
        demand: 4100,
        stockpile: 500,
        deficit: 200,
        shortage_severity: 0.25,
      },
      governance: {
        legitimacy: 0.64,
        execution_capacity: 0.58,
        internal_resistance: 0.19,
      },
    },
  ],
  pressures: [
    {
      id: "77777777-7777-4777-8777-777777777777",
      key: "food_shortage",
      region_id: REGION_ID,
      subject: { kind: "society", id: SOCIETY_ID },
      intensity: 0.42,
      milestone: "elevated",
      age_ticks: 3,
      cause_event_ids: [CAUSE_ID],
    },
  ],
};

const regions: RegionStatusResponse = {
  world_id: WORLD_ID,
  tick: 7,
  regions: [
    {
      id: REGION_ID,
      key: "northreach",
      terrain: "highlands",
      biome: "temperate_grassland",
      habitability: 0.67,
      water_access: 0.61,
      climate_pressure: 0.14,
      population: 4200,
      food: summary.societies[0]!.food,
      pressures: summary.pressures,
    },
  ],
};

const history: HistoryResponse = {
  world_id: WORLD_ID,
  events: [
    {
      id: EVENT_ID,
      tick: 7,
      year: 1207,
      source: "economy",
      kind: "food_shortage",
      reason: "Food demand exceeded current production.",
      subjects: [{ kind: "society", id: SOCIETY_ID }],
      cause_event_ids: [CAUSE_ID],
    },
  ],
};

const directives: DirectiveListResponse = {
  world_id: WORLD_ID,
  pending: [
    {
      queue_id: 4,
      submitted_tick: 7,
      author: "command-center",
      target: { kind: "society", id: SOCIETY_ID },
      intent: "strengthen_food_reserves",
      priority: "normal",
    },
  ],
  directives: [],
};

const bundle: CommandCenterBundle = { summary, regions, history, directives };

const noOpActions = {
  selectWorld: async () => {},
  refresh: async () => {},
  submitDirective: async () => {},
  advanceDevelopmentTick: async () => {},
};

test("Command Center renders authoritative summary and history without demo fallback", () => {
  const world = toWorldSnapshot(bundle);
  const html = renderToStaticMarkup(
    <CommandCenter
      world={world}
      worlds={[{ id: WORLD_ID, tick: 7, year: 1207, region_count: 1, society_count: 1, population_total: 4200 }]}
      actions={noOpActions}
    />,
  );

  assert.match(html, /1207/);
  assert.match(html, /4200|4,200/);
  assert.match(html, /Food Demand Exceeded Current Production|Food demand exceeded current production/);
  assert.match(html, new RegExp(EVENT_ID));
  assert.match(html, /1 causal link/);
  assert.doesNotMatch(html, /Prototype World/);
  assert.doesNotMatch(html, /2142/);
  assert.doesNotMatch(html, /2\.43M/);
  assert.doesNotMatch(html, /Showing presentation placeholders/);
});

test("loading, empty and backend failure states are explicit", () => {
  const loading = renderToStaticMarkup(<WorldLoadStatus status="loading" />);
  const empty = renderToStaticMarkup(<WorldLoadStatus status="empty" createWorld={async () => {}} />);
  const failed = renderToStaticMarkup(<WorldLoadStatus status="unavailable" message="Persistence operation failed." />);

  assert.match(loading, /Retrieving authoritative simulation status/);
  assert.match(empty, /No development world/);
  assert.match(empty, /Create world/);
  assert.match(failed, /Backend unavailable/);
  assert.match(failed, /Persistence operation failed/);
  assert.doesNotMatch(failed, /Prototype World/);
});

test("directive panel renders pending authoritative queue state", () => {
  const world = toWorldSnapshot(bundle);
  const html = renderToStaticMarkup(<DirectivesPanel world={world} onSubmit={async () => {}} />);

  assert.match(html, /Strengthen food reserves/);
  assert.match(html, /queued/);
  assert.match(html, /command-center/);
  assert.match(html, /normal/);
});

test("directive submission and manual tick revalidate lifecycle state", async () => {
  let tick = 7;
  let pending: QueuedDirective[] = [];
  let accepted = false;
  let expectedTickSeen: number | null = null;

  const api: CliovaApi = {
    async listWorlds(): Promise<WorldListResponse> {
      return {
        worlds: [{ id: WORLD_ID, tick, year: 1200 + tick, region_count: 1, society_count: 1, population_total: 4200 }],
      };
    },
    async createDevelopmentWorld() {
      return { ...summary, tick, year: 1200 + tick };
    },
    async getWorld() {
      return { ...summary, tick, year: 1200 + tick };
    },
    async getRegions() {
      return { ...regions, tick };
    },
    async getHistory() {
      return history;
    },
    async getDirectives(): Promise<DirectiveListResponse> {
      return {
        world_id: WORLD_ID,
        pending,
        directives: accepted ? [{
          id: DIRECTIVE_ID,
          author: "command-center",
          target: { kind: "society", id: SOCIETY_ID },
          intent: "strengthen_food_reserves",
          priority: "high",
          submitted_tick: 7,
          submission_event_id: EVENT_ID,
          status: "accepted",
          progress: 0.2,
        }] : [],
      };
    },
    async submitDirective(_worldId: string, request: DirectiveSubmissionRequest): Promise<QueuedDirective> {
      const queued: QueuedDirective = {
        queue_id: 8,
        submitted_tick: tick,
        author: request.author,
        target: request.target,
        intent: request.intent ?? "strengthen_food_reserves",
        priority: request.priority ?? "normal",
      };
      pending = [queued];
      return queued;
    },
    async advanceDevelopmentTick(_worldId: string, expectedTick: number): Promise<ManualTickResponse> {
      expectedTickSeen = expectedTick;
      tick += 1;
      pending = [];
      accepted = true;
      return {
        world: { ...summary, tick, year: 1200 + tick },
        event_ids: [EVENT_ID],
      };
    },
  };

  const client = new LiveCommandCenterClient(api);
  const initial = await client.load();
  assert.equal(initial.kind, "ready");
  if (initial.kind !== "ready") return;
  assert.equal(initial.data.directives.pending.length, 0);

  const afterSubmit = await client.submitDirective(WORLD_ID, {
    author: "command-center",
    target: { kind: "society", id: SOCIETY_ID },
    intent: "strengthen_food_reserves",
    priority: "high",
  });
  assert.equal(afterSubmit.kind, "ready");
  if (afterSubmit.kind !== "ready") return;
  assert.equal(afterSubmit.data.directives.pending[0]?.priority, "high");

  const afterTick = await client.advanceDevelopmentTick(WORLD_ID, 7);
  assert.equal(expectedTickSeen, 7);
  assert.equal(afterTick.kind, "ready");
  if (afterTick.kind !== "ready") return;
  assert.equal(afterTick.data.summary.tick, 8);
  assert.equal(afterTick.data.directives.pending.length, 0);
  assert.equal(afterTick.data.directives.directives[0]?.status, "accepted");
});
