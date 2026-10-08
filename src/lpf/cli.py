"""CLI entry point for the AI Educational Product Factory."""

from __future__ import annotations

import asyncio
import json

import click

from lpf import __version__
from lpf.config import LpfConfig, load_config
from lpf.logging_setup import setup_logging
from lpf.orchestration.pipeline import FactoryPipeline
from lpf.research.providers.arxiv import ArxivProvider
from lpf.research.providers.wikimedia import WikimediaProvider
from lpf.schemas.discovery import DiscoveryInputs
from lpf.schemas.research import SearchProvider


@click.group()
@click.version_option(version=__version__, prog_name="lpf")
@click.pass_context
def main(ctx: click.Context) -> None:
    """AI Educational Product Factory — generate complete learning products."""
    ctx.ensure_object(dict)
    config = load_config()
    setup_logging(config)
    ctx.obj["config"] = config


@main.command()
@click.argument("subject")
@click.argument("topic")
@click.option("--level", default="high-school", help="Learner level")
@click.option("--run-id", default="run", show_default=True, help="Run identifier")
@click.option("--seed", default="default", show_default=True, help="Determinism seed")
@click.option(
    "--mock/--no-mock",
    default=True,
    show_default=True,
    help="Run the deterministic offline pipeline (only mock is implemented).",
)
@click.option(
    "--live-research",
    is_flag=True,
    default=False,
    help="Search real sources via arXiv and Wikimedia instead of the offline provider.",
)
@click.pass_context
def generate(
    ctx: click.Context,
    subject: str,
    topic: str,
    level: str,
    run_id: str,
    seed: str,
    mock: bool,
    live_research: bool,
) -> None:
    """Generate an educational product for a subject and topic."""
    config: LpfConfig = ctx.obj["config"]

    if not mock and config.provider != "mock":
        raise click.ClickException(
            f"Provider {config.provider!r} is not implemented yet; use --mock."
        )

    inputs = DiscoveryInputs(
        request=f"Generate a learning product on {topic} for {level} learners.",
        subject=subject,
        level=level,
    )

    research_providers = None
    if live_research:
        research_providers = {
            SearchProvider.ARXIV: ArxivProvider(),
            SearchProvider.WIKIMEDIA: WikimediaProvider(),
        }

    click.echo(f"Generating product: subject={subject}, topic={topic}, level={level}")
    click.echo(f"Output directory: {config.output_dir}")
    click.echo(
        "Research providers: "
        + (
            ", ".join(sorted(provider.value for provider in research_providers))
            if research_providers
            else "mock (deterministic, offline)"
        )
    )

    pipeline = FactoryPipeline(output_dir=config.output_dir, research_providers=research_providers)
    result = asyncio.run(pipeline.run(inputs, run_id=run_id, seed=seed))

    if not result.succeeded:
        click.echo(f"Run failed at stage '{result.state.stage.value}'.", err=True)
        if result.state.failure_reason:
            click.echo(f"Reason: {result.state.failure_reason}", err=True)
        ctx.exit(1)

    verification = result.verification
    click.echo(f"Run complete: {result.run_id}")
    click.echo(f"Artifacts: {len(result.artifacts)}")
    if verification is not None:
        click.echo(
            f"QA: {verification.overall_status.value} "
            f"({verification.overall_score:.2f}, {len(verification.gates)} gates)"
        )
    if result.package is not None:
        click.echo(f"Written to: {result.package.root}")
        click.echo(
            json.dumps(
                {
                    "product": str(result.package.product_path),
                    "html": str(result.package.product_html_path),
                    "bundle": str(result.package.bundle_path),
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
