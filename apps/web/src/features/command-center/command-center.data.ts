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
    description: "Developer/player command surface for querying and submitting intents without duplicating simulation rules in the browser.",
    plannedViews: ["World feed", "Selected entity", "Command history", "Explainability output"],
    plannedActions: ["status", "inspect", "why", "submit directive"],
  },
  {
    id: "directives",
    label: "Directives",
    description: "Priorities, advice and multi-year projects submitted to the authoritative simulation.",
    plannedViews: ["Active directives", "Proposals", "Execution progress", "Capacity demand"],
    plannedActions: ["Create directive", "Reprioritize", "Withdraw", "Compare proposals"],
  },
  {
    id: "world",
    label: "World",
    description: "Geography, climate, resources, routes, regions and territorial context.",
    plannedViews: ["Map layers", "Regions", "Resources", "Routes", "Environment"],
    plannedActions: ["Inspect region", "Toggle layer", "Compare regions", "Open route"],
  },
  {
    id: "society",
    label: "Society",
    description: "Population, psychology, values, identity and culture as aggregate simulation state.",
    plannedViews: ["Population", "Demography", "Values", "Culture", "Social pressures"],
    plannedActions: ["Inspect cohort", "Compare trends", "Trace cause"],
  },
  {
    id: "economy",
    label: "Economy",
    description: "Production, consumption, prices, trade, labor and resource flows.",
    plannedViews: ["Production", "Consumption", "Markets", "Trade", "Resource balance"],
    plannedActions: ["Inspect flow", "Compare sectors", "Trace shortage", "Open proposal"],
  },
  {
    id: "knowledge",
    label: "Knowledge",
    description: "Knowledge, practical experience, innovation, diffusion and research capacity.",
    plannedViews: ["Knowledge domains", "Innovation", "Diffusion", "Institutions", "Open questions"],
    plannedActions: ["Inspect domain", "Trace breakthrough", "Set priority"],
  },
  {
    id: "state",
    label: "State",
    description: "Government, institutions, legitimacy, administration and societal capacity.",
    plannedViews: ["Government", "Institutions", "Legitimacy", "Administration", "Capacity"],
    plannedActions: ["Inspect institution", "Review proposal", "Trace resistance"],
  },
  {
    id: "belief",
    label: "Belief",
    description: "Spirituality, belief systems, rituals, institutions and ideological movements.",
    plannedViews: ["Beliefs", "Movements", "Institutions", "Regional influence"],
    plannedActions: ["Inspect movement", "Compare influence", "Trace spread"],
  },
  {
    id: "people",
    label: "People",
    description: "Notable individuals, factions and movements that are important enough to model explicitly.",
    plannedViews: ["Notable individuals", "Factions", "Movements", "Influence networks"],
    plannedActions: ["Inspect actor", "Trace influence", "Open history"],
  },
  {
    id: "diplomacy",
    label: "Diplomacy",
    description: "Relations, messages, trade proposals, treaties, claims, threats and conflict.",
    plannedViews: ["Relations", "Inbox", "Treaties", "Claims", "Conflict"],
    plannedActions: ["Reply", "Draft proposal", "Inspect relation", "Review treaty"],
  },
  {
    id: "scenarios",
    label: "Issues",
    description: "Detected situations that bundle simulation signals into understandable player-facing issues.",
    plannedViews: ["Open issues", "Signals", "Stakeholders", "Possible responses"],
    plannedActions: ["Inspect issue", "Open causes", "Create directive", "Defer"],
  },
  {
    id: "history",
    label: "History",
    description: "Chronicle, timeline and causal chains for meaningful changes and historical memory.",
    plannedViews: ["Chronicle", "Timeline", "Causal graph", "Historical memory"],
    plannedActions: ["Open event", "Trace causes", "Compare years", "Replay context"],
  },
];

export const mockWorld = {
  source: "presentation-placeholder" as const,
  worldName: "Prototype World",
  year: 2142,
  season: "Spring",
  nextTick: "14:27",
  treasury: "¤ 2.43M",
  worldStatus: "Unstable",
  connection: "Simulation API not connected",
  feed: [
    { time: "2142.03.12", text: "Northern caravan arrived in Kesh.", tone: "positive" },
    { time: "2142.03.11", text: "Visibility reduced in eastern basins.", tone: "neutral" },
    { time: "2142.03.10", text: "Food reserves in Northreach are running low.", tone: "critical" },
    { time: "2142.03.09", text: "Diplomatic request received from the Union.", tone: "neutral" },
    { time: "2142.03.07", text: "New survey data available for Ashridge.", tone: "neutral" },
    { time: "2142.03.06", text: "Border skirmish reported near Red Dunes.", tone: "warning" },
    { time: "2142.03.04", text: "Innovation milestone: Efficient Irrigation.", tone: "positive" },
    { time: "2142.03.02", text: "Nomad influence increased in the Steppe corridor.", tone: "warning" },
  ],
  selectedRegion: {
    name: "Northreach",
    description: "Placeholder region data. This panel will consume authoritative geography, population, resource and stability data once those endpoints exist.",
    population: "184,000",
    primaryResource: "Iron ore",
    administration: "Limited",
    stability: "42%",
    conditions: "Arid · seasonal dust",
  },
  mapMarkers: [
    { id: "northreach", label: "Northreach", x: 49, y: 45, kind: "capital" },
    { id: "ashridge", label: "Ashridge", x: 31, y: 25, kind: "resource" },
    { id: "kesh", label: "Kesh", x: 77, y: 27, kind: "trade" },
    { id: "vellen", label: "Vellen", x: 25, y: 70, kind: "city" },
    { id: "salt-basin", label: "Salt Basin", x: 54, y: 80, kind: "resource" },
    { id: "red-dunes", label: "Red Dunes", x: 84, y: 54, kind: "pressure" },
  ],
  metrics: [
    { label: "Economy", value: "¤ 2.43M", delta: "+6%", detail: "income / 6 ticks", tone: "positive" },
    { label: "Food", value: "62%", delta: "−1%", detail: "reserve level", tone: "warning" },
    { label: "Stability", value: "58%", delta: "−4%", detail: "aggregate index", tone: "warning" },
    { label: "Capacity", value: "3,200", delta: "+0%", detail: "mobilizable placeholder", tone: "neutral" },
    { label: "Knowledge", value: "T3", delta: "63%", detail: "current domain progress", tone: "positive" },
  ],
  pressures: [
    { label: "Food shortage", severity: "High" },
    { label: "Regional unrest", severity: "High" },
    { label: "Nomad influence", severity: "Medium" },
    { label: "Resource competition", severity: "Medium" },
    { label: "Dust activity", severity: "Low" },
  ],
};
