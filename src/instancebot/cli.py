"""CLI entry point for instancebot."""

from .lambda_watchdog import main


def cli():
    """Entry point for the instancebot CLI."""
    main()


if __name__ == "__main__":
    cli()
