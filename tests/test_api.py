"""Web API: login, session-bound customer, history and rate limits. Fake LLM, memory store."""
import pytest
import redis
from fastapi.testclient import TestClient

from agent.pipeline import Agent
from api import main
from api.store import FallbackStore, MemoryStore
from tests.test_pipeline import ScriptedLLM, submit


@pytest.fixture(autouse=True)
def fast_tools(monkeypatch):
    monkeypatch.setenv("TOOL_LATENCY_S", "0")
    monkeypatch.setenv("TOOL_FAIL_RATE", "0")
    monkeypatch.setenv("DEMO_PASSWORD", "pw")


@pytest.fixture(scope="module")
def agent():
    return Agent(llm=None)


def client_for(agent, *turns):
    agent.llm = ScriptedLLM(*turns)
    main.app.state.store = MemoryStore()
    main.app.state.agent = agent
    return TestClient(main.app)


def signed_in(agent, *turns, customer_id="CUST-2007"):
    client = client_for(agent, *turns)
    assert client.post("/api/auth/login", json={"customer_id": customer_id, "password": "pw"}).status_code == 200
    return client


def markup():
    return [submit("answer", [("The foreign currency markup is 3.5%.", ["POL-FEE-007"])], intent="fees")]


@pytest.mark.parametrize("customer_id, password", [("CUST-2007", "wrong"), ("CUST-9999", "pw")])
def test_login_rejects_bad_credentials(agent, customer_id, password):
    client = client_for(agent)
    response = client.post("/api/auth/login", json={"customer_id": customer_id, "password": password})
    assert response.status_code == 401 and "access" not in response.cookies


def test_chat_needs_a_session(agent):
    assert client_for(agent).post("/api/chat", json={"question": "Hi"}).status_code == 401


def test_customer_comes_from_the_session_not_the_request(agent):
    client = signed_in(agent, customer_id="CUST-2003")
    response = client.post("/api/chat", json={"question": "Please increase my limit", "customer_id": "CUST-2000"})
    assert response.json()["path"] == "rules" and "open dispute" in response.json()["message"]


def test_chat_answer_and_history(agent):
    client = signed_in(agent, markup())
    reply = client.post("/api/chat", json={"question": "What is the markup abroad?"}).json()
    assert reply["status"] == "answer" and "3.5%" in reply["message"] and reply["meta"]["llm_calls"] == 1
    roles = [m["role"] for m in client.get("/api/history").json()["messages"]]
    assert roles == ["customer", "agent"]


def test_logout_ends_the_session(agent):
    client = signed_in(agent)
    client.post("/api/auth/logout")
    assert client.get("/api/me").status_code == 401


def refresh_cookie(client):
    return next(c.value for c in client.cookies.jar if c.name == "refresh")


def test_expired_access_token_is_renewed_by_refresh(agent):
    client = signed_in(agent)
    main.app.state.store._data = {k: v for k, v in main.app.state.store._data.items() if not k.startswith("access:")}
    assert client.get("/api/me").status_code == 401
    assert client.post("/api/auth/refresh").status_code == 200
    assert client.get("/api/me").json()["customer_id"] == "CUST-2007"


def test_refresh_token_works_once(agent):
    client = signed_in(agent)
    old = refresh_cookie(client)
    assert client.post("/api/auth/refresh").status_code == 200
    assert refresh_cookie(client) != old


def test_second_tab_refreshing_at_the_same_moment_is_not_theft(agent):
    client = signed_in(agent)
    old = refresh_cookie(client)
    assert client.post("/api/auth/refresh").status_code == 200  # tab 1
    other_tab = TestClient(main.app)
    other_tab.cookies.set("refresh", old, path="/api/auth")
    assert other_tab.post("/api/auth/refresh").status_code == 401  # tab 2 retries with the new cookies instead
    assert client.get("/api/me").status_code == 200


def test_redis_failing_while_running_falls_back_to_memory(agent):
    class Broken:
        def __getattr__(self, name):
            def fail(*args, **kwargs):
                raise redis.ConnectionError("Redis went away")
            return fail

    client = client_for(agent)
    main.app.state.store = FallbackStore(Broken())
    assert client.post("/api/auth/login", json={"customer_id": "CUST-2007", "password": "pw"}).status_code == 200
    assert client.get("/api/me").status_code == 200
    assert client.get("/api/health").json()["store"] == "memory (Redis lost)"


def test_reused_refresh_token_ends_the_session(agent, monkeypatch):
    monkeypatch.setattr(main, "REUSE_GRACE_S", 0)
    client = signed_in(agent)
    stolen = refresh_cookie(client)
    assert client.post("/api/auth/refresh").status_code == 200  # the real user rotates first
    thief = TestClient(main.app)
    thief.cookies.set("refresh", stolen, path="/api/auth")
    assert thief.post("/api/auth/refresh").status_code == 401
    assert client.get("/api/me").status_code == 401  # the real user's tokens stop working too
    assert client.post("/api/auth/refresh").status_code == 401


def test_logins_are_rate_limited_per_customer(agent, monkeypatch):
    monkeypatch.setattr(main, "LOGIN_PER_MINUTE", 2)
    client = client_for(agent)
    codes = [client.post("/api/auth/login", json={"customer_id": "CUST-2007", "password": "x"}).status_code
             for _ in range(3)]
    assert codes == [401, 401, 429]
    assert client.post("/api/auth/login", json={"customer_id": "CUST-2003", "password": "pw"}).status_code == 200


def test_chat_is_rate_limited(agent, monkeypatch):
    monkeypatch.setattr(main, "CHAT_PER_MINUTE", 1)
    client = signed_in(agent, customer_id="CUST-2003")
    assert client.post("/api/chat", json={"question": "Please increase my limit"}).status_code == 200
    assert client.post("/api/chat", json={"question": "Please increase my limit"}).status_code == 429
