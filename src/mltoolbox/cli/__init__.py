import click

from mltoolbox.utils.logger import get_logger

from .init import init
from .remote import remote


@click.group()
@click.option("--debug", is_flag=True, help="Enable debug logging")
@click.option(
    "--dryrun",
    is_flag=True,
    help="Simulate all actions, do not run anything real (for UI/UX debugging)",
)
@click.pass_context
def cli(ctx, debug, dryrun):
    """ML Development Environment Management (with --dryrun for UI/UX simulation)"""
    ctx.ensure_object(dict)
    logger = get_logger()
    logger.set_debug(debug)
    logger.set_dryrun(dryrun)
    ctx.obj["debug"] = debug
    ctx.obj["dryrun"] = dryrun


cli.add_command(init)
cli.add_command(remote)
