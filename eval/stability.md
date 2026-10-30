# Eval stability

Three full runs on the primary model (`openai/gpt-5.4-mini`) and one on the fallback (`openai/gpt-4.1-mini`), same code and prompt. `eval/results.md` is the last primary run.

| Run | Passed | Cost | LLM calls | Validator rejections |
|---|---|---|---|---|
| primary 1 | 27/30 | $0.0716 | 35 | 5 |
| primary 2 | 30/30 | $0.0448 | 36 | 6 |
| primary 3 | 29/30 | $0.0486 | 36 | 5 |
| fallback | 24/30 | $0.0290 | 34 | 6 |

Cases that did not pass every run (P pass, F fail):

| Case | Primary 1 | Primary 2 | Primary 3 | Fallback | Failure |
|---|---|---|---|---|---|
| EV-005 | F | P | F | P | status raise_request != answer |
| EV-007 | P | P | P | F | status answer != raise_request; did not cite POL-SVC-006 |
| EV-012 | P | P | P | F | status raise_request != refuse |
| EV-014 | F | P | P | F | status answer != refuse |
| EV-022 | P | P | P | F | did not cite POL-SVC-006 |
| EV-024 | P | P | P | F | did not cite POL-SVC-006 |
| EV-025 | F | P | P | F | status raise_request != refuse; status answer != refuse |
