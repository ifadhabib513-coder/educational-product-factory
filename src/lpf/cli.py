"""CLI entry point for the AI Educational Product Factory."""

from __future__ import annotations

import click

from lpf import __version__
from lpf.config import LpfConfig, load_config
from lpf.logging_setup import setup_logging


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
@click.pass_context
def generate(ctx: click.Context, subject: str, topic: str, level: str) -> None:
    """Generate an educational product for a subject and topic."""
    config: LpfConfig = ctx.obj["config"]
    click.echo(f"Generating product: subject={subject}, topic={topic}, level={level}")
    click.echo(f"Output directory: {config.output_dir}")
    click.echo(f"Provider: {config.provider}")
    click.echo("Not yet implemented — Stage 4 will add the pipeline.")


if __name__ == "__main__":
    main()
