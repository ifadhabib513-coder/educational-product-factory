"""CLI entry point for the AI Educational Product Factory."""

from __future__ import annotations

import asyncio
import json

import click

from lpf import __version__
from lpf.config import LpfConfig, load_config
from lpf.errors import ConfigError
from lpf.logging_setup import setup_logging
from lpf.models.providers import create_live_model
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
    try:
        config = load_config()
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc
    setup_logging(config)
    ctx.obj["config"] = config


async def _async_main(
    config: LpfConfig,
    subject: str,
    topic: str,
    level: str,
    run_id: str,
    kind: str,
    live_research: bool,
) -> None:
    """Async entry point for the generate command."""
    model = None
    if kind == "mock":
        writer = "mock (deterministic, offline)"
    else:
        try:
            model = create_live_model(
                kind.lower(),
                model=config.model_name,
                base_url=config.model_endpoint,
                api_key=config.api_key,
                timeout_seconds=config.timeout_seconds,
            )
        except ConfigError as exc:
            raise click.ClickException(str(exc)) from exc
        name = config.model_name or "default"
        endpoint = config.model_endpoint or "default endpoint"
        writer = f"{kind} ({name} @ {endpoint})"

    inputs = DiscoveryInputs(
        request=f"Generate a learning product on {topic} for {level} learners.",
        subject=subject,
        level=level,
    )

    research_providers = None
    if live_research:
        research_providers = {
            SearchProvider.ARXIV: ArxivProvider(timeout_seconds=config.timeout_seconds),
            SearchProvider.WIKIMEDIA: WikimediaProvider(timeout_seconds=config.timeout_seconds),
        }

    click.echo(f"Generating product: subject={subject}, topic={topic}, level={level}")
    click.echo(f"Output directory: {config.output_dir}")
    click.echo(f"Writer model: {writer}")
    click.echo(
        "Research providers: "
        + (
            ", ".join(sorted(provider.value for provider in research_providers))
            if research_providers
            else "mock (deterministic, offline)"
        )
    )

    pipeline = FactoryPipeline(
        output_dir=config.output_dir,
        model=model,
        research_providers=research_providers,
    )
    try:
        result = await pipeline.run(inputs, run_id=run_id)
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc
    finally:
        await pipeline.aclose()

    if not result.succeeded:
        click.echo(f"Run failed at stage '{result.state.stage.value}'.", err=True)
        if result.state.failure_reason:
            click.echo(f"Reason: {result.state.failure_reason}", err=True)
        raise click.ClickException("Run failed")

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


@main.command()
@click.argument("subject")
@click.argument("topic")
@click.option("--level", default="high-school", help="Learner level")
@click.option("--run-id", default="run", show_default=True, help="Run identifier")
@click.option(
    "--model",
    "model_kind",
    default=None,
    type=click.Choice(["mock", "openai-compatible", "ollama", "opencode-server"], case_sensitive=False),
    help=(
        "Writer model provider. Default: LPF_PROVIDER / lpf.toml [model].kind, "
        "else 'mock' (deterministic, offline — the safe default)."
    ),
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
    model_kind: str | None,
    live_research: bool,
) -> None:
    """Generate an educational product for a subject and topic."""
    config: LpfConfig = ctx.obj["config"]
    kind = model_kind or config.provider

    asyncio.run(_async_main(config, subject, topic, level, run_id, kind, live_research))


if __name__ == "__main__":
    main()
