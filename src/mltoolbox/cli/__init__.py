import click

from .init import init
from .remote import remote


@click.group()
def cli():
    """ML Development Environment Management"""
    pass


cli.add_command(init)
cli.add_command(remote)
