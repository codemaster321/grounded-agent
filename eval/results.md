# Eval results

**28/30 passed (93%)** · seed: 11/12 · own: 17/18

Cost: $0.0399 total, $0.0013 per question · Latency: p50 2888ms, max 9719ms · LLM calls: 33 · Validator rejections: 3 · Cases hit by an LLM outage: 0

| Case | Result | Expected | Got | Path | Queues | Cited | ms | Failures |
|---|---|---|---|---|---|---|---|---|
| EV-001 | ✅ | answer | answer | llm |  | POL-FEE-007 | 5796 |  |
| EV-002 | ✅ | decline_with_reason | decline_with_reason | rules |  | POL-CRD-001, POL-SVC-005 | 408 |  |
| EV-003 | ✅ | decline_with_reason | decline_with_reason | rules |  | POL-CON-004, POL-CRD-001 | 407 |  |
| EV-004 | ✅ | decline_with_reason | decline_with_reason | rules |  | POL-CRD-001 | 407 |  |
| EV-005 | ❌ | answer | raise_request | llm | CREDIT_OPS | POL-CRD-003 | 6154 | status raise_request != answer |
| EV-006 | ✅ | decline_with_reason | decline_with_reason | rules |  | POL-KYC-008 | 407 |  |
| EV-007 | ✅ | raise_request | raise_request | llm | DISPUTES | POL-SVC-005, POL-SVC-006 | 9719 |  |
| EV-008 | ✅ | answer | answer | llm |  | POL-PRD-010 | 2888 |  |
| EV-009 | ✅ | answer | answer | llm |  | POL-FEE-007 | 3670 |  |
| EV-010 | ✅ | refuse | refuse | llm | GENERAL | POL-PRD-010 | 3039 |  |
| EV-011 | ✅ | refuse | refuse | llm | GENERAL | POL-GOV-009 | 2885 |  |
| EV-012 | ✅ | refuse | refuse | llm | GENERAL |  | 7043 |  |
| EV-013 | ✅ | answer | answer | llm |  | POL-PRD-010 | 2436 |  |
| EV-014 | ❌ | refuse | answer | llm | GENERAL | POL-PRD-010 | 4822 | status answer != refuse |
| EV-015 | ✅ | answer | answer | llm |  | POL-FEE-007 | 2818 |  |
| EV-016 | ✅ | answer | answer | llm |  | POL-FEE-007 | 2885 |  |
| EV-017 | ✅ | raise_request | raise_request | llm | CREDIT_OPS | POL-SVC-006 | 6559 |  |
| EV-018 | ✅ | raise_request | raise_request | llm | CREDIT_OPS | POL-SVC-006 | 6033 |  |
| EV-019 | ✅ | refuse | refuse | customer_not_found |  |  | 402 |  |
| EV-020 | ✅ | decline_with_reason | decline_with_reason | rules |  | POL-CRD-001, POL-SVC-005 | 410 |  |
| EV-021 | ✅ | decline_with_reason | decline_with_reason | rules |  | POL-CRD-001 | 409 |  |
| EV-022 | ✅ | raise_request | raise_request | llm | CARDS_URGENT | POL-SVC-006 | 7987 |  |
| EV-023 | ✅ | answer | answer | llm |  | POL-FEE-007 | 2376 |  |
| EV-024 | ✅ | raise_request | raise_request | llm | COMPLAINTS | POL-SVC-006 | 5096 |  |
| EV-025 | ✅ | refuse | refuse | llm | GENERAL | POL-CRD-001, POL-GOV-009 | 2559 |  |
| EV-026 | ✅ | refuse | refuse | llm | GENERAL |  | 2888 |  |
| EV-027 | ✅ | raise_request | raise_request | llm | GENERAL | POL-FEE-007, POL-SVC-006 | 9675 |  |
| EV-028 | ✅ | answer | answer | llm |  | POL-FEE-007 | 2316 |  |
| EV-029 | ✅ | answer | answer | llm |  | POL-FEE-007 | 3683 |  |
| EV-030 | ✅ | refuse | refuse | llm | GENERAL | POL-GOV-009 | 2412 |  |
