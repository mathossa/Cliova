import type {
  AttentionPriority,
  DirectiveIntent,
  DirectivePriority,
  DirectiveStatus,
  DirectiveSubmissionRequest,
  WorldListItem,
  WorldMapResponse,
} from "../../lib/api";

export type DisplayTone = "neutral" | "positive" | "warning" | "critical";

export type HistoryFeedItem = {
  id: string;
  time: string;
  text: string;
  tone: DisplayTone;
  source: string;
  technicalDetail: string;
  causeCount: number;
  regionIds: string[];
};

export type FoodView = {
  foodSecurity: string;
  production: string;
  demand: string;
  stockpile: string;
  deficit: string;
  shortageSeverity: string;
};

export type GovernanceView = {
  legitimacy: string;
  executionCapacity: string;
  internalResistance: string;
};

export type SocietyView = {
  id: string;
  kind: "society" | "polity" | "unsupported";
  label: string;
  regionId: string;
  regionLabel: string;
  population: string;
  food: FoodView;
  governance: GovernanceView;
};

export type RegionView = {
  id: string;
  label: string;
  terrain: string;
  biome: string;
  population: string;
  habitability: string;
  waterAccess: string;
  climatePressure: string;
  food: FoodView;
};

export type PressureView = {
  id: string;
  label: string;
  regionId: string;
  regionLabel: string;
  milestone: string;
  intensity: string;
  ageTicks: number;
  causeCount: number;
};

export type DirectiveQueueView = {
  queueId: number;
  submittedTick: number;
  author: string;
  targetId: string;
  targetLabel: string;
  intent: string;
  priority: DirectivePriority;
};

export type DirectiveView = {
  id: string;
  submittedTick: number;
  author: string;
  targetId: string;
  targetLabel: string;
  intent: string;
  priority: DirectivePriority;
  status: DirectiveStatus;
  progress: string;
};

export type AttentionItemView = {
  id: string;
  targetLabel: string;
  createdTick: number;
  createdYear: number;
  category: string;
  priority: AttentionPriority;
  context: string;
  relatedEventIds: string[];
};

export type DecisionOpportunityView = {
  id: string;
  targetId: string;
  targetKind: "society" | "polity";
  targetLabel: string;
  createdTick: number;
  category: string;
  context: string;
  earliestEffectTick: number;
  expiresAtTick: number | null;
  defaultBehavior: string;
  responseIntent: DirectiveIntent;
};

export type WorldMetric = {
  label: string;
  value: string;
  detail: string;
  tone: DisplayTone;
};

export type WorldSnapshot = {
  source: "api-v1";
  id: string;
  label: string;
  tick: number;
  year: number;
  population: string;
  foodShortageSeverity: string;
  contractVersion: string;
  connection: string;
  regionCount: number;
  societyCount: number;
  feed: HistoryFeedItem[];
  regions: RegionView[];
  societies: SocietyView[];
  metrics: WorldMetric[];
  pressures: PressureView[];
  attentionItems: AttentionItemView[];
  decisionOpportunities: DecisionOpportunityView[];
  pendingDirectives: DirectiveQueueView[];
  directives: DirectiveView[];
  map: WorldMapResponse;
};

export type CommandCenterActions = {
  selectWorld: (worldId: string) => Promise<void>;
  createWorld: (seed: number) => Promise<void>;
  refresh: () => Promise<void>;
  submitDirective: (request: DirectiveSubmissionRequest) => Promise<void>;
  advanceDevelopmentTick: () => Promise<void>;
};

export type CommandCenterProps = {
  world: WorldSnapshot;
  worlds: WorldListItem[];
  actions: CommandCenterActions;
};
