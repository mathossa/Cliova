// Stable browser-facing API v1 contracts.
// These mirror backend boundary DTOs, not simulation domain or frontend view models.

export type EntityKind = "world" | "region" | "society" | "polity" | "individual";
export type DirectiveIntent = "strengthen_food_reserves";
export type DirectivePriority = "low" | "normal" | "high";
export type DirectiveStatus =
  | "queued"
  | "accepted"
  | "partial"
  | "delayed"
  | "resisted"
  | "failed"
  | "completed";
export type PressureMilestone = "emerging" | "elevated" | "crisis" | "recovering" | "resolved";

export type EntityRef = {
  kind: EntityKind;
  id: string;
};

export type VersionMetadata = {
  contract_version: "v1";
  world_schema_version: number;
  simulation_version: number;
  rng_algorithm: string;
};

export type FoodStatus = {
  food_security: number | null;
  production: number | null;
  demand: number | null;
  stockpile: number | null;
  deficit: number | null;
  shortage_severity: number | null;
};

export type GovernanceCondition = {
  legitimacy: number;
  execution_capacity: number;
  internal_resistance: number;
};

export type PressureStatus = {
  id: string;
  key: string;
  region_id: string;
  subject: EntityRef | null;
  intensity: number;
  milestone: PressureMilestone;
  age_ticks: number;
  cause_event_ids: string[];
};

export type SocietySummary = {
  subject: EntityRef;
  region_id: string;
  population: number | null;
  food: FoodStatus;
  governance: GovernanceCondition;
};

export type RegionStatus = {
  id: string;
  key: string;
  terrain: string;
  biome: string;
  habitability: number;
  water_access: number;
  climate_pressure: number;
  population: number | null;
  food: FoodStatus;
  pressures: PressureStatus[];
};

export type WorldListItem = {
  id: string;
  tick: number;
  year: number;
  region_count: number;
  society_count: number;
  population_total: number | null;
};

export type WorldListResponse = {
  worlds: WorldListItem[];
};

export type WorldSummary = {
  id: string;
  tick: number;
  year: number;
  versions: VersionMetadata;
  region_count: number;
  population_total: number | null;
  food_shortage_severity: number | null;
  societies: SocietySummary[];
  pressures: PressureStatus[];
};

export type RegionStatusResponse = {
  world_id: string;
  tick: number;
  regions: RegionStatus[];
};

export type SocietyStatusResponse = {
  world_id: string;
  tick: number;
  societies: SocietySummary[];
};

export type CreateDevelopmentWorldRequest = {
  seed: number;
  world_key?: string;
};

export type HistoryEvent = {
  id: string;
  tick: number;
  year: number;
  source: string;
  kind: string;
  reason: string;
  subjects: EntityRef[];
  cause_event_ids: string[];
};

export type HistoryResponse = {
  world_id: string;
  events: HistoryEvent[];
};

export type DirectiveTarget = {
  kind: "society" | "polity";
  id: string;
};

export type DirectiveSubmissionRequest = {
  author: string;
  target: DirectiveTarget;
  intent?: DirectiveIntent;
  priority?: DirectivePriority;
};

export type QueuedDirective = {
  queue_id: number;
  submitted_tick: number;
  author: string;
  target: DirectiveTarget;
  intent: DirectiveIntent;
  priority: DirectivePriority;
};

export type AuthoritativeDirective = {
  id: string;
  author: string;
  target: DirectiveTarget;
  intent: DirectiveIntent;
  priority: DirectivePriority;
  submitted_tick: number;
  submission_event_id: string;
  status: DirectiveStatus;
  progress: number;
};

export type DirectiveListResponse = {
  world_id: string;
  pending: QueuedDirective[];
  directives: AuthoritativeDirective[];
};

export type ManualTickRequest = {
  expected_tick: number;
};

export type ManualTickResponse = {
  world: WorldSummary;
  event_ids: string[];
};

export type ApiErrorDetail = {
  location: string | null;
  message: string;
  type: string | null;
};

export type ApiErrorResponse = {
  error: {
    code: string;
    message: string;
    details: ApiErrorDetail[];
  };
};
