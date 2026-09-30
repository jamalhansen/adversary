"""Pure domain logic for adversary -- no CLI/Typer imports here."""

import json
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from local_first_common.providers.base import BaseProvider

from .prompts import (
    PITCH_SYSTEM,
    REBUT_SYSTEM,
    REVIEW_SYSTEM,
    build_pitch_user,
    build_rebut_user,
    build_review_user,
)
from .schema import AdversaryReport, Challenge, RebuttalReport, Ruling

Mode = Literal["review", "pitch"]

MAX_INPUT_CHARS = 60_000
STATE_DIR = Path(os.environ.get("ADVERSARY_STATE_DIR", "~/.local/state/adversary")).expanduser()


class AdversaryError(Exception):
    """Base typed error for adversary."""


class EmptyInputError(AdversaryError):
    """Nothing to argue against."""


class NoSessionError(AdversaryError):
    """`rebut` was called with no prior review/pitch to rebut."""


@dataclass
class Session:
    mode: Mode
    input_text: str
    report: dict


def git_diff(diff_range: str | None = None, cwd: Path | None = None) -> str:
    args = ["git", "diff", diff_range or "HEAD"]
    proc = subprocess.run(args, capture_output=True, text=True, cwd=cwd, check=False)
    if proc.returncode != 0:
        raise AdversaryError(f"`{' '.join(args)}` failed: {proc.stderr.strip()}")
    if not proc.stdout.strip():
        hint = "" if diff_range else " (no uncommitted changes -- try --range HEAD~1 for the last commit)"
        raise EmptyInputError(f"`{' '.join(args)}` produced an empty diff{hint}")
    return proc.stdout


def truncate(text: str, limit: int = MAX_INPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[... truncated {len(text) - limit} characters; argue only from what is shown ...]"


def mock_report() -> AdversaryReport:
    return AdversaryReport(
        strongest_objection="[LLM MOCK RESPONSE]",
        unexamined_assumption="[LLM MOCK RESPONSE]",
        challenges=[
            Challenge(
                claim="[LLM MOCK RESPONSE]",
                evidence="[LLM MOCK RESPONSE]",
                why_it_matters="[LLM MOCK RESPONSE]",
                refutation_test="[LLM MOCK RESPONSE]",
                severity="worth-checking",
            )
        ],
        better_alternative="[LLM MOCK RESPONSE]",
    )


def mock_rebuttal(report: AdversaryReport) -> RebuttalReport:
    return RebuttalReport(
        rulings=[Ruling(challenge=i, verdict="hold", reasoning="[LLM MOCK RESPONSE]") for i in range(1, len(report.challenges) + 1)],
        remaining_objection="[LLM MOCK RESPONSE]",
    )


def argue(provider: BaseProvider | None, mode: Mode, input_text: str, context: str = "") -> AdversaryReport:
    """provider=None means --no-llm: return a mock report without calling anything."""
    if not input_text.strip():
        raise EmptyInputError("Nothing to argue against: the input is empty.")
    if provider is None:
        return mock_report()
    if mode == "review":
        system, user = REVIEW_SYSTEM, build_review_user(truncate(input_text), context)
    else:
        system, user = PITCH_SYSTEM, build_pitch_user(truncate(input_text))
    report = provider.complete(system, user, response_model=AdversaryReport)
    report.challenges = report.challenges[:5]
    return report


def rebut(provider: BaseProvider | None, session: Session, response: str) -> RebuttalReport:
    report = AdversaryReport.model_validate(session.report)
    if not response.strip():
        raise EmptyInputError("Your rebuttal is empty.")
    if provider is None:
        return mock_rebuttal(report)
    user = build_rebut_user(truncate(session.input_text), report.model_dump_json(indent=2), response)
    return provider.complete(REBUT_SYSTEM, user, response_model=RebuttalReport)


def save_session(session: Session, state_dir: Path | None = None) -> Path:
    state_dir = state_dir or STATE_DIR
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "last.json"
    path.write_text(json.dumps(asdict(session), indent=2), encoding="utf-8")
    return path


def load_session(state_dir: Path | None = None) -> Session:
    path = (state_dir or STATE_DIR) / "last.json"
    if not path.exists():
        raise NoSessionError("No previous `adversary review` or `adversary pitch` to rebut.")
    return Session(**json.loads(path.read_text(encoding="utf-8")))


def render_report(report: AdversaryReport) -> str:
    lines = [
        "## Strongest objection",
        report.strongest_objection,
        "",
        "## Unexamined assumption",
        report.unexamined_assumption,
        "",
        "## Challenges",
    ]
    for i, c in enumerate(report.challenges, start=1):
        lines += [
            f"### {i}. [{c.severity}] {c.claim}",
            f"> {c.evidence.strip()}",
            "",
            f"- **Why it matters:** {c.why_it_matters}",
            f"- **Prove me wrong:** {c.refutation_test}",
            "",
        ]
    lines += ["## What should have been built instead", report.better_alternative, ""]
    lines.append('Answer the challenges you disagree with: `adversary rebut "..."`')
    return "\n".join(lines) + "\n"


def render_rebuttal(report: AdversaryReport, rebuttal: RebuttalReport) -> str:
    marks = {"concede": "CONCEDED", "hold": "HOLDS", "escalate": "ESCALATED"}
    lines = ["## Rulings"]
    for r in rebuttal.rulings:
        claim = report.challenges[r.challenge - 1].claim if 0 < r.challenge <= len(report.challenges) else "(unknown challenge)"
        lines += [f"- **{r.challenge}. {marks[r.verdict]}** -- {claim}", f"  {r.reasoning}"]
    lines += ["", "## What still stands", rebuttal.remaining_objection]
    return "\n".join(lines) + "\n"
