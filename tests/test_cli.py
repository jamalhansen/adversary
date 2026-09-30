import json

import pytest
from typer.testing import CliRunner

from adversary import core
from adversary.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def state_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "STATE_DIR", tmp_path)
    return tmp_path


def test_pitch_no_llm_from_file(tmp_path):
    idea = tmp_path / "idea.md"
    idea.write_text("An app that does X")
    result = runner.invoke(app, ["pitch", str(idea), "--no-llm"])
    assert result.exit_code == 0
    assert "## Strongest objection" in result.output


def test_no_llm_implies_dry_run_so_no_session_saved(state_dir):
    runner.invoke(app, ["pitch", "--no-llm"], input="idea")
    assert not (state_dir / "last.json").exists()


def test_pitch_json_output_is_pure_json():
    result = runner.invoke(app, ["pitch", "--no-llm", "--json"], input="idea")
    assert json.loads(result.stdout)["challenges"]


def test_empty_pitch_exits_nonzero():
    result = runner.invoke(app, ["pitch", "--no-llm"], input="  ")
    assert result.exit_code == 1


def test_rebut_without_session_exits_nonzero():
    result = runner.invoke(app, ["rebut", "1: no", "--no-llm"])
    assert result.exit_code == 1


def test_rebut_after_saved_session(state_dir):
    core.save_session(core.Session("pitch", "idea", core.mock_report().model_dump()), state_dir)
    result = runner.invoke(app, ["rebut", "1: disagree", "--no-llm"])
    assert result.exit_code == 0
    assert "HOLDS" in result.output
