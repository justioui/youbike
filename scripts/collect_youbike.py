import csv
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.request import urlopen

API_URL = "https://tcgbusfs.blob.core.windows.net/dotapp/youbike/v2/youbike_immediate.json"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "youbike.sqlite3"


def get_taipei_now() -> datetime:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Asia/Taipei"))
    except Exception:
        return datetime.now(timezone(timedelta(hours=8)))


def fetch_records() -> list[dict[str, Any]]:
    with urlopen(API_URL, timeout=30) as response:
        payload = response.read().decode("utf-8")

    decoded = json.loads(payload)
    if not isinstance(decoded, list):
        raise ValueError("API response is not a list")

    normalized: list[dict[str, Any]] = []
    for item in decoded:
        if isinstance(item, dict):
            normalized.append(item)
    return normalized


def read_csv_header(csv_path: Path) -> list[str]:
    if not csv_path.exists():
        return []
    with csv_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.reader(file)
        return next(reader, [])


def collect_fieldnames(existing_header: list[str], rows: list[dict[str, Any]]) -> list[str]:
    current = list(existing_header)
    seen = set(existing_header)

    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                current.append(key)
    return current


def write_daily_csv(csv_path: Path, rows: list[dict[str, Any]]) -> None:
    existing_header = read_csv_header(csv_path)
    final_header = collect_fieldnames(existing_header, rows)

    if not csv_path.exists():
        with csv_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=final_header, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        return

    if existing_header == final_header:
        with csv_path.open("a", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=final_header, extrasaction="ignore")
            writer.writerows(rows)
        return

    with csv_path.open("r", encoding="utf-8", newline="") as file:
        existing_rows = list(csv.DictReader(file))

    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=final_header, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(existing_rows)
        writer.writerows(rows)


@dataclass
class DbRow:
    fetched_at: str
    sno: str | None
    sna: str | None
    sarea: str | None
    available_rent_bikes: int | None
    available_return_bikes: int | None
    latitude: float | None
    longitude: float | None
    raw_json: str


def to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_db_rows(rows: list[dict[str, Any]], fetched_at: str) -> list[DbRow]:
    db_rows: list[DbRow] = []
    for row in rows:
        db_rows.append(
            DbRow(
                fetched_at=fetched_at,
                sno=row.get("sno"),
                sna=row.get("sna"),
                sarea=row.get("sarea"),
                available_rent_bikes=to_int(row.get("available_rent_bikes")),
                available_return_bikes=to_int(row.get("available_return_bikes")),
                latitude=to_float(row.get("latitude", row.get("lat"))),
                longitude=to_float(row.get("longitude", row.get("lng"))),
                raw_json=json.dumps(row, ensure_ascii=False),
            )
        )
    return db_rows


def ensure_database_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS youbike_immediate_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetched_at TEXT NOT NULL,
            sno TEXT,
            sna TEXT,
            sarea TEXT,
            available_rent_bikes INTEGER,
            available_return_bikes INTEGER,
            latitude REAL,
            longitude REAL,
            raw_json TEXT NOT NULL
        )
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_youbike_snapshot_fetched_at
        ON youbike_immediate_snapshots(fetched_at)
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_youbike_snapshot_sno
        ON youbike_immediate_snapshots(sno)
        """
    )


def insert_rows_to_db(db_path: Path, rows: list[DbRow]) -> None:
    with sqlite3.connect(db_path) as conn:
        ensure_database_schema(conn)
        conn.executemany(
            """
            INSERT INTO youbike_immediate_snapshots (
                fetched_at,
                sno,
                sna,
                sarea,
                available_rent_bikes,
                available_return_bikes,
                latitude,
                longitude,
                raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row.fetched_at,
                    row.sno,
                    row.sna,
                    row.sarea,
                    row.available_rent_bikes,
                    row.available_return_bikes,
                    row.latitude,
                    row.longitude,
                    row.raw_json,
                )
                for row in rows
            ],
        )
        conn.commit()


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    now = get_taipei_now()
    date_str = now.strftime("%Y-%m-%d")
    fetched_at = now.isoformat()
    csv_path = DATA_DIR / f"{date_str}.csv"

    base_rows = fetch_records()
    enriched_rows = [{"fetched_at": fetched_at, **row} for row in base_rows]

    write_daily_csv(csv_path, enriched_rows)
    insert_rows_to_db(DB_PATH, to_db_rows(base_rows, fetched_at))

    print(f"Fetched records: {len(base_rows)}")
    print(f"CSV updated: {csv_path}")
    print(f"SQLite updated: {DB_PATH}")


if __name__ == "__main__":
    main()
