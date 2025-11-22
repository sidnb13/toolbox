"""
Simple wrapper to import and run the mlt CLI.
This allows the mlt command to work when installed via the main toolbox package.
"""

import sys


def main():
    """Entry point for mlt command."""
    # Import the actual mlt CLI
    try:
        # Try to import from standalone mlt package (if installed separately)
        from mlt.cli import main as mlt_main

        mlt_main()
    except ImportError:
        # If mlt package not found, show helpful error
        print("ERROR: mlt package not found", file=sys.stderr)
        print("", file=sys.stderr)
        print(
            "The 'mlt' tool is installed automatically on remote hosts during 'mltoolbox remote connect'.",
            file=sys.stderr,
        )
        print("For local development/testing, install it manually:", file=sys.stderr)
        print("  cd src/mlt && pip install -e .", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
