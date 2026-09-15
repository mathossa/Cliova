import {
  cliovaApi,
  type CliovaApi,
  type CreateDevelopmentWorldRequest,
  type DirectiveSubmissionRequest,
  type WorldListItem,
} from "../../lib/api";
import type { CommandCenterBundle } from "./command-center.view";

const RECENT_HISTORY_TICKS = 24;

export type CommandCenterLoadResult =
  | { kind: "empty"; worlds: WorldListItem[] }
  | { kind: "missing"; worlds: WorldListItem[]; worldId: string }
  | { kind: "ready"; worlds: WorldListItem[]; worldId: string; data: CommandCenterBundle };

export interface CommandCenterClient {
  load(preferredWorldId?: string): Promise<CommandCenterLoadResult>;
  createWorld(request: CreateDevelopmentWorldRequest): Promise<CommandCenterLoadResult>;
  submitDirective(worldId: string, request: DirectiveSubmissionRequest): Promise<CommandCenterLoadResult>;
  advanceDevelopmentTick(worldId: string, expectedTick: number): Promise<CommandCenterLoadResult>;
}

export class LiveCommandCenterClient implements CommandCenterClient {
  constructor(private readonly api: CliovaApi = cliovaApi) {}

  async load(preferredWorldId?: string): Promise<CommandCenterLoadResult> {
    const { worlds } = await this.api.listWorlds();
    if (worlds.length === 0) return { kind: "empty", worlds };

    const selected = preferredWorldId
      ? worlds.find((world) => world.id === preferredWorldId)
      : worlds[0];
    if (!selected) return { kind: "missing", worlds, worldId: preferredWorldId ?? "" };

    const startTick = Math.max(0, selected.tick - RECENT_HISTORY_TICKS);
    const [summary, regions, map, history, directives] = await Promise.all([
      this.api.getWorld(selected.id),
      this.api.getRegions(selected.id),
      this.api.getWorldMap(selected.id),
      this.api.getHistory(selected.id, { startTick }),
      this.api.getDirectives(selected.id),
    ]);

    return {
      kind: "ready",
      worlds,
      worldId: selected.id,
      data: { summary, regions, map, history, directives },
    };
  }

  async createWorld(request: CreateDevelopmentWorldRequest): Promise<CommandCenterLoadResult> {
    const world = await this.api.createDevelopmentWorld(request);
    return this.load(world.id);
  }

  async submitDirective(
    worldId: string,
    request: DirectiveSubmissionRequest,
  ): Promise<CommandCenterLoadResult> {
    await this.api.submitDirective(worldId, request);
    return this.load(worldId);
  }

  async advanceDevelopmentTick(worldId: string, expectedTick: number): Promise<CommandCenterLoadResult> {
    await this.api.advanceDevelopmentTick(worldId, expectedTick);
    return this.load(worldId);
  }
}

export const liveCommandCenterClient = new LiveCommandCenterClient();
