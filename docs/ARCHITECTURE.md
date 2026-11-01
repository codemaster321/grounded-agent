# Architecture

## The one-line design

**The LLM explains; code decides.** Anything that would be a compliance breach if
wrong (declining a limit, who the customer is, which queue a request goes to, whether a
citation is real) is enforced in code. The LLM retrieves context, reasons, and phrases.

## Request flow

```
customer question + customer_id (from the session, never from the LLM)
        │
        ▼
 1. get_account_state ──timeout──► retry once ──fail──► account = UNAVAILABLE (degraded mode)
        │
        ▼
 2. hybrid retrieval over the policy corpus
      BM25 (keywords) + embeddings (meaning) ──► fused with RRF ──► top-k chunks
      non-policy docs (POL-OPS-012) are excluded from the index
        │
        ▼
 3. hard policy rules in code  (vulnerable flag, open dispute, 6-month bar, re-KYC overdue)
      each rule that fires carries its citation and its reason code
      limit request + mandatory decline ──► code states the decline, no LLM call, go to 6
      (if only the LLM spots the limit request, its answer is replaced the same way)
        │
        ▼
 4. LLM call ── structured output (Pydantic schema)
      may call tool: raise_service_request(category ∈ the 7 queues; customer_id injected)
        │
        ▼
 5. validator
      - schema valid?
      - every claim has ≥1 citation, and every citation is a policy chunk in context or a real account field?
      - every number in a claim appears in its cited sources?
      - no internal score, no vulnerable-flag disclosure, no "approved/actioned" wording?
      - no decline without a rule behind it from step 3?
      fail ──► retry once with the error ──fail──► safe message + GENERAL ticket
        │
        ▼
 6. response to customer  +  one trace record (spans, tokens, latency, cost, model, prompt version)
```

## Stack

| Concern | Choice | Why this and not the obvious alternative |
|---|---|---|
| Language | Python 3.12 | The ecosystem for this work |
| LLM access | **LiteLLM**, primary `gpt-5.4-mini` (reasoning effort low), fallback `gpt-4.1-mini` | One interface for any provider, token/cost reporting. The fallback chain is written out by hand so the trace says which model answered and why. It falls back **only on provider errors**: a bug in our code fails the same on every model, and falling back on it hid one during the build. Skipped LangChain: too much hidden magic to explain line by line |
| Agent loop | **Hand-written**, ~100 lines | We have to own the citation check and the retry; a framework would hide exactly the part being marked |
| Keyword search | `rank_bm25` | Catches exact terms like "Signature", "markup", "POL-CRD-001" that embeddings blur |
| Semantic search | `fastembed` (bge-small, runs locally on ONNX) | No API key, no 2 GB PyTorch install, works offline in CI |
| Fusion | Reciprocal Rank Fusion, written by hand | ~10 lines; BM25 and cosine scores aren't on the same scale, but ranks are |
| Vector store | **None**: a numpy array in memory | 12 documents. A vector DB here is premature; see "At 100x" below |
| Schema | Pydantic v2 | Validation errors double as retry feedback for the LLM |
| Tracing | Own `span()` context manager writing **JSONL** | Gives 90% of OpenTelemetry/Langfuse value at 5% of the setup; one line per request is easy to show the panel |
| Prompts | Files in `prompts/`, version = file name + content hash, logged on every trace | Lets us answer "which prompt produced this answer?" |
| Eval | CSV of cases + `pytest`-style runner; GitHub Actions gate on pass rate | Seeds plus our own 15+ cases |
| Interface | CLI, plus a small Streamlit chat page (`app.py`) | The brief asks for an agent, not a web app, so the page is a thin screen over the same `Agent.answer`. Production would need an API and a login |

## Key decisions 

1. **Mandatory declines are decided and worded in code.** Injection or a retrieval miss
   cannot talk the agent out of one. First version let the LLM word them and policed the
   wording; it produced a vague "a mandatory decline rule applies". Code stating them
   removed that failure class. Costs: the rules duplicate the corpus, so a policy change
   needs a code change (arguably correct in a bank), and a question mixing a limit request
   with something else gets only the decline.
2. **The agent cannot approve anything.** There is no approve tool, and approval needs
   income and a debt-burden ratio, which the data doesn't have. Outcomes are: answer,
   decline with a reason, refer to a human queue, or refuse. This also defuses the
   POL-OPS-012 injection by design.
3. **`customer_id` is bound server-side.** The LLM never chooses whose account is read
   or whom a request is raised for.
4. **Account state is fetched by code up front, not by the LLM.** Every question is about
   the customer's card, the rules in step 3 need it, and it saves one LLM round trip.
   `raise_service_request` *is* an LLM tool call because choosing the category is a judgement.
5. **Non-policy documents are excluded from the index.** POL-OPS-012 says "Not policy".
   For the Break section we can index it on purpose and show the other layers
   (no approve capability + output validator) still hold.
6. **Document precedence is metadata, not retrieval luck.** A small manifest records
   "POL-CRD-001 §3 overrides POL-CRD-011". In production this comes from the document
   management system.
7. **The clock is injectable (`AS_OF` date).** The 3-vs-6-month contradiction only matters
   for some dates; evals pin one.
8. **When the account tool fails, the customer is told plainly.** Policy-only questions are
   still answered; account-dependent ones get "I couldn't check your account just now" plus
   an offer to raise a request. Account state is never guessed.

9. **The LLM writes no free text.** It submits `claims` (sentence + citations); code renders
   the customer message from validated claims, plus fixed templates for routing and errors.
   Nothing reaches the customer that skipped the citation check.
10. **Data minimisation.** `behavioural_score` and `name` are never sent to the LLM, so it cannot
    leak them under any prompt or injection. The validator also checks for the score value.
11. **Fail closed.** Every failure path ends in a defined customer message: validation fails
    twice or both models down → safe message + GENERAL ticket; unknown customer → no LLM
    call at all. A mandatory decline needs no LLM, so it survives a model outage.
## Deliberately not built (argued in the README)

- **Streaming.** The full answer must pass the citation validator before the customer
  sees it. Streaming unvalidated tokens defeats that. Production option: stream after
  validation, or stream a "checking…" status.
- **Vector DB, API server, auth, UI.** Not what is being assessed at this size.
- **Response caching.** Answers depend on live account state, so cache hits are rare and
  stale answers are dangerous. We do cache corpus embeddings, and the static system
  prompt is ordered so provider-side prompt caching can hit it.

## At 100x corpus, split across tenants (Scale)

- Index per tenant, or one index with a mandatory `tenant_id` filter applied in code
  *before* retrieval. Never trust the LLM to filter.
- pgvector or OpenSearch (both do BM25 + vectors) replace the in-memory arrays.
- Embeddings computed at ingest, not at startup; re-embed only changed documents.
- Precedence/supersession metadata becomes mandatory at ingest, because contradictions
  grow with the corpus.
- Every cache key includes `tenant_id`.

## Cost, latency and concurrency (measured over 90 primary-model runs)

- **Cost:** about $0.0014 per question. Single-turn only, so cost per conversation is an estimate:
  about $0.004 for an assumed three questions.
- **Latency:** p50 2.9s, p95 9.7s, max 11.2s. Rule-based declines take about 0.4s (the
  simulated account call) and cost nothing: 18 of the 90 runs.
- **Biggest cost levers:** avoiding model calls (more rule paths) and the validator retry,
  which adds a whole extra call. Reasoning effort took one call from 21s to about 6s.
- **Concurrency:** not built or load-tested. Each request is blocking and sequential. The work
  is I/O-bound, so production would use async calls behind a per-provider rate limiter,
  with a limit on queued requests. Traces would go to a collector, not one shared file.
