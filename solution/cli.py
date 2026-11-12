from __future__ import annotations

import argparse
from pathlib import Path

from .database import initialize_database


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Assignment A data pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init-db",
        help="create the SQLite database tables",
    )
    init_parser.add_argument("--db", required=True, type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "init-db":
        initialize_database(args.db)


if __name__ == "__main__":
    main()
