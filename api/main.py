"""HTTP API for the web app: login, chat and history.

  uvicorn api.main:app --port 8000

The customer is identified by the access token only. The chat endpoint takes a
question and nothing else, so neither the browser nor the LLM can choose whose
account is read. All decisions and checks stay in agent/; this layer adds login,
storage and rate limits.

Tokens are random strings stored in Redis, not JWTs, so signing out or a detected
theft ends a session immediately:
- access token: 10 minutes, sent with every request.
- refresh token: single use. Each refresh swaps it for a new pair. A refresh token
  that was already used means someone else has a copy, so the whole session ends.
- session ("family"): at most 8 hours from login, however often it is refreshed.
"""
import hmac
import json
import os
import secrets
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from agent import tools  # noqa: E402
from agent.corpus import ROOT  # noqa: E402
from agent.pipeline import Agent  # noqa: E402
from agent.upstream import fetch_account  # noqa: E402
from api.store import make_store  # noqa: E402

ACCESS_TTL_S = 10 * 60
REFRESH_TTL_S = 8 * 3600
SESSION_MAX_S = 8 * 3600
REUSE_GRACE_S = 10  # two tabs refreshing together is not theft; an attacker within 10s goes undetected
REFRESH_PATH = "/api/auth"  # the refresh cookie is only sent to the auth endpoints
HISTORY_KEEP = 50
HISTORY_TTL_S = 24 * 3600
CHAT_PER_MINUTE = 10
LOGIN_PER_MINUTE = 5
FEEDBACK_PER_MINUTE = 20
_feedback_lock = threading.Lock()  # several requests can write the file at once


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.store = getattr(app.state, "store", None) or make_store()
    app.state.agent = getattr(app.state, "agent", None) or Agent()  # builds the search index once
    yield


app = FastAPI(title="Grounded card agent", lifespan=lifespan)


class Login(BaseModel):
    customer_id: str = Field(max_length=32)
    password: str = Field(max_length=128)


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class Feedback(BaseModel):
    trace_id: str = Field(max_length=32)
    helpful: bool


def _limit(store, key: str, per_minute: int):
    if store.incr(f"rate:{key}", ttl=60) > per_minute:
        raise HTTPException(429, "Too many requests. Please wait a minute and try again.")


def _issue_tokens(store, response: Response, customer_id: str, family: str):
    access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    claims = json.dumps({"customer_id": customer_id, "family": family})
    store.set(f"access:{access}", claims, ttl=ACCESS_TTL_S)
    store.set(f"refresh:{refresh}", claims, ttl=REFRESH_TTL_S)
    secure = os.environ.get("COOKIE_SECURE") == "1"
    response.set_cookie("access", access, max_age=ACCESS_TTL_S, httponly=True, samesite="lax", secure=secure)
    response.set_cookie("refresh", refresh, max_age=REFRESH_TTL_S, httponly=True, samesite="strict", secure=secure,
                        path=REFRESH_PATH)


def _clear_cookies(response: Response):
    response.delete_cookie("access")
    response.delete_cookie("refresh", path=REFRESH_PATH)


def current_customer(request: Request, access: str | None = Cookie(default=None)) -> str:
    store = request.app.state.store
    raw = store.get(f"access:{access}") if access else None
    claims = json.loads(raw) if raw else None
    # The family check makes sign-out and theft detection end every token at once.
    if not claims or not store.get(f"family:{claims['family']}"):
        raise HTTPException(401, "Please sign in.")
    return claims["customer_id"]


@app.get("/api/health")
def health(request: Request):
    return {"ok": True, "store": request.app.state.store.kind}


@app.post("/api/auth/login")
def login(body: Login, request: Request, response: Response):
    store = request.app.state.store
    # Counted per customer ID: behind the Next.js proxy every browser shares one client IP.
    _limit(store, f"login:{body.customer_id.upper()}", LOGIN_PER_MINUTE)
    # Demo credentials: every synthetic customer shares DEMO_PASSWORD. A bank would use its own identity provider.
    password = os.environ.get("DEMO_PASSWORD", "demo1234")
    if not (tools.customer_exists(body.customer_id) and
            hmac.compare_digest(body.password.encode(), password.encode())):
        raise HTTPException(401, "Customer ID or password is incorrect.")
    family = secrets.token_urlsafe(16)
    store.set(f"family:{family}", body.customer_id, ttl=SESSION_MAX_S)
    _issue_tokens(store, response, body.customer_id, family)
    return {"customer_id": body.customer_id}


@app.post("/api/auth/refresh")
def refresh(request: Request, response: Response, refresh_token: str | None = Cookie(default=None, alias="refresh")):
    store = request.app.state.store
    raw = store.take(f"refresh:{refresh_token}") if refresh_token else None
    if raw is None:
        used = store.get(f"used:{refresh_token}") if refresh_token else None
        if used:
            used = json.loads(used)
            if time.time() - used["at"] < REUSE_GRACE_S:
                # Another tab of the same browser refreshed a moment ago and the cookies are already
                # new. Not theft: leave the session and the new cookies alone, and let the page retry.
                raise HTTPException(401, "Please retry.")
            store.delete(f"family:{used['family']}")  # an old token came back: assume theft and end the session
        _clear_cookies(response)
        raise HTTPException(401, "Please sign in.")
    claims = json.loads(raw)
    store.set(f"used:{refresh_token}", json.dumps({"family": claims["family"], "at": time.time()}), ttl=REFRESH_TTL_S)
    if not store.get(f"family:{claims['family']}"):
        _clear_cookies(response)
        raise HTTPException(401, "Please sign in.")
    _issue_tokens(store, response, claims["customer_id"], claims["family"])
    return {"ok": True}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, access: str | None = Cookie(default=None)):
    store = request.app.state.store
    raw = store.get(f"access:{access}") if access else None
    if raw:
        store.delete(f"family:{json.loads(raw)['family']}")
    _clear_cookies(response)
    return {"ok": True}


@app.get("/api/me")
def me(customer_id: str = Depends(current_customer)):
    lookup = fetch_account(customer_id)
    account = lookup.account or {}
    # The customer may see their own name and card; the LLM never receives the name.
    return {"customer_id": customer_id, "name": account.get("name"), "card_product": account.get("card_product")}


@app.get("/api/history")
def history(request: Request, customer_id: str = Depends(current_customer)):
    return {"messages": request.app.state.store.items(f"history:{customer_id}")}


@app.post("/api/feedback")
def feedback(body: Feedback, request: Request, customer_id: str = Depends(current_customer)):
    store = request.app.state.store
    _limit(store, f"feedback:{customer_id}", FEEDBACK_PER_MINUTE)
    # Only answers in this customer's own history can be rated.
    mine = {m.get("meta", {}).get("trace_id") for m in store.items(f"history:{customer_id}")}
    if body.trace_id not in mine:
        raise HTTPException(404, "Answer not found.")
    # A file next to the traces, so ratings last and join to the full trace by trace_id.
    # No customer_id: the trace already links to the customer.
    line = json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "trace_id": body.trace_id, "helpful": body.helpful})
    path = Path(os.environ.get("FEEDBACK_FILE", ROOT / "traces" / "feedback.jsonl"))
    path.parent.mkdir(exist_ok=True)
    with _feedback_lock, path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return {"ok": True}


@app.delete("/api/history")
def clear_history(request: Request, customer_id: str = Depends(current_customer)):
    # Clears the chat on screen only; traces are kept as the audit record.
    request.app.state.store.delete(f"history:{customer_id}")
    return {"ok": True}


@app.post("/api/chat")
def chat(body: Question, request: Request, customer_id: str = Depends(current_customer)):
    # A plain def runs in FastAPI's thread pool, so a slow model call doesn't block other requests.
    store = request.app.state.store
    _limit(store, f"chat:{customer_id}", CHAT_PER_MINUTE)
    result = request.app.state.agent.answer(customer_id, body.question)
    usage = result.trace["usage"]
    reply = {
        "role": "agent",
        "status": result.status,
        "path": result.path,
        "message": result.customer_message,  # rendered by pipeline.render; the UI only styles it
        "reason_codes": result.reason_codes,
        "requests": [{"request_id": r["request_id"], "queue": r["queue"]} for r in result.service_requests],
        "meta": {"ms": result.trace["total_ms"], "llm_calls": usage["llm_calls"],
                 "cost_usd": usage["cost_usd"], "trace_id": result.trace["trace_id"]},
    }
    key = f"history:{customer_id}"
    store.push(key, {"role": "customer", "text": body.question}, keep=HISTORY_KEEP, ttl=HISTORY_TTL_S)
    store.push(key, reply, keep=HISTORY_KEEP, ttl=HISTORY_TTL_S)
    return reply
