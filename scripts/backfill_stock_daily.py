#!/usr/bin/env python3
"""Safely backfill recent ``stock_daily`` rows for existing symbols."""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)


@dataclass
class BackfillSummary:
    total: int
    succeeded: int = 0
    skipped: int = 0
    failed: int = 0
    added_rows: int = 0
    failures: dict[str, str] = field(default_factory=dict)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return parsed


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill recent stock_daily rows for existing symbols",
    )
    parser.add_argument("--days", type=_positive_int, default=15)
    parser.add_argument("--workers", type=_positive_int, default=3)
    parser.add_argument("--codes", help="Comma-separated symbols; defaults to stock_daily symbols")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-backup", action="store_true")
    return parser.parse_args(argv)


def _normalize_codes(codes: Iterable[str]) -> list[str]:
    return sorted({code.strip().upper() for code in codes if code.strip()})


def backup_sqlite_database(
    source: Path,
    destination: Optional[Path] = None,
) -> Path:
    source = source.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"SQLite database does not exist: {source}")
    if destination is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = source.with_name(f"{source.name}.backup.{timestamp}")
    destination = destination.expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"Backup destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    source_uri = f"file:{source.as_posix()}?mode=ro"
    with sqlite3.connect(source_uri, uri=True) as source_connection:
        with sqlite3.connect(destination) as destination_connection:
            source_connection.backup(destination_connection)
    return destination


def execute_backfill(
    codes: Sequence[str],
    *,
    days: int,
    workers: int,
    repository,
    fetcher,
) -> BackfillSummary:
    normalized_codes = _normalize_codes(codes)
    summary = BackfillSummary(total=len(normalized_codes))

    def process(code: str) -> tuple[str, str, int, str]:
        try:
            frame, source = fetcher.get_daily_data(code, days=days)
            if frame is None or frame.empty:
                return code, "skipped", 0, "empty provider response"
            added = repository.db.save_daily_data(frame, code, source)
            return code, "succeeded", added, ""
        except Exception as exc:  # noqa: BLE001 - failures are summarized per symbol.
            return code, "failed", 0, str(exc)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process, code): code for code in normalized_codes}
        for future in as_completed(futures):
            code, status, added, error = future.result()
            if status == "succeeded":
                summary.succeeded += 1
                summary.added_rows += added
            elif status == "skipped":
                summary.skipped += 1
            else:
                summary.failed += 1
                summary.failures[code] = error
    return summary


def _sqlite_path_from_url(database_url: str) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix) or database_url == "sqlite:///:memory:":
        raise ValueError("automatic backup requires a file-backed SQLite database")
    return Path(database_url[len(prefix):])


def run(
    argv: Optional[Sequence[str]] = None,
    *,
    db_factory: Optional[Callable[[], object]] = None,
    fetcher_factory: Optional[Callable[[], object]] = None,
    output: Callable[[str], None] = print,
) -> int:
    args = parse_args(argv)
    explicit_codes = _normalize_codes((args.codes or "").split(","))

    if args.dry_run and explicit_codes:
        for code in explicit_codes:
            output(code)
        return 0

    from src.repositories.stock_repo import StockRepository
    from src.storage import get_db

    db = (db_factory or get_db)()
    repository = StockRepository(db)
    codes = explicit_codes or repository.list_daily_codes()
    if args.dry_run:
        for code in codes:
            output(code)
        return 0
    if not codes:
        output("No stock_daily symbols found; nothing to backfill.")
        return 0

    if not args.skip_backup:
        from src.config import get_config

        backup_path = backup_sqlite_database(
            _sqlite_path_from_url(get_config().get_db_url())
        )
        output(f"Backup: {backup_path}")

    if fetcher_factory is None:
        from data_provider import DataFetcherManager

        fetcher_factory = DataFetcherManager
    summary = execute_backfill(
        codes,
        days=args.days,
        workers=args.workers,
        repository=repository,
        fetcher=fetcher_factory(),
    )
    output(
        "Backfill: "
        f"total={summary.total} succeeded={summary.succeeded} "
        f"skipped={summary.skipped} failed={summary.failed} "
        f"added_rows={summary.added_rows}"
    )
    for code, error in sorted(summary.failures.items()):
        output(f"FAILED {code}: {error}")
    return 1 if summary.failed else 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    raise SystemExit(run())


if __name__ == "__main__":
    main()
