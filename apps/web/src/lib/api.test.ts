import assert from "node:assert/strict";
import test from "node:test";
import {
  CliovaApiError,
  HttpCliovaApiClient,
  type WorldListResponse,
} from "./api";

const WORLD_ID = "11111111-1111-4111-8111-111111111111";
const SOCIETY_ID = "22222222-2222-4222-8222-222222222222";

const worlds: WorldListResponse = {
  worlds: [
    {
      id: WORLD_ID,
      tick: 7,
      year: 1207,
      region_count: 1,
      society_count: 1,
      population_total: 4200,
    },
  ],
};

test("API client returns typed success payloads", async () => {
  const client = new HttpCliovaApiClient(async (input, init) => {
    assert.equal(input, "/api/v1/worlds");
    assert.equal(init?.cache, "no-store");
    return jsonResponse(worlds);
  });

  assert.deepEqual(await client.listWorlds(), worlds);
});

test("API client preserves structured backend validation errors", async () => {
  const client = new HttpCliovaApiClient(async () => jsonResponse(
    {
      error: {
        code: "invalid_directive",
        message: "Directive target is not an active society/polity.",
        details: [{ location: "body.target.id", message: "Invalid target", type: "value_error" }],
      },
    },
    422,
  ));

  await assert.rejects(
    () => client.submitDirective(WORLD_ID, {
      author: "test",
      target: { kind: "society", id: SOCIETY_ID },
      intent: "strengthen_food_reserves",
      priority: "normal",
    }),
    (error: unknown) => {
      assert.ok(error instanceof CliovaApiError);
      assert.equal(error.status, 422);
      assert.equal(error.code, "invalid_directive");
      assert.equal(error.details[0]?.location, "body.target.id");
      return true;
    },
  );
});

test("directive and manual tick requests use the authoritative v1 shapes", async () => {
  const requests: Array<{ input: string; init?: RequestInit }> = [];
  const client = new HttpCliovaApiClient(async (input, init) => {
    requests.push({ input, init });
    if (input.endsWith("/directives")) {
      return jsonResponse({
        queue_id: 9,
        submitted_tick: 7,
        author: "command-center",
        target: { kind: "society", id: SOCIETY_ID },
        intent: "strengthen_food_reserves",
        priority: "high",
      }, 202);
    }
    return jsonResponse({
      world: {
        id: WORLD_ID,
        tick: 8,
        year: 1208,
        versions: { contract_version: "v1", world_schema_version: 1, simulation_version: 1, rng_algorithm: "pcg64" },
        region_count: 1,
        population_total: 4200,
        food_shortage_severity: 0.2,
        societies: [],
        pressures: [],
      },
      event_ids: [],
    });
  });

  await client.submitDirective(WORLD_ID, {
    author: "command-center",
    target: { kind: "society", id: SOCIETY_ID },
    intent: "strengthen_food_reserves",
    priority: "high",
  });
  await client.advanceDevelopmentTick(WORLD_ID, 7);

  assert.equal(requests[0]?.input, `/api/v1/worlds/${WORLD_ID}/directives`);
  assert.deepEqual(JSON.parse(String(requests[0]?.init?.body)), {
    author: "command-center",
    target: { kind: "society", id: SOCIETY_ID },
    intent: "strengthen_food_reserves",
    priority: "high",
  });
  assert.equal(requests[1]?.input, `/api/v1/dev/worlds/${WORLD_ID}/ticks`);
  assert.deepEqual(JSON.parse(String(requests[1]?.init?.body)), { expected_tick: 7 });
});

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
