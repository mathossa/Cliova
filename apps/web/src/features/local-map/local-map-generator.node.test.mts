import assert from "node:assert/strict";
import test from "node:test";

import type { LocalMapRequest } from "../../lib/api.ts";
import { generateLocalMap } from "./local-map-generator.ts";

const physicalContext: LocalMapRequest["physical_context"] = {
  terrain: "plain",
  biome: "temperate",
  surface: "land",
  water_access: 0.45,
  coast_fraction: 0,
  mean_elevation: 0.2,
  region_centroid_x: null,
  region_centroid_y: null,
  world_extent_width: null,
  world_extent_height: null,
};

function request(renderer: LocalMapRequest["renderer"] = "settlemaker"): LocalMapRequest {
  const camp = renderer === "cliova_camp";
  return {
    contract_version: "v1",
    world_id: "00000000-0000-4000-8000-000000000001",
    settlement_id: camp
      ? "00000000-0000-4000-8000-000000000002"
      : "00000000-0000-4000-8000-000000000003",
    layout_seed: 72631491,
    generation_version: "local-map-v1",
    render_version: "local-map-render-v1",
    renderer,
    renderer_version: camp ? "cliova-camp-v1" : "3.0.1",
    state_fingerprint: "fixture-fingerprint",
    settlement: {
      id: camp
        ? "00000000-0000-4000-8000-000000000002"
        : "00000000-0000-4000-8000-000000000003",
      key: camp ? "seasonal-camp" : "river-haven",
      name: camp ? "Seasonal Camp" : "River Haven",
      region_id: "00000000-0000-4000-8000-000000000004",
      associated_subject: null,
      established_year: 12,
      population_estimate: camp ? 120 : 700,
      archetype: camp ? "seasonal_camp" : "permanent",
      status: camp ? "dormant" : "active",
    },
    physical_context: { ...physicalContext },
    authoritative_structures: camp
      ? [
          {
            id: "00000000-0000-4000-8000-000000000010",
            key: "camp-storage",
            definition_id: "storage",
            display_name: "Storage",
            established_year: 12,
            status: "active",
          },
          {
            id: "00000000-0000-4000-8000-000000000011",
            key: "camp-enclosure",
            definition_id: "livestock_enclosure",
            display_name: "Livestock enclosure",
            established_year: 12,
            status: "active",
          },
        ]
      : [
          {
            id: "00000000-0000-4000-8000-000000000020",
            key: "river-storage",
            definition_id: "storage",
            display_name: "Storage",
            established_year: 12,
            status: "active",
          },
          {
            id: "00000000-0000-4000-8000-000000000021",
            key: "river-workshop",
            definition_id: "workshop",
            display_name: "Workshop",
            established_year: 13,
            status: "active",
          },
        ],
    visual_style_key: null,
  };
}

test("permanent settlement output is deterministic and authority-tagged", () => {
  const first = generateLocalMap(request("settlemaker"));
  const second = generateLocalMap(request("settlemaker"));

  assert.equal(first.svg, second.svg);
  assert.deepEqual(first.features, second.features);
  assert.deepEqual(first.structure_feature_mappings, second.structure_feature_mappings);
  assert.ok(first.svg.startsWith("<svg"));
  assert.ok(first.features.some((feature) => feature.authority === "visual_fabric"));
  assert.ok(first.features.some((feature) => feature.authority === "generated_infrastructure_geometry"));
  assert.equal(first.structure_feature_mappings.length, 2);
  assert.ok(first.structure_feature_mappings.every((mapping) => mapping.status === "mapped" || mapping.message));
  assert.ok(first.features.some((feature) => feature.authority === "authoritative_structure" && feature.structure?.definition_id === "storage"));
});

test("seasonal camp uses distinct small deterministic renderer", () => {
  const first = generateLocalMap(request("cliova_camp"));
  const second = generateLocalMap(request("cliova_camp"));

  assert.equal(first.svg, second.svg);
  assert.deepEqual(first.features, second.features);
  assert.equal(first.renderer, "cliova_camp");
  assert.ok(first.features.some((feature) => feature.source_layer === "shelter"));
  assert.ok(first.features.every((feature) => feature.properties.permanence !== "permanent"));
  assert.ok(first.structure_feature_mappings.every((mapping) => mapping.status === "mapped"));
});

test("impossible authoritative placement fails explicitly instead of disappearing", () => {
  const value = request("cliova_camp");
  value.physical_context.water_access = 0;
  value.authoritative_structures = [
    {
      id: "00000000-0000-4000-8000-000000000099",
      key: "dry-harbour",
      definition_id: "harbour_infrastructure",
      display_name: "Harbour infrastructure",
      established_year: 20,
      status: "active",
    },
  ];

  const result = generateLocalMap(value);
  assert.deepEqual(result.structure_feature_mappings.map((mapping) => mapping.status), ["failed"]);
  assert.ok(result.issues.some((issue) => issue.code === "harbour_without_water"));
  assert.equal(result.features.some((feature) => feature.structure?.id === value.authoritative_structures[0].id), false);
});
