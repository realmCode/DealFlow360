/**
 * The single place this application calls `fetch`.
 *
 * Responsibilities: bearer auth, one shared silent refresh, error
 * normalisation into DealFlowError, page-envelope awareness and binary
 * downloads. Components never see a raw Response.
 */
import { DealFlowError, type ApiErrorBody } from "./errors";
import type { TokenPair } from "./types";

export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://127.0.0.1:8010";

/* -- token storage --------------------------------------------------------
   sessionStorage rather than a cookie: the backend runs with
   cors_allow_credentials off and authenticates from the Authorization
   header, so there is nothing for a cookie to do here. */
const ACCESS = "df360.access";
const REFRESH = "df360.refresh";

export const tokens = {
  access: () => sessionStorage.getItem(ACCESS),
  refresh: () => sessionStorage.getItem(REFRESH),
  set(pair: TokenPair) {
    sessionStorage.setItem(ACCESS, pair.access_token);
    sessionStorage.setItem(REFRESH, pair.refresh_token);
  },
  clear() {
    sessionStorage.removeItem(ACCESS);
    sessionStorage.removeItem(REFRESH);
  },
};

type Listener = () => void;
const authLost = new Set<Listener>();
export const onAuthLost = (fn: Listener) => {
  authLost.add(fn);
  return () => authLost.delete(fn);
};
const fireAuthLost = () => authLost.forEach((fn) => fn());

/* -- refresh: one in-flight promise shared by every concurrent 401 -------- */
let refreshing: Promise<boolean> | null = null;

async function refreshOnce(): Promise<boolean> {
  const token = tokens.refresh();
  if (!token) return false;
  if (!refreshing) {
    refreshing = (async () => {
      try {
        const res = await fetch(`${API_BASE}/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: token }),
        });
        if (!res.ok) return false;
        tokens.set((await res.json()) as TokenPair);
        return true;
      } catch {
        return false;
      } finally {
        // Release on the next tick so simultaneous callers share this result.
        setTimeout(() => (refreshing = null), 0);
      }
    })();
  }
  return refreshing;
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  idempotencyKey?: string;
  signal?: AbortSignal;
  /** Skip the automatic refresh-and-retry (used by the auth calls). */
  raw?: boolean;
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(API_BASE + path);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      // Omit empty params entirely — the backend rejects "" for enum filters.
      if (v === undefined || v === null || v === "") continue;
      url.searchParams.set(k, String(v));
    }
  }
  return url.toString();
}

async function toError(res: Response): Promise<DealFlowError> {
  let code = "INTERNAL_ERROR";
  let message = res.statusText || "Request failed";
  let details: Record<string, unknown> = {};
  try {
    const body = (await res.json()) as ApiErrorBody;
    if (body?.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
      details = body.error.details ?? {};
    }
  } catch {
    /* non-JSON error body — keep the status text */
  }
  return new DealFlowError(res.status, code, message, details);
}

async function run(path: string, opts: RequestOptions, retry: boolean): Promise<Response> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const access = tokens.access();
  if (access) headers.Authorization = `Bearer ${access}`;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (opts.idempotencyKey) headers["Idempotency-Key"] = opts.idempotencyKey;

  let res: Response;
  try {
    res = await fetch(buildUrl(path, opts.query), {
      method: opts.method ?? "GET",
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: opts.signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new DealFlowError(0, "NETWORK_ERROR", "Cannot reach the DealFlow360 API.");
  }

  if (res.status === 401 && retry && !opts.raw) {
    const body = await res.clone().json().catch(() => null) as ApiErrorBody | null;
    // Only a genuinely expired access token is retryable. A disabled account
    // or a token-type mix-up will fail again and should surface immediately.
    if (body?.error?.code === "AUTHENTICATION_FAILED" && (await refreshOnce())) {
      return run(path, opts, false);
    }
    tokens.clear();
    fireAuthLost();
  }
  return res;
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const res = await run(path, opts, true);
  if (!res.ok) throw await toError(res);
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

/** Binary download (report exports). Returns the blob and its filename. */
export async function download(
  path: string,
  query?: RequestOptions["query"],
): Promise<{ blob: Blob; filename: string }> {
  const res = await run(path, { query }, true);
  if (!res.ok) throw await toError(res);
  const disposition = res.headers.get("content-disposition") ?? "";
  const match = /filename="?([^"]+)"?/.exec(disposition);
  return { blob: await res.blob(), filename: match?.[1] ?? "dealflow360-export" };
}

export const api = {
  get: <T>(path: string, query?: RequestOptions["query"], signal?: AbortSignal) =>
    request<T>(path, { method: "GET", query, signal }),
  post: <T>(path: string, body?: unknown, extra?: Partial<RequestOptions>) =>
    request<T>(path, { method: "POST", body: body ?? {}, ...extra }),
  patch: <T>(path: string, body?: unknown, extra?: Partial<RequestOptions>) =>
    request<T>(path, { method: "PATCH", body: body ?? {}, ...extra }),
  del: <T>(path: string, extra?: Partial<RequestOptions>) =>
    request<T>(path, { method: "DELETE", ...extra }),
  download,
};

/** A stable key per user intent, kept across retries of that same intent. */
export const idempotencyKey = (intent: string) => `${intent}:${crypto.randomUUID()}`;

/** Unwrap `Page<T>` or a bare array — the backend uses both. */
export const rows = <T>(payload: T[] | { items: T[] } | undefined | null): T[] => {
  if (!payload) return [];
  return Array.isArray(payload) ? payload : (payload.items ?? []);
};
