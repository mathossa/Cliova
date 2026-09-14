// Frontend display model; a future API adapter maps shared contracts into this shape.
// Marker coordinates describe artwork placement only.
export type WorldSnapshot = {
  source: string;
  worldName: string;
  year: number;
  season: string;
  nextTick: string;
  treasury: string;
  worldStatus: string;
  connection: string;
  feed: { time: string; text: string; tone: string }[];
  selectedRegion: {
    id: string; name: string; description: string; population: string;
    primaryResource: string; administration: string; stability: string; conditions: string;
  } | null;
  mapMarkers: { id: string; label: string; x: number; y: number; kind: string }[];
  metrics: { label: string; value: string; delta: string; detail: string; tone: string }[];
  pressures: { label: string; severity: string }[];
};
export type WorldClient = { load: () => Promise<WorldSnapshot | null> };
