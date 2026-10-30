"""Ask the agent one question.

  python -m agent.cli CUST-2000 "My annual fee was charged, I thought it was waived."
  python -m agent.cli CUST-2000 "..." --trace     # also print the full trace record
"""
import argparse
import json
import os

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from agent.pipeline import Agent  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("customer_id")
    parser.add_argument("question")
    parser.add_argument("--trace", action="store_true", help="print the full trace record")
    args = parser.parse_args()

    result = Agent().answer(args.customer_id, args.question)
    usage = result.trace["usage"]
    print(result.customer_message)
    print(f"\n--- status={result.status} path={result.path} reason_codes={result.reason_codes} "
          f"cited={result.cited_docs}")
    print(f"--- trace={result.trace['trace_id']} {result.trace['total_ms']}ms llm_calls={usage['llm_calls']} "
          f"tokens={usage['input_tokens']}+{usage['output_tokens']} cost=${usage['cost_usd']:.5f} "
          f"prompt={result.trace['prompt_version']} errors={len(result.trace['errors'])}")
    if args.trace:
        print(json.dumps(result.trace, indent=2, default=str))


if __name__ == "__main__":
    main()
