// Calls to the FastAPI backend. The session lives in an httpOnly cookie, so the
// browser never handles the token and never sends a customer ID with a question.

export type Status = "answer" | "decline_with_reason" | "raise_request" | "refuse";

export type AgentReply = {
  role: "agent";
  status: Status;
  path: "llm" | "rules" | "safe_fallback" | "customer_not_found" | "small_talk";
  message: string;
  reason_codes: string[];
  requests: { request_id: string; queue: string }[];
  meta: { ms: number; llm_calls: number; cost_usd: number; trace_id: string };
};

export type Turn = { role: "customer"; text: string } | AgentReply;

export type Me = { customer_id: string; name: string | null; card_product: string | null };

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

// One refresh at a time: refresh tokens are single use, so two parallel refreshes
// would look like a stolen token and end the session.
let refreshing: Promise<boolean> | null = null;

function refreshTokens(): Promise<boolean> {
  refreshing ??= fetch("/api/auth/refresh", { method: "POST" })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => { refreshing = null; });
  return refreshing;
}

async function call<T>(path: string, init?: RequestInit, retry = true): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  // The access token lasts 10 minutes: swap the refresh token for a new pair and try once more.
  // Retry even if this refresh failed: another tab may have just refreshed and set new cookies.
  if (response.status === 401 && retry && !path.startsWith("/auth/")) {
    await refreshTokens();
    return call<T>(path, init, false);
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, body.detail ?? "Something went wrong. Please try again.");
  }
  return response.json();
}

export const api = {
  login: (customer_id: string, password: string) =>
    call<{ customer_id: string }>("/auth/login", { method: "POST", body: JSON.stringify({ customer_id, password }) }),
  logout: () => call("/auth/logout", { method: "POST" }),
  me: () => call<Me>("/me"),
  history: () => call<{ messages: Turn[] }>("/history"),
  ask: (question: string) => call<AgentReply>("/chat", { method: "POST", body: JSON.stringify({ question }) }),
};
