import { mockWorld } from "./command-center.data";
import type { WorldClient } from "./command-center.types";

// Replace this adapter when the API contracts exist. Never silently fall back to
// mock data on a failed live request.
export const previewWorldClient: WorldClient = {
  async load() { return mockWorld; },
};
