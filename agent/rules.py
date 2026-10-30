"""Hard policy rules, evaluated in code from account state.

Why in code: retrieval cannot find these policies from the question alone. "Can you
increase my limit?" never mentions a vulnerable flag or a dispute, so the deciding
policy is not in the top-k (measured: EV-002/003/006 miss it). The account state is what
triggers them, so code checks the account and attaches the citation itself.

Only POL-CRD-001 s.3 "mandatory declines, without discretion" (plus POL-KYC-008) are
automated here. Everything else about an increase (income, debt-burden ratio) needs data
we do not have, so it is referred to a human, never approved.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

KYC_REFRESH_YEARS = {"high": 2, "medium": 8, "low": 10}  # POL-KYC-008
KYC_GRACE_DAYS = 90
INCREASE_BAR_MONTHS = 6  # POL-CRD-001 s.3; POL-CRD-011 says 3 but is overridden (see corpus_manifest.json)
THIN_FILE_MONTHS = 6  # POL-CRD-003 s.5


@dataclass(frozen=True)
class Finding:
    rule: str
    outcome: Literal["decline", "refer"]
    reason_code: str | None  # POL-GOV-009 code; None where no approved code fits
    citations: tuple[str, ...]  # policy chunk ids and account.<field> references
    fact: str  # customer-safe wording: no scores, no flags named that the customer shouldn't see


def _add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 Feb
        return d.replace(year=d.year + years, day=28)


def _months_before(d: date, months: int) -> date:
    year, month = divmod(d.year * 12 + d.month - 1 - months, 12)
    month += 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    raise AssertionError("unreachable")


def limit_increase_findings(account: dict, today: date) -> list[Finding]:
    findings = []

    if account["vulnerable_flag"]:
        # Gap in the corpus: POL-GOV-009 requires an approved reason code, and none covers
        # this. Naming the flag to the customer is itself a conduct risk, so the fact is generic.
        findings.append(Finding(
            "vulnerable_customer", "decline", None,
            ("POL-CON-004", "POL-CRD-001#3"),
            "We are not able to increase your credit limit at the moment.",
        ))

    if account["open_dispute"]:
        findings.append(Finding(
            "open_dispute", "decline", "AA04",
            ("POL-CRD-001#3", "POL-SVC-005", "account.open_dispute"),
            "There is an open dispute on your account, and a limit increase cannot be processed while a dispute is open.",
        ))

    last = account["last_limit_increase_date"]
    if last and date.fromisoformat(last) > _months_before(today, INCREASE_BAR_MONTHS):
        findings.append(Finding(
            "recent_increase", "decline", "AA05",
            ("POL-CRD-001#3", "account.last_limit_increase_date"),
            f"Your limit was last increased on {last}, and a further increase needs at least 6 months since the last one.",
        ))

    kyc_due = _add_years(date.fromisoformat(account["kyc_last_done"]), KYC_REFRESH_YEARS[account["kyc_risk_band"]])
    if today > kyc_due + timedelta(days=KYC_GRACE_DAYS):
        findings.append(Finding(
            "rekyc_overdue", "decline", "AA06",
            ("POL-KYC-008", "account.kyc_last_done"),
            "We need to refresh the identity (KYC) information we hold for you before your limit can be increased. Your existing limit and account are not affected.",
        ))

    if account["months_repayment_history"] < THIN_FILE_MONTHS:
        # "Thin-file" also needs no bureau record (or < 2 trade lines). We have no bureau
        # data, so this says "may be" and refers rather than asserting it.
        findings.append(Finding(
            "possible_thin_file", "refer", "AA03",
            ("POL-CRD-003#5", "account.months_repayment_history"),
            f"You have {account['months_repayment_history']} months of repayment history with us. With less than 6 months of history, "
            "any increase may be capped at 1.25 times your current limit and must be reviewed by a credit officer.",
        ))

    return findings
