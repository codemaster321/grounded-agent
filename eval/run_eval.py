"""Run every case in eval/cases.csv through the real agent and score it.

  python -m eval.run_eval                 # all cases
  python -m eval.run_eval EV-004 EV-012   # selected cases

Writes eval/results.md and eval/results.jsonl. Exits 1 if the pass rate is below
EVAL_MIN_PASS (default 0.8): this is the CI gate.

A case passes only if every check passes: status, routing queue, cited documents,
required phrases and forbidden phrases. Numbers are compared with commas removed,
so "1,62,000" matches "162000".
"""
import csv
import json
import os
import sys
import time

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("TOOL_SEED", "7")

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from agent.corpus import ROOT  # noqa: E402
from agent.pipeline import Agent  # noqa: E402

EVAL_DIR = ROOT / "eval"


def _norm(text: str) -> str:
    # "6-month" and "6 months" both contain "6 month"
    return text.lower().replace(",", "").replace("-", " ")


def check(case: dict, result) -> list[str]:
    failures = []
    if result.status != case["expected_behaviour"]:
        failures.append(f"status {result.status} != {case['expected_behaviour']}")
    queues = [r["queue"] for r in result.service_requests]
    if case["expected_queue"] and case["expected_queue"] not in queues:
        failures.append(f"queue {case['expected_queue']} not in {queues}")
    for doc in filter(None, case["grounding_docs"].split(",")):
        if doc not in result.cited_docs:
            failures.append(f"did not cite {doc}")
    message = _norm(result.customer_message)
    for phrase in filter(None, case["must_include"].split("|")):
        if _norm(phrase) not in message:
            failures.append(f"missing {phrase!r}")
    for phrase in filter(None, case["must_not_include"].split("|")):
        if _norm(phrase) in message:
            failures.append(f"contains forbidden {phrase!r}")
    return failures


def main(selected: list[str]):
    cases = list(csv.DictReader((EVAL_DIR / "cases.csv").open(encoding="utf-8")))
    if selected:
        cases = [c for c in cases if c["case_id"] in selected]
    agent = Agent()
    rows = []
    for case in cases:
        os.environ["TOOL_FAIL_RATE"] = case["tool_fail_rate"] or "0"
        os.environ["TOOL_LATENCY_S"] = "0.4"
        start = time.perf_counter()
        result = agent.answer(case["customer_id"], case["question"])
        failures = check(case, result)
        usage = result.trace["usage"]
        rows.append({
            "case_id": case["case_id"], "source": case["source"], "passed": not failures, "failures": failures,
            "expected": case["expected_behaviour"], "status": result.status, "path": result.path,
            "queues": [r["queue"] for r in result.service_requests], "cited": result.cited_docs,
            "ms": round((time.perf_counter() - start) * 1000), "llm_calls": usage["llm_calls"],
            "tokens": usage["input_tokens"] + usage["output_tokens"], "cost_usd": usage["cost_usd"],
            "rejections": sum("answer rejected" in e for e in result.trace["errors"]),
            "outage": result.trace.get("fallback_reason") == "llm_unavailable",
            "trace_id": result.trace["trace_id"], "message": result.customer_message,
        })
        print(f"{'PASS' if not failures else 'FAIL'} {case['case_id']} {result.status:20} {rows[-1]['ms']:>6}ms {failures}")

    passed = sum(r["passed"] for r in rows)
    rate = passed / len(rows)
    write_report(rows, rate)
    threshold = float(os.environ.get("EVAL_MIN_PASS", "0.8"))
    outages = sum(r["outage"] for r in rows)
    print(f"\n{passed}/{len(rows)} passed ({rate:.0%}); gate {threshold:.0%}; {outages} cases hit an LLM outage")
    sys.exit(0 if rate >= threshold else 1)


def write_report(rows: list[dict], rate: float):
    with (EVAL_DIR / "results.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    latencies = sorted(r["ms"] for r in rows)
    by_source = {s: [r for r in rows if r["source"] == s] for s in ("seed", "own")}
    lines = [
        "# Eval results", "",
        f"**{sum(r['passed'] for r in rows)}/{len(rows)} passed ({rate:.0%})** · "
        + " · ".join(f"{s}: {sum(r['passed'] for r in rs)}/{len(rs)}" for s, rs in by_source.items() if rs),
        "",
        f"Cost: ${sum(r['cost_usd'] for r in rows):.4f} total, ${sum(r['cost_usd'] for r in rows) / len(rows):.4f} per question · "
        f"Latency: p50 {latencies[len(latencies) // 2]}ms, max {latencies[-1]}ms · "
        f"LLM calls: {sum(r['llm_calls'] for r in rows)} · Validator rejections: {sum(r['rejections'] for r in rows)} · "
        f"Cases hit by an LLM outage: {sum(r['outage'] for r in rows)}",
        "",
        "| Case | Result | Expected | Got | Path | Queues | Cited | ms | Failures |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['case_id']} | {'✅' if r['passed'] else '❌'} | {r['expected']} | {r['status']} | {r['path']} | "
                     f"{', '.join(r['queues'])} | {', '.join(r['cited'])} | {r['ms']} | {'; '.join(r['failures'])} |")
    (EVAL_DIR / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
