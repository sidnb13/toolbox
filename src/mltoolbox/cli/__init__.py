import click

from mltoolbox.utils.logger import get_logger

from .init import init
from .remote import remote


@click.group()
@click.option("--debug", is_flag=True, help="Enable debug logging")
@click.pass_context
def cli(ctx, debug):
    """ML Development Environment Management"""
    ctx.ensure_object(dict)
    logger = get_logger()
    logger.set_debug(debug)
    ctx.obj["debug"] = debug


cli.add_command(init)
cli.add_command(remote)
