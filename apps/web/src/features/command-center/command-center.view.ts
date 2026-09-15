import type {
  AttentionItemsResponse,
  DecisionOpportunityListResponse,
  DirectiveListResponse,
  HistoryResponse,
  RegionStatusResponse,
  SocietySummary,
  WorldSummary,
} from "../../lib/api";
import type {
  DisplayTone,
  FoodView,
  GovernanceView,
  HistoryFeedItem,
  RegionView,
  SocietyView,
  WorldSnapshot,
} from "./command-center.types";

export type CommandCenterBundle = {
  summary: WorldSummary;
  regions: RegionStatusResponse;
  history: HistoryResponse;
  directives: DirectiveListResponse;
  attention: AttentionItemsResponse;
  decisions: DecisionOpportunityListResponse;
};

const integerFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const decimalFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 3 });

export function toWorldSnapshot(bundle: CommandCenterBundle): WorldSnapshot {
  const { summary, regions, history, directives, attention, decisions } = bundle;
  const population = formatInteger(summary.population_total);
  const shortage = formatNumber(summary.food_shortage_severity);
  const regionViews = regions.regions.map(toRegionView);
  const societyViews = summary.societies.map((society) => toSocietyView(society, regionViews));

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
    feed: history.events.map((event) => toHistoryFeedItem(event, regionViews, societyViews)),
    regions: regionViews,
    societies: societyViews,
    metrics: [
      { label: "Population", value: population, detail: "world total", tone: "neutral" },
      { label: "Food shortage", value: shortage, detail: "authoritative severity", tone: "neutral" },
      { label: "Regions", value: String(summary.region_count), detail: "known regions", tone: "neutral" },
      { label: "Societies", value: String(summary.societies.length), detail: "status summaries", tone: "neutral" },
      { label: "Tensions", value: String(summary.pressures.length), detail: "active tension states", tone: "neutral" },
    ],
    pressures: summary.pressures.map((pressure) => ({
      id: pressure.id,
      label: formatLabel(pressure.key),
      regionId: pressure.region_id,
      regionLabel: regionViews.find((region) => region.id === pressure.region_id)?.label ?? `Region ${shortId(pressure.region_id)}`,
      milestone: formatLabel(pressure.milestone),
      intensity: formatNumber(pressure.intensity),
      ageTicks: pressure.age_ticks,
      causeCount: pressure.cause_event_ids.length,
    })),
    attentionItems: attention.items.map((item) => ({
      id: item.id,
      targetLabel: item.target
        ? directiveTargetLabel(item.target.id, societyViews)
        : "World",
      createdTick: item.created_tick,
      createdYear: item.created_year,
      category: formatLabel(item.category),
      priority: item.priority,
      context: item.context,
      relatedEventIds: item.related_event_ids,
    })),
    decisionOpportunities: decisions.opportunities.map((opportunity) => ({
      id: opportunity.id,
      targetId: opportunity.target.id,
      targetKind: opportunity.target.kind,
      targetLabel: directiveTargetLabel(opportunity.target.id, societyViews),
      createdTick: opportunity.created_tick,
      category: formatLabel(opportunity.category),
      context: opportunity.context,
      earliestEffectTick: opportunity.earliest_effect_tick,
      expiresAtTick: opportunity.expires_at_tick,
      defaultBehavior: opportunity.default_behavior,
      responseIntent: opportunity.response_intent,
    })),
    pendingDirectives: directives.pending.map((directive) => ({
      queueId: directive.queue_id,
      submittedTick: directive.submitted_tick,
      author: directive.author,
      targetId: directive.target.id,
      targetLabel: directiveTargetLabel(directive.target.id, societyViews),
      intent: formatLabel(directive.intent),
      priority: directive.priority,
    })),
    directives: directives.directives.map((directive) => ({
      id: directive.id,
      submittedTick: directive.submitted_tick,
      author: directive.author,
      targetId: directive.target.id,
      targetLabel: directiveTargetLabel(directive.target.id, societyViews),
      intent: formatLabel(directive.intent),
      priority: directive.priority,
      status: directive.status,
      progress: formatNumber(directive.progress),
    })),
  };
}

function toSocietyView(society: SocietySummary, regions: RegionView[]): SocietyView {
  const kind = society.subject.kind === "society" || society.subject.kind === "polity"
    ? society.subject.kind
    : "unsupported";
  const regionLabel = regions.find((region) => region.id === society.region_id)?.label ?? `Region ${shortId(society.region_id)}`;
  const kindLabel = kind === "unsupported" ? "Society" : formatLabel(kind);
  return {
    id: society.subject.id,
    kind,
    label: `${regionLabel} ${kindLabel}`,
    regionId: society.region_id,
    regionLabel,
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

function toHistoryFeedItem(
  event: HistoryResponse["events"][number],
  regions: RegionView[],
  societies: SocietyView[],
): HistoryFeedItem {
  const kind = normalizeKind(event.kind);
  const subject = event.subjects
    .map((item) => historySubjectLabel(item.kind, item.id, regions, societies))
    .find((label): label is string => Boolean(label));

  return {
    id: event.id,
    time: `Y${event.year} · T${event.tick}`,
    text: humanHistoryText(kind, subject),
    tone: historyTone(kind),
    source: event.source,
    technicalDetail: event.reason,
    causeCount: event.cause_event_ids.length,
  };
}

function humanHistoryText(kind: string, subject?: string): string {
  const place = subject ?? "A region";
  const target = subject ?? "a society";

  switch (kind) {
    case "resource_surplus":
      return `${place} produced more of a resource than it needed.`;
    case "resource_shortage":
      return `${place} is experiencing a resource shortage.`;
    case "food_shortage":
      return `${place} is experiencing a food shortage.`;
    case "food_insecurity_emerging":
      return `Food insecurity is emerging in ${place}.`;
    case "food_insecurity_elevated":
      return `Food insecurity has become elevated in ${place}.`;
    case "food_insecurity_crisis":
      return `${place} is in a food insecurity crisis.`;
    case "food_insecurity_recovering":
      return `Food insecurity is easing in ${place}.`;
    case "food_insecurity_resolved":
      return `Food insecurity has been resolved in ${place}.`;
    case "directive_submitted":
      return `A food-reserve directive was submitted for ${target}.`;
    case "directive_queued":
      return `A food-reserve directive for ${target} is waiting to be processed.`;
    case "directive_accepted":
      return `The food-reserve directive for ${target} was accepted and is now being carried out.`;
    case "directive_partial":
      return `The food-reserve directive for ${target} is only being carried out in part.`;
    case "directive_delayed":
      return `The food-reserve directive for ${target} has been delayed.`;
    case "directive_resisted":
      return `The food-reserve directive for ${target} is meeting resistance.`;
    case "directive_failed":
      return `The food-reserve directive for ${target} failed.`;
    case "directive_completed":
      return `The food-reserve directive for ${target} was completed.`;
    default:
      return subject
        ? `${subject}: ${formatLabel(kind).toLowerCase()} was recorded.`
        : `${formatLabel(kind)} was recorded in the world.`;
  }
}

function historyTone(kind: string): DisplayTone {
  if (kind.includes("crisis") || kind.includes("shortage") || kind.includes("failed")) return "critical";
  if (kind.includes("emerging") || kind.includes("elevated") || kind.includes("delayed") || kind.includes("resisted")) return "warning";
  if (kind.includes("surplus") || kind.includes("recovering") || kind.includes("resolved") || kind.includes("completed")) return "positive";
  return "neutral";
}

function historySubjectLabel(
  kind: string,
  id: string,
  regions: RegionView[],
  societies: SocietyView[],
): string | undefined {
  if (kind === "region") return regions.find((region) => region.id === id)?.label ?? `Region ${shortId(id)}`;
  if (kind === "society" || kind === "polity") {
    return societies.find((society) => society.id === id)?.label ?? `${formatLabel(kind)} ${shortId(id)}`;
  }
  if (kind === "world") return "The world";
  return undefined;
}

function directiveTargetLabel(targetId: string, societies: SocietyView[]): string {
  return societies.find((society) => society.id === targetId)?.label ?? `Society ${shortId(targetId)}`;
}

function normalizeKind(value: string): string {
  return value.trim().toLowerCase().replace(/[\s-]+/g, "_");
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
