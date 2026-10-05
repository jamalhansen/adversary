import subprocess

import pytest

from adversary.core import (
    EmptyInputError,
    NoSessionError,
    Session,
    argue,
    git_diff,
    load_session,
    mock_report,
    rebut,
    render_rebuttal,
    render_report,
    save_session,
    truncate,
)
from adversary.prompts import PITCH_SYSTEM, REBUT_SYSTEM, REVIEW_SYSTEM
from adversary.schema import AdversaryReport, Challenge, RebuttalReport, Ruling


def _challenge(i: int, severity="serious") -> Challenge:
    return Challenge(
        claim=f"claim {i}",
        evidence=f"line {i}",
        why_it_matters="it breaks",
        refutation_test="run the tests",
        severity=severity,
    )


def _report(n: int = 2) -> AdversaryReport:
    return AdversaryReport(
        strongest_objection="it solves the wrong problem",
        unexamined_assumption="callers pass UTC",
        challenges=[_challenge(i) for i in range(1, n + 1)],
        better_alternative="fix it at the source",
    )


class FakeProvider:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def complete(self, system, user, response_model=None):
        self.calls.append((system, user, response_model))
        return self.result


class TestArgue:
    def test_review_uses_review_prompt_with_intent(self):
        llm = FakeProvider(_report())
        argue(llm, "review", "diff --git a b", context="make it faster")
        system, user, model = llm.calls[0]
        assert system == REVIEW_SYSTEM
        assert "AUTHOR'S STATED INTENT:\nmake it faster" in user
        assert "diff --git a b" in user
        assert model is AdversaryReport

    def test_pitch_uses_pitch_prompt(self):
        llm = FakeProvider(_report())
        argue(llm, "pitch", "An app for X")
        assert llm.calls[0][0] == PITCH_SYSTEM

    def test_caps_challenges_at_five(self):
        report = argue(FakeProvider(_report(8)), "pitch", "idea")
        assert len(report.challenges) == 5

    def test_empty_input_raises(self):
        with pytest.raises(EmptyInputError):
            argue(FakeProvider(_report()), "pitch", "   ")

    def test_no_provider_returns_mock_without_calling(self):
        assert argue(None, "pitch", "idea") == mock_report()


class TestRebut:
    def test_sends_original_report_and_response(self):
        session = Session("review", "the diff", _report().model_dump())
        ruling = RebuttalReport(
            rulings=[Ruling(challenge=1, verdict="concede", reasoning="test passed")], remaining_objection="2 stands"
        )
        llm = FakeProvider(ruling)
        assert rebut(llm, session, "1: ran it, passes") is ruling
        system, user, model = llm.calls[0]
        assert system == REBUT_SYSTEM
        assert "the diff" in user and "claim 1" in user and "1: ran it, passes" in user
        assert model is RebuttalReport

    def test_empty_response_raises(self):
        with pytest.raises(EmptyInputError):
            rebut(FakeProvider(None), Session("pitch", "x", _report().model_dump()), "")

    def test_no_provider_holds_everything(self):
        result = rebut(None, Session("pitch", "x", _report(3).model_dump()), "no")
        assert [r.verdict for r in result.rulings] == ["hold"] * 3


class TestSession:
    def test_round_trip(self, tmp_path):
        session = Session("pitch", "idea", _report().model_dump())
        save_session(session, tmp_path)
        assert load_session(tmp_path) == session

    def test_missing_session_raises(self, tmp_path):
        with pytest.raises(NoSessionError):
            load_session(tmp_path)


class TestGitDiff:
    @pytest.fixture
    def repo(self, tmp_path):
        def git(*args):
            subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

        git("init", "-q")
        git("config", "user.email", "t@example.com")
        git("config", "user.name", "t")
        (tmp_path / "a.txt").write_text("one\n")
        git("add", ".")
        git("commit", "-qm", "init")
        return tmp_path

    def test_uncommitted_changes(self, repo):
        (repo / "a.txt").write_text("two\n")
        assert "+two" in git_diff(cwd=repo)

    def test_clean_tree_hints_at_range(self, repo):
        with pytest.raises(EmptyInputError, match="--range HEAD~1"):
            git_diff(cwd=repo)

    def test_bad_range_raises(self, repo):
        with pytest.raises(Exception, match="failed"):
            git_diff("nope..nada", cwd=repo)


def test_truncate_marks_the_cut():
    out = truncate("x" * 100, limit=10)
    assert out.startswith("x" * 10)
    assert "truncated 90 characters" in out


class TestRender:
    def test_report_has_falsifiable_challenges_and_alternative(self):
        text = render_report(_report(1))
        assert "## Strongest objection" in text
        assert "### 1. [serious] claim 1" in text
        assert "**Prove me wrong:** run the tests" in text
        assert "## What should have been built instead" in text

    def test_rebuttal_maps_rulings_to_claims(self):
        rebuttal = RebuttalReport(
            rulings=[
                Ruling(challenge=1, verdict="concede", reasoning="ok"),
                Ruling(challenge=9, verdict="hold", reasoning="?"),
            ],
            remaining_objection="nothing",
        )
        text = render_rebuttal(_report(1), rebuttal)
        assert "1. CONCEDED** -- claim 1" in text
        assert "(unknown challenge)" in text
