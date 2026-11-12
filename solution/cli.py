from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_dispositions
from .database import connect_database, initialize_database
from .pipeline import ingest_drop
from .pii import PiiProtector
from .reports import generate_reports


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Assignment A data pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init-db",
        help="create the SQLite database tables",
    )
    init_parser.add_argument("--db", required=True, type=Path)
    report_parser = subparsers.add_parser(
        "report",
        help="write the five report files",
    )
    report_parser.add_argument("--db", required=True, type=Path)
    report_parser.add_argument("--out", required=True, type=Path)
    report_parser.add_argument(
        "--dispositions",
        type=Path,
        default=Path("assignment-a-data/schemas/dispositions.csv"),
    )
    ingest_parser = subparsers.add_parser(
        "ingest",
        help="ingest one data drop",
    )
    ingest_parser.add_argument("--db", required=True, type=Path)
    ingest_parser.add_argument("--drop", required=True, type=Path)
    ingest_parser.add_argument(
        "--schemas",
        type=Path,
        default=Path("assignment-a-data/schemas"),
    )
    ingest_parser.add_argument(
        "--dispositions",
        type=Path,
        default=Path("assignment-a-data/schemas/dispositions.csv"),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "init-db":
        initialize_database(args.db)
    elif args.command == "report":
        connection = connect_database(args.db)
        try:
            generate_reports(
                connection,
                args.out,
                load_dispositions(args.dispositions),
                PiiProtector.from_environment(),
            )
        finally:
            connection.close()
    elif args.command == "ingest":
        connection = connect_database(args.db)
        try:
            ingest_drop(
                connection,
                args.drop,
                args.schemas,
                args.dispositions,
                PiiProtector.from_environment(),
            )
        finally:
            connection.close()


if __name__ == "__main__":
    main()
