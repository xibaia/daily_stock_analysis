from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts.backfill_stock_daily import (
    backup_sqlite_database,
    execute_backfill,
    parse_args,
    run,
)
from src.repositories.stock_repo import StockRepository
from src.storage import DatabaseManager


def _daily_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": date(2026, 7, 9),
                "open": 10.0,
                "high": 11.0,
                "low": 9.5,
                "close": 10.5,
                "volume": 1000,
                "amount": 10500,
            },
            {
                "date": date(2026, 7, 10),
                "open": 10.5,
                "high": 11.5,
                "low": 10.0,
                "close": 11.0,
                "volume": 1200,
                "amount": 13200,
            },
        ]
    )


@pytest.fixture
def stock_repository(tmp_path: Path):
    DatabaseManager.reset_instance()
    db = DatabaseManager(db_url=f"sqlite:///{tmp_path / 'stock.db'}")
    try:
        yield StockRepository(db), db
    finally:
        DatabaseManager.reset_instance()


@pytest.mark.parametrize(("flag", "value"), [("--days", "0"), ("--workers", "-1")])
def test_parse_args_rejects_non_positive_limits(flag: str, value: str) -> None:
    with pytest.raises(SystemExit):
        parse_args([flag, value])


def test_stock_repository_lists_distinct_daily_codes(stock_repository) -> None:
    repository, db = stock_repository
    db.save_daily_data(_daily_frame(), "600519", "fixture")
    db.save_daily_data(_daily_frame(), "000001", "fixture")

    assert repository.list_daily_codes() == ["000001", "600519"]


def test_sqlite_backup_api_produces_readable_consistent_copy(tmp_path: Path) -> None:
    source = tmp_path / "live.db"
    connection = sqlite3.connect(source)
    connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
    connection.execute("INSERT INTO sample(value) VALUES ('kept')")
    connection.commit()

    backup = backup_sqlite_database(source, tmp_path / "backup.db")

    with sqlite3.connect(backup) as copied:
        assert copied.execute("SELECT value FROM sample").fetchone() == ("kept",)
    connection.close()


def test_execute_backfill_is_idempotent_and_reports_partial_failure(
    stock_repository,
) -> None:
    repository, _db = stock_repository

    class FakeFetcher:
        def get_daily_data(self, code: str, *, days: int):
            assert days == 15
            if code == "BAD":
                raise RuntimeError("provider unavailable")
            return _daily_frame(), "fixture"

    first = execute_backfill(
        ["600519", "BAD"],
        days=15,
        workers=2,
        repository=repository,
        fetcher=FakeFetcher(),
    )
    second = execute_backfill(
        ["600519"],
        days=15,
        workers=1,
        repository=repository,
        fetcher=FakeFetcher(),
    )

    assert first.succeeded == 1
    assert first.failed == 1
    assert first.added_rows == 2
    assert first.failures == {"BAD": "provider unavailable"}
    assert second.succeeded == 1
    assert second.added_rows == 0


def test_dry_run_with_explicit_codes_has_no_database_or_provider_side_effects() -> None:
    output: list[str] = []

    def forbidden_factory():
        raise AssertionError("dry-run with explicit codes must not initialize services")

    exit_code = run(
        ["--dry-run", "--codes", "600519, 000001", "--days", "5"],
        db_factory=forbidden_factory,
        fetcher_factory=forbidden_factory,
        output=output.append,
    )

    assert exit_code == 0
    assert output == ["000001", "600519"]
