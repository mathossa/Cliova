import type {
  ApiErrorResponse,
  CreateDevelopmentWorldRequest,
  DirectiveListResponse,
  DirectiveSubmissionRequest,
  HistoryResponse,
  ManualTickResponse,
  QueuedDirective,
  RegionStatusResponse,
  WorldListResponse,
  WorldSummary,
} from "../../../../packages/contracts/v1";

export type {
  ApiErrorResponse,
  AuthoritativeDirective,
  CreateDevelopmentWorldRequest,
  DirectiveIntent,
  DirectiveListResponse,
  DirectivePriority,
  DirectiveStatus,
  DirectiveSubmissionRequest,
  HistoryEvent,
  HistoryResponse,
  ManualTickResponse,
  PressureStatus,
  QueuedDirective,
  RegionStatus,
  RegionStatusResponse,
  SocietySummary,
  WorldListItem,
  WorldListResponse,
  WorldSummary,
} from "../../../../packages/contracts/v1";

export type HistoryQuery = {
  startTick?: number;
  endTick?: number;
};

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export interface CliovaApi {
  listWorlds(): Promise<WorldListResponse>;
  createDevelopmentWorld(request: CreateDevelopmentWorldRequest): Promise<WorldSummary>;
  getWorld(worldId: string): Promise<WorldSummary>;
  getRegions(worldId: string): Promise<RegionStatusResponse>;
  getHistory(worldId: string, query?: HistoryQuery): Promise<HistoryResponse>;
  getDirectives(worldId: string): Promise<DirectiveListResponse>;
  submitDirective(worldId: string, request: DirectiveSubmissionRequest): Promise<QueuedDirective>;
  advanceDevelopmentTick(worldId: string, expectedTick: number): Promise<ManualTickResponse>;
}

export class CliovaApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: ApiErrorResponse["error"]["details"];

  constructor(
    message: string,
    { status, code, details = [] }: { status: number; code: string; details?: ApiErrorResponse["error"]["details"] },
    options?: ErrorOptions,
  ) {
    super(message, options);
    this.name = "CliovaApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function describeApiError(error: unknown): string {
  if (error instanceof CliovaApiError) {
    const detail = error.details.map((item) => item.message).filter(Boolean).join(" ");
    return detail ? `${error.message} ${detail}` : error.message;
  }
  if (error instanceof Error) return error.message;
  return "Unexpected Cliova API error.";
}

export class HttpCliovaApiClient implements CliovaApi {
  constructor(
    private readonly fetchImpl: FetchLike = (input, init) => fetch(input, init),
    private readonly baseUrl = "",
  ) {}

  listWorlds(): Promise<WorldListResponse> {
    return this.request("/api/v1/worlds");
  }

  createDevelopmentWorld(request: CreateDevelopmentWorldRequest): Promise<WorldSummary> {
    return this.request("/api/v1/dev/worlds", { method: "POST", body: JSON.stringify(request) });
  }

  getWorld(worldId: string): Promise<WorldSummary> {
    return this.request(`/api/v1/worlds/${encodeURIComponent(worldId)}`);
  }

  getRegions(worldId: string): Promise<RegionStatusResponse> {
    return this.request(`/api/v1/worlds/${encodeURIComponent(worldId)}/regions`);
  }

  getHistory(worldId: string, query: HistoryQuery = {}): Promise<HistoryResponse> {
    const params = new URLSearchParams();
    if (query.startTick !== undefined) params.set("start_tick", String(query.startTick));
    if (query.endTick !== undefined) params.set("end_tick", String(query.endTick));
    const suffix = params.size > 0 ? `?${params.toString()}` : "";
    return this.request(`/api/v1/worlds/${encodeURIComponent(worldId)}/history${suffix}`);
  }

  getDirectives(worldId: string): Promise<DirectiveListResponse> {
    return this.request(`/api/v1/worlds/${encodeURIComponent(worldId)}/directives`);
  }

  submitDirective(worldId: string, request: DirectiveSubmissionRequest): Promise<QueuedDirective> {
    return this.request(`/api/v1/worlds/${encodeURIComponent(worldId)}/directives`, {
      method: "POST",
      body: JSON.stringify(request),
    });
  }

  advanceDevelopmentTick(worldId: string, expectedTick: number): Promise<ManualTickResponse> {
    return this.request(`/api/v1/dev/worlds/${encodeURIComponent(worldId)}/ticks`, {
      method: "POST",
      body: JSON.stringify({ expected_tick: expectedTick }),
    });
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl}${path}`, {
        ...init,
        headers: {
          Accept: "application/json",
          ...(init.body ? { "Content-Type": "application/json" } : {}),
          ...init.headers,
        },
        cache: "no-store",
      });
    } catch (cause) {
      throw new CliovaApiError("Unable to reach the Cliova API.", {
        status: 0,
        code: "network_error",
      }, { cause });
    }

    if (!response.ok) {
      const payload = await parseErrorPayload(response);
      throw new CliovaApiError(payload.error.message, {
        status: response.status,
        code: payload.error.code,
        details: payload.error.details,
      });
    }

    return response.json() as Promise<T>;
  }
}

async function parseErrorPayload(response: Response): Promise<ApiErrorResponse> {
  try {
    const payload = await response.json() as Partial<ApiErrorResponse>;
    if (payload.error?.message && payload.error.code) {
      return {
        error: {
          code: payload.error.code,
          message: payload.error.message,
          details: payload.error.details ?? [],
        },
      };
    }
  } catch {
    // Fall through to a stable client-side error shape.
  }

  return {
    error: {
      code: `http_${response.status}`,
      message: `Cliova API request failed with HTTP ${response.status}.`,
      details: [],
    },
  };
}

export const cliovaApi = new HttpCliovaApiClient();
