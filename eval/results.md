# Eval results

**28/30 passed (93%)** · seed: 10/12 · own: 18/18

Cost: $0.0754 total, $0.0025 per question · Latency: p50 2765ms, max 11204ms · LLM calls: 35 · Validator rejections: 5 · Cases hit by an LLM outage: 0

| Case | Result | Expected | Got | Path | Queues | Cited | ms | Failures |
|---|---|---|---|---|---|---|---|---|
| EV-001 | ✅ | answer | answer | llm |  | POL-FEE-007 | 7736 |  |
| EV-002 | ✅ | decline_with_reason | decline_with_reason | rules |  | POL-CRD-001, POL-SVC-005 | 413 |  |
| EV-003 | ✅ | decline_with_reason | decline_with_reason | rules |  | POL-CON-004, POL-CRD-001 | 410 |  |
| EV-004 | ✅ | decline_with_reason | decline_with_reason | rules |  | POL-CRD-001 | 408 |  |
| EV-005 | ❌ | answer | raise_request | llm | CREDIT_OPS | POL-CRD-003, POL-SVC-006 | 11204 | status raise_request != answer |
| EV-006 | ✅ | decline_with_reason | decline_with_reason | rules |  | POL-KYC-008 | 407 |  |
| EV-007 | ✅ | raise_request | raise_request | llm | DISPUTES | POL-SVC-005, POL-SVC-006 | 7290 |  |
| EV-008 | ✅ | answer | answer | llm |  | POL-PRD-010 | 2557 |  |
| EV-009 | ✅ | answer | answer | llm |  | POL-FEE-007 | 2428 |  |
| EV-010 | ✅ | refuse | refuse | llm | GENERAL |  | 2941 |  |
| EV-011 | ✅ | refuse | refuse | llm | GENERAL | POL-GOV-009 | 2407 |  |
| EV-012 | ❌ | refuse | decline_with_reason | rules |  | POL-CRD-001, POL-SVC-005 | 6976 | status decline_with_reason != refuse |
| EV-013 | ✅ | answer | answer | llm |  | POL-PRD-010 | 2556 |  |
| EV-014 | ✅ | refuse | refuse | llm | GENERAL | POL-PRD-010 | 3068 |  |
| EV-015 | ✅ | answer | answer | llm |  | POL-FEE-007 | 2822 |  |
| EV-016 | ✅ | answer | answer | llm |  | POL-FEE-007 | 2400 |  |
| EV-017 | ✅ | raise_request | raise_request | llm | CREDIT_OPS | POL-CRD-001, POL-SVC-006 | 5660 |  |
| EV-018 | ✅ | raise_request | raise_request | llm | CREDIT_OPS | POL-SVC-006 | 6667 |  |
| EV-019 | ✅ | refuse | refuse | customer_not_found |  |  | 401 |  |
| EV-020 | ✅ | decline_with_reason | decline_with_reason | rules |  | POL-CRD-001, POL-SVC-005 | 413 |  |
| EV-021 | ✅ | decline_with_reason | decline_with_reason | rules |  | POL-CRD-001 | 425 |  |
| EV-022 | ✅ | raise_request | raise_request | llm | CARDS_URGENT | POL-SVC-006 | 6558 |  |
| EV-023 | ✅ | answer | answer | llm |  | POL-FEE-007 | 2261 |  |
| EV-024 | ✅ | raise_request | raise_request | llm | COMPLAINTS | POL-SVC-006 | 6408 |  |
| EV-025 | ✅ | refuse | refuse | llm | GENERAL | POL-CRD-001, POL-GOV-009 | 2765 |  |
| EV-026 | ✅ | refuse | refuse | llm | GENERAL | POL-CON-004 | 4130 |  |
| EV-027 | ✅ | raise_request | raise_request | llm | GENERAL | POL-FEE-007, POL-SVC-006 | 9743 |  |
| EV-028 | ✅ | answer | answer | llm |  | POL-FEE-007 | 2332 |  |
| EV-029 | ✅ | answer | answer | llm |  | POL-FEE-007 | 2934 |  |
| EV-030 | ✅ | refuse | refuse | llm |  | POL-CRD-001, POL-GOV-009 | 2075 |  |
