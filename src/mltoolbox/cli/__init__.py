import click
from dotenv import load_dotenv

from .init import init
from .local import local
from .remote import remote

load_dotenv()


@click.group()
def cli():
    """ML Development Environment Management"""
    pass


cli.add_command(init)
cli.add_command(remote)
cli.add_command(local)
