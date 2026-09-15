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
  DirectiveListResponse,
  DirectivePriority,
  DirectiveStatus,
  DirectiveSubmissionRequest,
  HistoryEvent,
  HistoryResponse,
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
      const headers = new Headers(init.headers);
      headers.set("Accept", "application/json");
      if (init.body !== undefined && !headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
      }
      response = await this.fetchImpl(`${this.baseUrl}${path}`, {
        ...init,
        cache: "no-store",
        headers,
      });
    } catch (error) {
      throw new CliovaApiError(
        "Unable to reach the Cliova API.",
        { status: 0, code: "network_error" },
        { cause: error },
      );
    }

    if (!response.ok) {
      const payload = await parseApiError(response);
      throw new CliovaApiError(payload.message, {
        status: response.status,
        code: payload.code,
        details: payload.details,
      });
    }

    return (await response.json()) as T;
  }
}

async function parseApiError(
  response: Response,
): Promise<{ code: string; message: string; details: ApiErrorResponse["error"]["details"] }> {
  try {
    const payload = (await response.json()) as Partial<ApiErrorResponse>;
    if (payload.error && typeof payload.error.code === "string" && typeof payload.error.message === "string") {
      return {
        code: payload.error.code,
        message: payload.error.message,
        details: Array.isArray(payload.error.details) ? payload.error.details : [],
      };
    }
  } catch {
    // Fall through to the stable generic HTTP error below.
  }

  return {
    code: `http_${response.status}`,
    message: `Cliova API request failed with HTTP ${response.status}.`,
    details: [],
  };
}

export const cliovaApi = new HttpCliovaApiClient();
