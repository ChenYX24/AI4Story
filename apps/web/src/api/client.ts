// 轻量 fetch wrapper —— 自动附 Authorization: Bearer <token>
const BASE = "";
const TOKEN_KEY = "mindshow_token";

export function getAuthToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setAuthToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch { /* noop */ }
}

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail || `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

function buildHeaders(extra?: HeadersInit): HeadersInit {
  const h: Record<string, string> = { ...(extra as Record<string, string> | undefined) };
  const t = getAuthToken();
  if (t) h["Authorization"] = `Bearer ${t}`;
  return h;
}

async function handle(resp: Response) {
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const j = await resp.json();
      detail = j.detail ?? detail;
    } catch { /* ignore */ }
    // 401 自动清除 token
    if (resp.status === 401) setAuthToken(null);
    throw new ApiError(resp.status, detail);
  }
  const ct = resp.headers.get("content-type") || "";
  return ct.includes("application/json") ? resp.json() : resp.text();
}

export async function apiGet<T = unknown>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { headers: buildHeaders() });
  return handle(r) as Promise<T>;
}

export async function apiPost<T = unknown>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: buildHeaders({ "Content-Type": "application/json" }),
    body: body != null ? JSON.stringify(body) : undefined,
  });
  return handle(r) as Promise<T>;
}

export async function apiPatch<T = unknown>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "PATCH",
    headers: buildHeaders({ "Content-Type": "application/json" }),
    body: body != null ? JSON.stringify(body) : undefined,
  });
  return handle(r) as Promise<T>;
}

export async function apiPut<T = unknown>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "PUT",
    headers: buildHeaders({ "Content-Type": "application/json" }),
    body: body != null ? JSON.stringify(body) : undefined,
  });
  return handle(r) as Promise<T>;
}

export async function apiDelete<T = unknown>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "DELETE",
    headers: buildHeaders(),
  });
  return handle(r) as Promise<T>;
}
