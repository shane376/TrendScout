from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from .config import Settings
from .pipeline import run_pipeline
from .sources.base import SourceError

app = typer.Typer(help="Discover, rank and draft traceable short-form video concepts.", no_args_is_help=True)
console = Console()


@app.callback()
def main():
    """TrendScout V1: content research without a paid AI API."""


@app.command()
def run(
    niche: Annotated[str, typer.Option(help="Topic to research (1-200 characters).")],
    limit: Annotated[int, typer.Option(min=1, max=20, help="Number of final ideas.")] = 5,
    demo: Annotated[bool, typer.Option(help="Use synthetic offline fixtures explicitly.")] = False,
    output_dir: Annotated[Path | None, typer.Option(help="Override OUTPUT_DIR.")] = None,
):
    if not niche.strip() or len(" ".join(niche.split())) > 200:
        raise typer.BadParameter("Niche must contain 1-200 nonblank characters.", param_hint="--niche")
    settings = Settings.from_env()
    if output_dir is not None:
        from dataclasses import replace
        settings = replace(settings, output_dir=output_dir)
    mode = "DEMO - synthetic fixtures; not live trends" if demo else f"LIVE - {settings.content_source}"
    console.print(mode, markup=False)
    try:
        with console.status("Collecting candidates, ranking, generating templates and exporting..."):
            result = run_pipeline(niche, limit, settings, demo=demo)
    except (SourceError, ValueError, OSError) as error:
        console.print(f"Error: {error}", style="red", markup=False)
        raise typer.Exit(1) from None
    if len(result.ideas) < limit:
        console.print(f"Only {len(result.ideas)} valid, unique candidates available; requested {limit}.")
    table = Table("Rank", "Source topic", "Opportunity")
    for item in result.posts[:limit]:
        from rich.text import Text
        table.add_row(str(item.rank), Text(item.post.title), f"{item.opportunity_score:.2f}")
    console.print(table)
    console.print(f"Ranked {result.candidate_count} candidates; generated {len(result.ideas)} template concepts.")
    console.print(f"Exports: {result.output_dir.resolve()}", markup=False)
    console.print("Research heuristic only. Scripts require fact-checking before production.")
