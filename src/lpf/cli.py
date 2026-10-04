"""CLI entry point for the AI Educational Product Factory."""

from __future__ import annotations

import asyncio
import json

import click

from lpf import __version__
from lpf.config import LpfConfig, load_config
from lpf.logging_setup import setup_logging
from lpf.orchestration.pipeline import FactoryPipeline
from lpf.schemas.discovery import DiscoveryInputs


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
@click.pass_context
def generate(
    ctx: click.Context,
    subject: str,
    topic: str,
    level: str,
    run_id: str,
    seed: str,
    mock: bool,
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

    click.echo(f"Generating product: subject={subject}, topic={topic}, level={level}")
    click.echo(f"Output directory: {config.output_dir}")

    pipeline = FactoryPipeline(output_dir=config.output_dir)
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
        click.echo(json.dumps({"product": str(result.package.product_path)}, indent=2))


if __name__ == "__main__":
    main()
