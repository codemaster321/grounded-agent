"""Minimal tracing: one JSON line per request in traces/traces.jsonl.

Each request gets a trace_id and a list of spans (name, duration, attributes, error).
Tokens and cost are summed across LLM calls. This is the shape OpenTelemetry would give
us; at this size a file is enough and nothing leaves the machine.
"""
import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from agent.corpus import ROOT

TRACE_FILE = ROOT / "traces" / "traces.jsonl"


class Trace:
    def __init__(self, customer_id: str, question: str, **attrs):
        self.record = {
            "trace_id": uuid.uuid4().hex[:12],
            "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "customer_id": customer_id,
            "question": question,
            **attrs,
            "spans": [],
            "usage": {"llm_calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
            "errors": [],
        }
        self._t0 = time.perf_counter()

    @property
    def trace_id(self) -> str:
        return self.record["trace_id"]

    @contextmanager
    def span(self, name: str, **attrs):
        span = {"name": name, **attrs}
        start = time.perf_counter()
        try:
            yield span
        except Exception as e:
            span["error"] = f"{type(e).__name__}: {e}"
            self.error(f"{name}: {span['error']}")
            raise
        finally:
            span["ms"] = round((time.perf_counter() - start) * 1000)
            self.record["spans"].append(span)

    def add_usage(self, input_tokens: int, output_tokens: int, cost_usd: float | None):
        usage = self.record["usage"]
        usage["llm_calls"] += 1
        usage["input_tokens"] += input_tokens
        usage["output_tokens"] += output_tokens
        if cost_usd is None:
            usage["cost_unknown"] = True
        else:
            usage["cost_usd"] = round(usage["cost_usd"] + cost_usd, 6)

    def error(self, message: str):
        self.record["errors"].append(message)

    def finish(self, **attrs) -> dict:
        self.record.update(attrs)
        self.record["total_ms"] = round((time.perf_counter() - self._t0) * 1000)
        path = Path(os.environ.get("TRACE_FILE", TRACE_FILE))
        path.parent.mkdir(exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(self.record, default=str) + "\n")
        return self.record
