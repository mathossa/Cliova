export type ModuleId =
  | "terminal"
  | "directives"
  | "world"
  | "society"
  | "economy"
  | "knowledge"
  | "state"
  | "belief"
  | "people"
  | "diplomacy"
  | "scenarios"
  | "history";

export type CommandCenterModule = {
  id: ModuleId;
  label: string;
  description: string;
  plannedViews: string[];
  plannedActions: string[];
};

export const assetPaths = {
  worldMap: "/assets/maps/world-overview.webp",
  regionPreview: "/assets/regions/northreach.webp",
} as const;

export const modules: CommandCenterModule[] = [
  {
    id: "terminal",
    label: "Terminal",
    description: "Read-only command surface for inspecting the live world without duplicating simulation rules in the browser.",
    plannedViews: ["World feed", "Selected region", "Status queries"],
    plannedActions: ["status", "inspect", "history"],
  },
  {
    id: "directives",
    label: "Directives",
    description: "Submit supported priorities to the authoritative simulation and follow their lifecycle.",
    plannedViews: ["Pending queue", "Directive lifecycle", "Execution progress"],
    plannedActions: ["Submit supported directive"],
  },
  {
    id: "world",
    label: "World",
    description: "Authoritative world and regional status exposed by API v1.",
    plannedViews: ["Regions", "Geography", "Environment"],
    plannedActions: ["Inspect region"],
  },
  {
    id: "society",
    label: "Society",
    description: "Aggregate population and society status exposed by API v1.",
    plannedViews: ["Population", "Societies"],
    plannedActions: ["Inspect society"],
  },
  {
    id: "economy",
    label: "Economy",
    description: "Stable high-level food/economic condition from API v1; internal production mechanics stay server-side.",
    plannedViews: ["Food security", "Production", "Demand", "Stockpile", "Deficit"],
    plannedActions: ["Inspect food condition"],
  },
  {
    id: "knowledge",
    label: "Knowledge",
    description: "Knowledge and capability detail is not part of the initial API v1 browser boundary.",
    plannedViews: ["Knowledge domains", "Innovation", "Diffusion"],
    plannedActions: ["Inspect domain"],
  },
  {
    id: "state",
    label: "State",
    description: "High-level governance condition exposed by API v1.",
    plannedViews: ["Legitimacy", "Execution capacity", "Internal resistance"],
    plannedActions: ["Inspect governance"],
  },
  {
    id: "belief",
    label: "Belief",
    description: "Belief systems are not yet exposed through API v1.",
    plannedViews: ["Beliefs", "Movements", "Institutions"],
    plannedActions: ["Inspect movement"],
  },
  {
    id: "people",
    label: "People",
    description: "Notable people and factions are not yet exposed through API v1.",
    plannedViews: ["Notable individuals", "Factions", "Movements"],
    plannedActions: ["Inspect actor"],
  },
  {
    id: "diplomacy",
    label: "Diplomacy",
    description: "Diplomacy is not yet exposed through API v1.",
    plannedViews: ["Relations", "Treaties", "Claims", "Conflict"],
    plannedActions: ["Inspect relation"],
  },
  {
    id: "scenarios",
    label: "Issues",
    description: "Persistent pressure state exposed by API v1, including milestone, intensity and causal event references.",
    plannedViews: ["Active pressures", "Milestones", "Causal references"],
    plannedActions: ["Inspect pressure"],
  },
  {
    id: "history",
    label: "History",
    description: "Recent authoritative simulation events and their causal references.",
    plannedViews: ["Recent history", "Causal links"],
    plannedActions: ["Inspect event"],
  },
];
