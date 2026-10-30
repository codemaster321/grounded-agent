"""Runtime settings, all overridable by env var (see .env.example).

AS_OF is injectable because the POL-CRD-001 vs POL-CRD-011 contradiction (6 vs 3 months
between increases) only shows for some dates. The default, 2026-10-30, puts CUST-2001's
last increase (2026-06-19) about 4 months back: allowed under the wrong rule, barred
under the right one. The eval pins this date.
"""
import os
from datetime import date

DEFAULT_AS_OF = "2026-10-30"
DEFAULT_PRIMARY_MODEL = "openai/gpt-5.4-mini"
DEFAULT_FALLBACK_MODEL = "openai/gpt-4.1-mini"


def as_of() -> date:
    return date.fromisoformat(os.environ.get("AS_OF", DEFAULT_AS_OF))


def models() -> list[str]:
    return [
        os.environ.get("PRIMARY_MODEL") or DEFAULT_PRIMARY_MODEL,
        os.environ.get("FALLBACK_MODEL") or DEFAULT_FALLBACK_MODEL,
    ]
