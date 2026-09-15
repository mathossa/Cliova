import { generateSettlement } from "settlemaker";
import type { AzgaarBurgInput } from "settlemaker";
import type { LocalMapRequest, StructureProjection } from "../../lib/api";

export type LocalMapAuthority =
  | "authoritative_structure"
  | "visual_fabric"
  | "generated_infrastructure_geometry"
  | "natural_context";

export type LocalPoint = [number, number];
export type LocalGeometry =
  | { type: "Point"; coordinates: LocalPoint }
  | { type: "LineString"; coordinates: LocalPoint[] }
  | { type: "Polygon"; coordinates: LocalPoint[][] }
  | { type: "MultiPolygon"; coordinates: LocalPoint[][][] };

export type LocalMapFeature = {
  feature_id: string;
  authority: LocalMapAuthority;
  source_layer: string;
  source_feature_id: string | null;
  geometry: LocalGeometry;
  structure: StructureProjection | null;
  properties: Record<string, string | number | boolean | null>;
};

export type LocalMapBounds = {
  min_x: number;
  min_y: number;
  max_x: number;
  max_y: number;
};

export type LocalMapIssue = {
  severity: "warning" | "error";
  code: string;
  message: string;
  structure_id: string | null;
};

export type StructureFeatureMapping = {
  structure_id: string;
  status: "mapped" | "failed";
  feature_id: string | null;
  message: string | null;
};

export type LocalMapResult = {
  settlement_id: string;
  generation_version: string;
  render_version: string;
  layout_seed: number;
  state_fingerprint: string;
  renderer: "settlemaker" | "cliova_camp";
  renderer_version: string;
  bounds: LocalMapBounds;
  svg: string;
  features: LocalMapFeature[];
  structure_feature_mappings: StructureFeatureMapping[];
  issues: LocalMapIssue[];
};

type UpstreamFeature = {
  type?: unknown;
  properties?: Record<string, unknown> | null;
  geometry?: unknown;
};

type UpstreamFeatureCollection = {
  type?: unknown;
  features?: UpstreamFeature[];
};

const VISUAL_LAYERS = new Set(["ward", "building", "green", "field", "poi"]);
const INFRASTRUCTURE_LAYERS = new Set([
  "street",
  "wall",
  "tower",
  "entrance",
  "gate",
  "crossing",
  "junction",
  "pier",
]);

export function generateLocalMap(request: LocalMapRequest): LocalMapResult {
  return request.renderer === "settlemaker"
    ? generatePermanentSettlement(request)
    : generateCamp(request);
}

function generatePermanentSettlement(request: LocalMapRequest): LocalMapResult {
  const structureTypes = new Set(request.authoritative_structures.map((item) => item.definition_id));
  const coastal = request.physical_context.coast_fraction > 0 || request.physical_context.surface === "mixed";
  const harbourRequested = structureTypes.has("harbour_infrastructure");
  const oceanBearing = coastal ? request.layout_seed % 360 : undefined;
  const burg: AzgaarBurgInput = {
    name: request.settlement.name,
    population: Math.max(1, request.settlement.population_estimate),
    port: harbourRequested && coastal,
    citadel: false,
    walls: structureTypes.has("fortification"),
    plaza: structureTypes.has("market"),
    temple: structureTypes.has("ritual_structure"),
    shanty: false,
    capital: structureTypes.has("administrative_structure"),
    trade: structureTypes.has("market"),
    biome: toSettlemakerBiome(request.physical_context.biome),
    oceanBearing,
    harbourSize: request.settlement.population_estimate >= 10_000 ? "large" : "small",
  };

  const generated = generateSettlement(burg, { seed: request.layout_seed });
  const normalized = normalizeGeoJson(generated.geojson as UpstreamFeatureCollection);
  const mapped = mapAuthoritativeStructures(
    normalized,
    request.authoritative_structures,
    { coastal },
  );
  const issues: LocalMapIssue[] = [...mapped.issues];
  for (const flag of generated.degradedFlags) {
    issues.push({
      severity: "warning",
      code: `settlemaker_degraded_${flag}`,
      message: `Settlemaker could not realize requested presentation feature: ${flag}.`,
      structure_id: null,
    });
  }
  if (coastal) {
    issues.push({
      severity: "warning",
      code: "synthetic_coast_bearing",
      message: "Region state indicates a coast but no local coastline geometry exists; coast direction is deterministic presentation-only geometry.",
      structure_id: null,
    });
  }
  if (request.settlement.population_estimate < 1) {
    issues.push({
      severity: "warning",
      code: "population_visual_floor",
      message: "Renderer used a visual population floor of one; authoritative population was not changed.",
      structure_id: null,
    });
  }

  const features = [...normalized, ...mapped.authoritative].sort(compareFeatureId);
  return {
    settlement_id: request.settlement_id,
    generation_version: request.generation_version,
    render_version: request.render_version,
    layout_seed: request.layout_seed,
    state_fingerprint: request.state_fingerprint,
    renderer: request.renderer,
    renderer_version: request.renderer_version,
    bounds: boundsFor(features),
    svg: generated.svg,
    features,
    structure_feature_mappings: mapped.mappings,
    issues: issues.sort(compareIssue),
  };
}

function normalizeGeoJson(collection: UpstreamFeatureCollection): LocalMapFeature[] {
  const source = Array.isArray(collection.features) ? collection.features : [];
  const features: LocalMapFeature[] = [];
  source.forEach((feature, index) => {
    const geometry = normalizeGeometry(feature.geometry);
    if (geometry === null) return;
    const properties = primitiveProperties(feature.properties ?? {});
    const layer = typeof properties.layer === "string" ? properties.layer : "unknown";
    const sourceId = upstreamFeatureId(properties);
    const authority: LocalMapAuthority = layer === "water"
      ? "natural_context"
      : INFRASTRUCTURE_LAYERS.has(layer)
        ? "generated_infrastructure_geometry"
        : VISUAL_LAYERS.has(layer)
          ? "visual_fabric"
          : "visual_fabric";
    features.push({
      feature_id: `settlemaker:${layer}:${sourceId ?? index}`,
      authority,
      source_layer: layer,
      source_feature_id: sourceId,
      geometry,
      structure: null,
      properties,
    });
  });
  return features.sort(compareFeatureId);
}

function mapAuthoritativeStructures(
  features: LocalMapFeature[],
  structures: StructureProjection[],
  context: { coastal: boolean },
): {
  authoritative: LocalMapFeature[];
  mappings: StructureFeatureMapping[];
  issues: LocalMapIssue[];
} {
  const authoritative: LocalMapFeature[] = [];
  const mappings: StructureFeatureMapping[] = [];
  const issues: LocalMapIssue[] = [];
  const used = new Set<string>();
  const ordered = [...structures].sort(compareStructure);

  for (const structure of ordered) {
    if (structure.definition_id === "harbour_infrastructure" && !context.coastal) {
      mappings.push(failedMapping(structure, "Harbour infrastructure requires coastal/water context."));
      issues.push(structureIssue(structure, "harbour_without_water", "Harbour structure could not be placed because the region has no coastal context."));
      continue;
    }

    const candidates = candidatesForStructure(features, structure).filter((item) => !used.has(item.feature_id));
    const candidate = deterministicCandidate(candidates, structure.id);
    if (candidate === null) {
      const message = `No compatible generated geometry exists for ${structure.display_name}.`;
      mappings.push(failedMapping(structure, message));
      issues.push(structureIssue(structure, "authoritative_structure_unplaced", message));
      continue;
    }

    used.add(candidate.feature_id);
    const featureId = `structure:${structure.id}`;
    authoritative.push({
      feature_id: featureId,
      authority: "authoritative_structure",
      source_layer: candidate.source_layer,
      source_feature_id: candidate.source_feature_id,
      geometry: candidate.geometry,
      structure,
      properties: {
        definition_id: structure.definition_id,
        status: structure.status,
        established_year: structure.established_year,
      },
    });
    mappings.push({ structure_id: structure.id, status: "mapped", feature_id: featureId, message: null });
  }

  return { authoritative, mappings, issues };
}

function candidatesForStructure(features: LocalMapFeature[], structure: StructureProjection): LocalMapFeature[] {
  const byLayer = (layers: string[]) => features.filter((item) => layers.includes(item.source_layer));
  const poi = (kinds: string[]) => features.filter(
    (item) => item.source_layer === "poi" && typeof item.properties.kind === "string" && kinds.includes(item.properties.kind),
  );
  const linkedPoiBuildings = (kinds: string[]) => {
    const buildingIds = new Set(
      poi(kinds)
        .map((item) => item.properties.building_id)
        .filter((value): value is string => typeof value === "string"),
    );
    return features.filter(
      (item) => item.source_layer === "building" && item.source_feature_id !== null && buildingIds.has(item.source_feature_id),
    );
  };
  const semanticThenFallback = (kinds: string[], fallback: string[]) => [
    ...linkedPoiBuildings(kinds),
    ...poi(kinds),
    ...byLayer(fallback),
  ];

  switch (structure.definition_id) {
    case "storage": return semanticThenFallback(["warehouse"], ["building"]);
    case "workshop": return semanticThenFallback(["smithy"], ["building"]);
    case "market": return semanticThenFallback(["market"], ["ward", "building"]);
    case "ritual_structure": return semanticThenFallback(["temple", "cathedral", "chapel"], ["building"]);
    case "water_infrastructure": return [...poi(["well"]), ...byLayer(["building"] )];
    case "livestock_enclosure": return semanticThenFallback(["stable"], ["field", "green", "building"]);
    case "fortification": return byLayer(["wall"]);
    case "harbour_infrastructure": return byLayer(["pier"]);
    case "transport_infrastructure": return byLayer(["entrance", "gate", "street"]);
    case "administrative_structure": return semanticThenFallback(["guildhall", "guardhouse"], ["building"]);
    default: return [];
  }
}

function deterministicCandidate(candidates: LocalMapFeature[], structureId: string): LocalMapFeature | null {
  if (candidates.length === 0) return null;
  return [...candidates]
    .sort((a, b) => {
      const ah = stableHash(`${structureId}:${a.feature_id}`);
      const bh = stableHash(`${structureId}:${b.feature_id}`);
      return ah - bh || a.feature_id.localeCompare(b.feature_id);
    })[0] ?? null;
}

function generateCamp(request: LocalMapRequest): LocalMapResult {
  const population = Math.max(1, request.settlement.population_estimate);
  const radius = clamp(38 + Math.sqrt(population) * 4.5, 46, 150);
  const tentCount = clamp(Math.ceil(population / 8), 6, 36);
  const rotation = (request.layout_seed % 360) * Math.PI / 180;
  const features: LocalMapFeature[] = [];

  for (let index = 0; index < tentCount; index += 1) {
    const angle = rotation + (Math.PI * 2 * index) / tentCount;
    const ring = radius * (0.45 + 0.16 * ((stableHash(`${request.layout_seed}:tent:${index}`) % 1000) / 1000));
    const cx = Math.cos(angle) * ring;
    const cy = Math.sin(angle) * ring;
    const size = 4.5 + (index % 3);
    features.push({
      feature_id: `camp:tent:${index}`,
      authority: "visual_fabric",
      source_layer: "shelter",
      source_feature_id: null,
      geometry: {
        type: "Polygon",
        coordinates: [[
          [cx, cy - size],
          [cx - size * 0.85, cy + size * 0.65],
          [cx + size * 0.85, cy + size * 0.65],
          [cx, cy - size],
        ]],
      },
      structure: null,
      properties: { kind: "tent", permanence: "temporary" },
    });
  }

  features.push({
    feature_id: "camp:hearth",
    authority: "visual_fabric",
    source_layer: "communal_area",
    source_feature_id: null,
    geometry: { type: "Point", coordinates: [0, 0] },
    structure: null,
    properties: { kind: "hearth" },
  });
  for (let index = 0; index < 3; index += 1) {
    const angle = rotation + (Math.PI * 2 * index) / 3;
    features.push({
      feature_id: `camp:path:${index}`,
      authority: "generated_infrastructure_geometry",
      source_layer: "path",
      source_feature_id: null,
      geometry: {
        type: "LineString",
        coordinates: [[0, 0], [Math.cos(angle) * radius, Math.sin(angle) * radius]],
      },
      structure: null,
      properties: { kind: "informal_path", permanence: "temporary" },
    });
  }

  if (request.physical_context.water_access > 0.35) {
    const waterY = radius * 0.86;
    features.push({
      feature_id: "camp:natural:water-edge",
      authority: "natural_context",
      source_layer: "water",
      source_feature_id: null,
      geometry: {
        type: "LineString",
        coordinates: [[-radius, waterY], [radius, waterY]],
      },
      structure: null,
      properties: { kind: "water_access" },
    });
  }

  const placed = placeCampStructures(features, request.authoritative_structures, radius, request);
  const allFeatures = [...features, ...placed.features].sort(compareFeatureId);
  const bounds = boundsFor(allFeatures);
  return {
    settlement_id: request.settlement_id,
    generation_version: request.generation_version,
    render_version: request.render_version,
    layout_seed: request.layout_seed,
    state_fingerprint: request.state_fingerprint,
    renderer: request.renderer,
    renderer_version: request.renderer_version,
    bounds,
    svg: renderCampSvg(allFeatures, bounds, request),
    features: allFeatures,
    structure_feature_mappings: placed.mappings,
    issues: placed.issues.sort(compareIssue),
  };
}

function placeCampStructures(
  baseFeatures: LocalMapFeature[],
  structures: StructureProjection[],
  radius: number,
  request: LocalMapRequest,
): { features: LocalMapFeature[]; mappings: StructureFeatureMapping[]; issues: LocalMapIssue[] } {
  const features: LocalMapFeature[] = [];
  const mappings: StructureFeatureMapping[] = [];
  const issues: LocalMapIssue[] = [];
  const occupied: LocalMapBounds[] = [];

  for (const structure of [...structures].sort(compareStructure)) {
    if (structure.definition_id === "harbour_infrastructure" && request.physical_context.water_access <= 0.35) {
      const message = "Harbour infrastructure requires water access in local physical context.";
      mappings.push(failedMapping(structure, message));
      issues.push(structureIssue(structure, "harbour_without_water", message));
      continue;
    }

    let geometry: LocalGeometry | null = null;
    for (let attempt = 0; attempt < 8 && geometry === null; attempt += 1) {
      const slot = (stableHash(structure.id) + attempt * 5) % 24;
      const angle = ((slot / 24) * Math.PI * 2) + ((request.layout_seed % 17) / 17) * 0.25;
      const distance = radius * (structure.definition_id === "livestock_enclosure" ? 0.72 : 0.34 + (slot % 3) * 0.09);
      const cx = Math.cos(angle) * distance;
      let cy = Math.sin(angle) * distance;
      if (structure.definition_id === "harbour_infrastructure") cy = radius * 0.82;
      const width = structure.definition_id === "livestock_enclosure" ? 24 : 12;
      const height = structure.definition_id === "livestock_enclosure" ? 18 : 10;
      const candidate: LocalGeometry = structure.definition_id === "transport_infrastructure"
        ? { type: "LineString", coordinates: [[0, 0], [cx, cy], [cx * 1.6, cy * 1.6]] }
        : structure.definition_id === "fortification"
          ? campFortification(radius * 0.78)
          : rectangle(cx, cy, width, height);
      const candidateBounds = geometryBounds(candidate);
      if (structure.definition_id === "transport_infrastructure" || structure.definition_id === "fortification" || !occupied.some((box) => intersects(box, candidateBounds))) {
        geometry = candidate;
        if (structure.definition_id !== "transport_infrastructure" && structure.definition_id !== "fortification") occupied.push(candidateBounds);
      }
    }

    if (geometry === null) {
      const message = `No collision-free camp presentation slot exists for ${structure.display_name}.`;
      mappings.push(failedMapping(structure, message));
      issues.push(structureIssue(structure, "authoritative_structure_collision", message));
      continue;
    }

    const featureId = `structure:${structure.id}`;
    features.push({
      feature_id: featureId,
      authority: "authoritative_structure",
      source_layer: campStructureLayer(structure.definition_id),
      source_feature_id: null,
      geometry,
      structure,
      properties: {
        definition_id: structure.definition_id,
        status: structure.status,
        established_year: structure.established_year,
        permanence: "authoritative_structure_only",
      },
    });
    mappings.push({ structure_id: structure.id, status: "mapped", feature_id: featureId, message: null });
  }

  // Keep the function's dependency on generated camp fabric explicit but
  // presentation-only; no base feature is transformed into simulation state.
  void baseFeatures;
  return { features, mappings, issues };
}

function campStructureLayer(definitionId: string): string {
  if (definitionId === "livestock_enclosure") return "enclosure";
  if (definitionId === "fortification") return "fortification";
  if (definitionId === "harbour_infrastructure") return "water_access_structure";
  if (definitionId === "transport_infrastructure") return "route";
  return "structure_footprint";
}

function campFortification(radius: number): LocalGeometry {
  const coordinates: LocalPoint[] = [];
  for (let index = 0; index <= 20; index += 1) {
    const angle = (Math.PI * 2 * index) / 20;
    coordinates.push([Math.cos(angle) * radius, Math.sin(angle) * radius]);
  }
  return { type: "LineString", coordinates };
}

function rectangle(cx: number, cy: number, width: number, height: number): LocalGeometry {
  const left = cx - width / 2;
  const right = cx + width / 2;
  const top = cy - height / 2;
  const bottom = cy + height / 2;
  return {
    type: "Polygon",
    coordinates: [[[left, top], [right, top], [right, bottom], [left, bottom], [left, top]]],
  };
}

function renderCampSvg(features: LocalMapFeature[], bounds: LocalMapBounds, request: LocalMapRequest): string {
  const padding = 12;
  const minX = bounds.min_x - padding;
  const minY = bounds.min_y - padding;
  const width = Math.max(1, bounds.max_x - bounds.min_x + padding * 2);
  const height = Math.max(1, bounds.max_y - bounds.min_y + padding * 2);
  const body = features.map((feature) => geometrySvg(feature)).join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${n(minX)} ${n(minY)} ${n(width)} ${n(height)}" data-settlement-id="${escapeXml(request.settlement_id)}" data-generation-version="${escapeXml(request.generation_version)}"><style>.visual_fabric{fill:#d8ccb0;stroke:#746958;stroke-width:1}.generated_infrastructure_geometry{fill:none;stroke:#87755f;stroke-width:2}.natural_context{fill:none;stroke:#6f8d93;stroke-width:3}.authoritative_structure{fill:#b89c68;stroke:#312b24;stroke-width:2}</style>${body}</svg>`;
}

function geometrySvg(feature: LocalMapFeature): string {
  const attrs = `class="${feature.authority}" data-feature-id="${escapeXml(feature.feature_id)}"${feature.structure ? ` data-structure-id="${escapeXml(feature.structure.id)}"` : ""}`;
  const geometry = feature.geometry;
  if (geometry.type === "Point") {
    return `<circle ${attrs} cx="${n(geometry.coordinates[0])}" cy="${n(geometry.coordinates[1])}" r="3"/>`;
  }
  if (geometry.type === "LineString") {
    return `<polyline ${attrs} points="${geometry.coordinates.map(pointText).join(" ")}"/>`;
  }
  if (geometry.type === "Polygon") {
    return geometry.coordinates.map((ring) => `<polygon ${attrs} points="${ring.map(pointText).join(" ")}"/>`).join("");
  }
  return geometry.coordinates.flatMap((polygon) => polygon.map((ring) => `<polygon ${attrs} points="${ring.map(pointText).join(" ")}"/>`)).join("");
}

function normalizeGeometry(value: unknown): LocalGeometry | null {
  if (typeof value !== "object" || value === null) return null;
  const candidate = value as { type?: unknown; coordinates?: unknown };
  if (candidate.type === "Point" && isPoint(candidate.coordinates)) {
    return { type: "Point", coordinates: candidate.coordinates };
  }
  if (candidate.type === "LineString" && isPointArray(candidate.coordinates)) {
    return { type: "LineString", coordinates: candidate.coordinates };
  }
  if (candidate.type === "Polygon" && isPointArrayArray(candidate.coordinates)) {
    return { type: "Polygon", coordinates: candidate.coordinates };
  }
  if (candidate.type === "MultiPolygon" && isPointArrayArrayArray(candidate.coordinates)) {
    return { type: "MultiPolygon", coordinates: candidate.coordinates };
  }
  return null;
}

function primitiveProperties(properties: Record<string, unknown>): Record<string, string | number | boolean | null> {
  const result: Record<string, string | number | boolean | null> = {};
  for (const [key, value] of Object.entries(properties)) {
    if (value === null || typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
      result[key] = value;
    }
  }
  return result;
}

function upstreamFeatureId(properties: Record<string, string | number | boolean | null>): string | null {
  const keys = ["building_id", "street_id", "poi_id", "entrance_id", "gate_id", "wall_id", "field_id", "water_id", "crossing_id", "junction_id"];
  for (const key of keys) {
    const value = properties[key];
    if (typeof value === "string" || typeof value === "number") return String(value);
  }
  return null;
}

function boundsFor(features: LocalMapFeature[]): LocalMapBounds {
  if (features.length === 0) return { min_x: -1, min_y: -1, max_x: 1, max_y: 1 };
  const boxes = features.map((feature) => geometryBounds(feature.geometry));
  return {
    min_x: Math.min(...boxes.map((box) => box.min_x)),
    min_y: Math.min(...boxes.map((box) => box.min_y)),
    max_x: Math.max(...boxes.map((box) => box.max_x)),
    max_y: Math.max(...boxes.map((box) => box.max_y)),
  };
}

function geometryBounds(geometry: LocalGeometry): LocalMapBounds {
  const points = geometry.type === "Point"
    ? [geometry.coordinates]
    : geometry.type === "LineString"
      ? geometry.coordinates
      : geometry.type === "Polygon"
        ? geometry.coordinates.flat()
        : geometry.coordinates.flat(2);
  return {
    min_x: Math.min(...points.map((point) => point[0])),
    min_y: Math.min(...points.map((point) => point[1])),
    max_x: Math.max(...points.map((point) => point[0])),
    max_y: Math.max(...points.map((point) => point[1])),
  };
}

function intersects(a: LocalMapBounds, b: LocalMapBounds): boolean {
  return a.min_x <= b.max_x && a.max_x >= b.min_x && a.min_y <= b.max_y && a.max_y >= b.min_y;
}

function failedMapping(structure: StructureProjection, message: string): StructureFeatureMapping {
  return { structure_id: structure.id, status: "failed", feature_id: null, message };
}

function structureIssue(structure: StructureProjection, code: string, message: string): LocalMapIssue {
  return { severity: "error", code, message, structure_id: structure.id };
}

function compareStructure(a: StructureProjection, b: StructureProjection): number {
  return a.established_year - b.established_year || a.id.localeCompare(b.id);
}

function compareFeatureId(a: LocalMapFeature, b: LocalMapFeature): number {
  return a.feature_id.localeCompare(b.feature_id);
}

function compareIssue(a: LocalMapIssue, b: LocalMapIssue): number {
  return a.code.localeCompare(b.code) || (a.structure_id ?? "").localeCompare(b.structure_id ?? "");
}

function stableHash(value: string): number {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

function toSettlemakerBiome(biome: string): string {
  const aliases: Record<string, string> = {
    semi_arid: "grassland",
    arid: "desert",
    boreal: "taiga",
    tropical: "tropical",
    alpine: "tundra",
    temperate: "temperate",
  };
  return aliases[biome] ?? "temperate";
}

function isPoint(value: unknown): value is LocalPoint {
  return Array.isArray(value) && value.length >= 2 && typeof value[0] === "number" && typeof value[1] === "number";
}

function isPointArray(value: unknown): value is LocalPoint[] {
  return Array.isArray(value) && value.every(isPoint);
}

function isPointArrayArray(value: unknown): value is LocalPoint[][] {
  return Array.isArray(value) && value.every(isPointArray);
}

function isPointArrayArrayArray(value: unknown): value is LocalPoint[][][] {
  return Array.isArray(value) && value.every(isPointArrayArray);
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function n(value: number): string {
  return Number(value.toFixed(3)).toString();
}

function pointText(point: LocalPoint): string {
  return `${n(point[0])},${n(point[1])}`;
}

function escapeXml(value: string): string {
  return value.replaceAll("&", "&amp;").replaceAll("\"", "&quot;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}
