"""
Module entry point so the CLI works via `python -m kaxanuk.data_curator`.

Useful when the console script directory is not on the system PATH.
"""

from kaxanuk.data_curator.services.cli import cli


if __name__ == '__main__':
    cli()
