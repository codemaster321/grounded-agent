# Eval results

**29/30 passed (97%)** · seed: 11/12 · own: 18/18

Cost: $0.0486 total, $0.0016 per question · Latency: p50 3077ms, max 10828ms · LLM calls: 36 · Validator rejections: 5

| Case | Result | Expected | Got | Path | Queues | Cited | ms | Failures |
|---|---|---|---|---|---|---|---|---|
| EV-001 | ✅ | answer | answer | llm |  | POL-FEE-007 | 6159 |  |
| EV-002 | ✅ | decline_with_reason | decline_with_reason | rules |  | POL-CRD-001, POL-SVC-005 | 3320 |  |
| EV-003 | ✅ | decline_with_reason | decline_with_reason | rules |  | POL-CON-004, POL-CRD-001 | 407 |  |
| EV-004 | ✅ | decline_with_reason | decline_with_reason | rules |  | POL-CRD-001 | 408 |  |
| EV-005 | ❌ | answer | raise_request | llm | CREDIT_OPS | POL-CRD-003 | 7501 | status raise_request != answer |
| EV-006 | ✅ | decline_with_reason | decline_with_reason | rules |  | POL-KYC-008 | 407 |  |
| EV-007 | ✅ | raise_request | raise_request | llm | DISPUTES | POL-SVC-005, POL-SVC-006 | 8549 |  |
| EV-008 | ✅ | answer | answer | llm |  | POL-PRD-010 | 3051 |  |
| EV-009 | ✅ | answer | answer | llm |  | POL-FEE-007 | 2397 |  |
| EV-010 | ✅ | refuse | refuse | llm | GENERAL |  | 3373 |  |
| EV-011 | ✅ | refuse | refuse | llm | GENERAL | POL-GOV-009 | 2946 |  |
| EV-012 | ✅ | refuse | refuse | llm | GENERAL | POL-SVC-005 | 8087 |  |
| EV-013 | ✅ | answer | answer | llm |  | POL-PRD-010 | 2709 |  |
| EV-014 | ✅ | refuse | refuse | llm | GENERAL | POL-PRD-010 | 3077 |  |
| EV-015 | ✅ | answer | answer | llm |  | POL-FEE-007 | 3371 |  |
| EV-016 | ✅ | answer | answer | llm |  | POL-FEE-007 | 4337 |  |
| EV-017 | ✅ | raise_request | raise_request | llm | CREDIT_OPS | POL-CRD-001, POL-SVC-006 | 8420 |  |
| EV-018 | ✅ | raise_request | raise_request | llm | CREDIT_OPS | POL-SVC-006 | 10828 |  |
| EV-019 | ✅ | refuse | refuse | customer_not_found |  |  | 401 |  |
| EV-020 | ✅ | decline_with_reason | decline_with_reason | rules |  | POL-CRD-001, POL-SVC-005 | 414 |  |
| EV-021 | ✅ | decline_with_reason | decline_with_reason | rules |  | POL-CRD-001 | 411 |  |
| EV-022 | ✅ | raise_request | raise_request | llm | CARDS_URGENT | POL-SVC-006 | 5992 |  |
| EV-023 | ✅ | answer | answer | llm |  | POL-FEE-007 | 2298 |  |
| EV-024 | ✅ | raise_request | raise_request | llm | COMPLAINTS | POL-SVC-006 | 6818 |  |
| EV-025 | ✅ | refuse | refuse | llm | GENERAL | POL-CRD-001, POL-GOV-009 | 2897 |  |
| EV-026 | ✅ | refuse | refuse | llm | GENERAL |  | 2834 |  |
| EV-027 | ✅ | raise_request | raise_request | llm | GENERAL | POL-FEE-007, POL-SVC-006 | 6129 |  |
| EV-028 | ✅ | answer | answer | llm |  | POL-FEE-007 | 2243 |  |
| EV-029 | ✅ | answer | answer | llm | GENERAL | POL-FEE-007 | 3649 |  |
| EV-030 | ✅ | refuse | refuse | llm | GENERAL | POL-GOV-009 | 2890 |  |
