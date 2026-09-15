import type {
  DirectiveListResponse,
  HistoryResponse,
  RegionStatusResponse,
  SocietySummary,
  WorldSummary,
} from "../../lib/api";
import type {
  FoodView,
  GovernanceView,
  RegionView,
  SocietyView,
  WorldSnapshot,
} from "./command-center.types";

export type CommandCenterBundle = {
  summary: WorldSummary;
  regions: RegionStatusResponse;
  history: HistoryResponse;
  directives: DirectiveListResponse;
};

const integerFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const decimalFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 3 });

export function toWorldSnapshot(bundle: CommandCenterBundle): WorldSnapshot {
  const { summary, regions, history, directives } = bundle;
  const population = formatInteger(summary.population_total);
  const shortage = formatNumber(summary.food_shortage_severity);

  return {
    source: "api-v1",
    id: summary.id,
    label: `World ${shortId(summary.id)}`,
    tick: summary.tick,
    year: summary.year,
    population,
    foodShortageSeverity: shortage,
    contractVersion: summary.versions.contract_version,
    connection: "Live API v1",
    regionCount: summary.region_count,
    societyCount: summary.societies.length,
    feed: history.events.map((event) => ({
      id: event.id,
      time: `Y${event.year} · T${event.tick}`,
      text: `${formatLabel(event.kind)} — ${event.reason}`,
      tone: "neutral",
      source: event.source,
      causeCount: event.cause_event_ids.length,
    })),
    regions: regions.regions.map(toRegionView),
    societies: summary.societies.map(toSocietyView),
    metrics: [
      { label: "Population", value: population, detail: "world total", tone: "neutral" },
      { label: "Food shortage", value: shortage, detail: "authoritative severity", tone: "neutral" },
      { label: "Regions", value: String(summary.region_count), detail: "known regions", tone: "neutral" },
      { label: "Societies", value: String(summary.societies.length), detail: "status summaries", tone: "neutral" },
      { label: "Pressures", value: String(summary.pressures.length), detail: "active pressure states", tone: "neutral" },
    ],
    pressures: summary.pressures.map((pressure) => ({
      id: pressure.id,
      label: formatLabel(pressure.key),
      regionId: pressure.region_id,
      milestone: formatLabel(pressure.milestone),
      intensity: formatNumber(pressure.intensity),
      ageTicks: pressure.age_ticks,
      causeCount: pressure.cause_event_ids.length,
    })),
    pendingDirectives: directives.pending.map((directive) => ({
      queueId: directive.queue_id,
      submittedTick: directive.submitted_tick,
      author: directive.author,
      targetId: directive.target.id,
      intent: formatLabel(directive.intent),
      priority: directive.priority,
    })),
    directives: directives.directives.map((directive) => ({
      id: directive.id,
      submittedTick: directive.submitted_tick,
      author: directive.author,
      targetId: directive.target.id,
      intent: formatLabel(directive.intent),
      priority: directive.priority,
      status: directive.status,
      progress: formatNumber(directive.progress),
    })),
  };
}

function toSocietyView(society: SocietySummary): SocietyView {
  const kind = society.subject.kind === "society" || society.subject.kind === "polity"
    ? society.subject.kind
    : "unsupported";
  return {
    id: society.subject.id,
    kind,
    label: `${formatLabel(society.subject.kind)} ${shortId(society.subject.id)}`,
    regionId: society.region_id,
    population: formatInteger(society.population),
    food: toFoodView(society.food),
    governance: toGovernanceView(society.governance),
  };
}

function toRegionView(region: RegionStatusResponse["regions"][number]): RegionView {
  return {
    id: region.id,
    label: formatLabel(region.key),
    terrain: formatLabel(region.terrain),
    biome: formatLabel(region.biome),
    population: formatInteger(region.population),
    habitability: formatNumber(region.habitability),
    waterAccess: formatNumber(region.water_access),
    climatePressure: formatNumber(region.climate_pressure),
    food: toFoodView(region.food),
  };
}

function toFoodView(food: SocietySummary["food"]): FoodView {
  return {
    foodSecurity: formatNumber(food.food_security),
    production: formatNumber(food.production),
    demand: formatNumber(food.demand),
    stockpile: formatNumber(food.stockpile),
    deficit: formatNumber(food.deficit),
    shortageSeverity: formatNumber(food.shortage_severity),
  };
}

function toGovernanceView(governance: SocietySummary["governance"]): GovernanceView {
  return {
    legitimacy: formatNumber(governance.legitimacy),
    executionCapacity: formatNumber(governance.execution_capacity),
    internalResistance: formatNumber(governance.internal_resistance),
  };
}

export function formatLabel(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function shortId(value: string): string {
  return value.slice(0, 8);
}

export function formatInteger(value: number | null): string {
  return value === null || !Number.isFinite(value) ? "Unavailable" : integerFormatter.format(value);
}

export function formatNumber(value: number | null): string {
  return value === null || !Number.isFinite(value) ? "Unavailable" : decimalFormatter.format(value);
}
