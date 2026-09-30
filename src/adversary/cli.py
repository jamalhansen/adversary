import sys
from pathlib import Path
from typing import Annotated

import typer
from local_first_common.cli import (
    dry_run_option,
    json_option,
    model_option,
    no_llm_option,
    provider_option,
    resolve_dry_run,
    resolve_provider,
)
from local_first_common.config import get_setting
from local_first_common.providers import PROVIDERS
from local_first_common.tracking import register_tool
from rich.console import Console

from .core import (
    AdversaryError,
    Mode,
    Session,
    argue,
    git_diff,
    load_session,
    rebut,
    render_rebuttal,
    render_report,
    save_session,
)
from .schema import AdversaryReport

TOOL_NAME = "adversary"
_TOOL = register_tool(TOOL_NAME)
# Adversarial critique is the reasoning tier's job (see tiering.py); small local
# models make agreeable, vague adversaries. Override per call or in config.
DEFAULT_PROVIDER = "claude-code"
DEFAULT_MODELS = {"claude-code": "sonnet"}

console = Console(stderr=True)
app = typer.Typer(help="Argues against your change or plan: the strongest objection, falsifiable challenges, and what should have been built instead.")


def _provider(provider: str | None, model: str | None, no_llm: bool):
    if no_llm:
        return None
    name = get_setting(TOOL_NAME, "provider", cli_val=provider, env_var="MODEL_PROVIDER", default=DEFAULT_PROVIDER)
    chosen = get_setting(TOOL_NAME, "model", cli_val=model, default=DEFAULT_MODELS.get(name))
    return resolve_provider(PROVIDERS, name, chosen, tool_name=TOOL_NAME)


def _argue_and_print(mode: Mode, text: str, context: str, provider, model, dry_run: bool, no_llm: bool, as_json: bool) -> None:
    dry_run = resolve_dry_run(dry_run, no_llm)
    try:
        llm = _provider(provider, model, no_llm)
        if llm is not None:
            console.print(f"[dim]Arguing against it with {llm.provider_name}/{llm.model}...[/dim]")
        report = argue(llm, mode, text, context)
    except AdversaryError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from e
    if not dry_run:
        save_session(Session(mode, text, report.model_dump()))
    typer.echo(report.model_dump_json(indent=2) if as_json else render_report(report))


@app.command()
def review(
    diff_range: Annotated[str | None, typer.Option("--range", "-r", help="git diff range (default: uncommitted changes vs HEAD)")] = None,
    context: Annotated[str, typer.Option("--context", "-c", help="What the change is meant to do, so it can be argued against on its own terms")] = "",
    provider: Annotated[str | None, provider_option()] = None,
    model: Annotated[str | None, model_option()] = None,
    as_json: Annotated[bool, json_option()] = False,
    dry_run: Annotated[bool, dry_run_option()] = False,
    no_llm: Annotated[bool, no_llm_option()] = False,
) -> None:
    """Argue against a code change (a git diff in the current repo)."""
    try:
        diff = git_diff(diff_range)
    except AdversaryError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from e
    _argue_and_print("review", diff, context, provider, model, dry_run, no_llm, as_json)


@app.command()
def pitch(
    path: Annotated[Path | None, typer.Argument(help="Markdown plan/pitch/idea to argue against (omit to read stdin)")] = None,
    provider: Annotated[str | None, provider_option()] = None,
    model: Annotated[str | None, model_option()] = None,
    as_json: Annotated[bool, json_option()] = False,
    dry_run: Annotated[bool, dry_run_option()] = False,
    no_llm: Annotated[bool, no_llm_option()] = False,
) -> None:
    """Argue against a plan, pitch, or idea -- PRFAQ-style, problem before solution."""
    text = path.read_text(encoding="utf-8") if path else sys.stdin.read()
    _argue_and_print("pitch", text, "", provider, model, dry_run, no_llm, as_json)


@app.command(name="rebut")
def rebut_cmd(
    response: Annotated[str | None, typer.Argument(help="Your answers to the challenges, e.g. '1: ran the test, passes. 3: ...' (omit to read stdin)")] = None,
    provider: Annotated[str | None, provider_option()] = None,
    model: Annotated[str | None, model_option()] = None,
    as_json: Annotated[bool, json_option()] = False,
    no_llm: Annotated[bool, no_llm_option()] = False,
) -> None:
    """Answer the last review/pitch. The adversary concedes to evidence, holds, or escalates."""
    try:
        session = load_session()
        llm = _provider(provider, model, no_llm)
        result = rebut(llm, session, response if response is not None else sys.stdin.read())
    except AdversaryError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from e
    report = AdversaryReport.model_validate(session.report)
    typer.echo(result.model_dump_json(indent=2) if as_json else render_rebuttal(report, result))


if __name__ == "__main__":
    app()
