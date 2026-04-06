from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
import csv
import re
import sqlite3

import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "lotto.db"
NORMALIZED_EXPORT_PATH = DATA_DIR / "normalized_results.csv"

DRAW_TYPES = {"midday", "evening"}


@dataclass(frozen=True)
class DrawRecord:
    draw_type: str
    draw_date: date
    draw_number: int | None
    digits: tuple[int, int, int]
    source: str

    @property
    def number(self) -> str:
        return "-".join(str(digit) for digit in self.digits)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["draw_date"] = self.draw_date.isoformat()
        payload["number"] = self.number
        return payload


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS draw_records (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                draw_type   TEXT    NOT NULL,
                draw_date   TEXT    NOT NULL,
                draw_number INTEGER,
                digit1      INTEGER NOT NULL,
                digit2      INTEGER NOT NULL,
                digit3      INTEGER NOT NULL,
                source      TEXT    NOT NULL,
                UNIQUE(draw_type, draw_date)
            )
        """)
        conn.execute("DROP TABLE IF EXISTS custom_records")
        conn.commit()
    _sync_normalized_csv_to_db()


def _sync_normalized_csv_to_db() -> None:
    """Seed the canonical draw_records table from the normalized CSV export when empty."""
    if not NORMALIZED_EXPORT_PATH.exists():
        return

    with _connect() as conn:
        existing_count = conn.execute("SELECT COUNT(*) FROM draw_records").fetchone()[0]
    if existing_count > 0:
        return

    records = _load_normalized_csv_records(NORMALIZED_EXPORT_PATH)
    if not records:
        return

    with _connect() as conn:
        for record in records:
            conn.execute(
                """
                INSERT INTO draw_records
                    (draw_type, draw_date, draw_number, digit1, digit2, digit3, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(draw_type, draw_date) DO UPDATE SET
                    draw_number = excluded.draw_number,
                    digit1 = excluded.digit1,
                    digit2 = excluded.digit2,
                    digit3 = excluded.digit3,
                    source = excluded.source
                """,
                (
                    record.draw_type,
                    record.draw_date.isoformat(),
                    record.draw_number,
                    record.digits[0],
                    record.digits[1],
                    record.digits[2],
                    record.source,
                ),
            )
        conn.commit()


def parse_number(raw_value: str) -> tuple[int, int, int]:
    digits = [int(char) for char in re.findall(r"\d", raw_value or "")]
    if len(digits) != 3:
        raise ValueError("Winning number must contain exactly 3 digits.")
    return digits[0], digits[1], digits[2]


def _load_normalized_csv_records(path: Path) -> list[DrawRecord]:
    records: list[DrawRecord] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            number = str(row.get("number") or "").strip()
            if not number:
                continue
            records.append(
                DrawRecord(
                    draw_type=str(row["draw_type"]).strip().lower(),
                    draw_date=date.fromisoformat(str(row["draw_date"]).strip()),
                    draw_number=int(float(row["draw_number"])) if row.get("draw_number") else None,
                    digits=parse_number(number),
                    source=str(row.get("source") or "unknown").strip(),
                )
            )
    return records


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_all_records() -> pd.DataFrame:
    DATA_DIR.mkdir(exist_ok=True)

    records = _load_draw_records()
    if not records:
        _sync_normalized_csv_to_db()
        records = _load_draw_records()

    frame = pd.DataFrame(record.to_dict() for record in records)
    if frame.empty:
        return frame

    frame["draw_date"] = pd.to_datetime(frame["draw_date"])
    frame["sort_draw_number"] = frame["draw_number"].fillna(-1)
    frame = frame.sort_values(
        by=["draw_type", "draw_date", "sort_draw_number"],
        ascending=[True, False, False],
    ).reset_index(drop=True)
    frame = frame.drop(columns=["sort_draw_number"])
    frame.to_csv(NORMALIZED_EXPORT_PATH, index=False)
    return frame


def _load_draw_records() -> list[DrawRecord]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT draw_type, draw_date, draw_number, digit1, digit2, digit3, source
            FROM draw_records
            ORDER BY draw_type, draw_date DESC, draw_number DESC
            """
        ).fetchall()
    return [
        DrawRecord(
            draw_type=row["draw_type"],
            draw_date=date.fromisoformat(row["draw_date"]),
            draw_number=row["draw_number"],
            digits=(row["digit1"], row["digit2"], row["digit3"]),
            source=row["source"],
        )
        for row in rows
    ]


def append_record(
    draw_type: str,
    draw_date: date,
    winning_number: str,
    draw_number: int | None = None,
) -> DrawRecord:
    normalized_type = draw_type.strip().lower()
    if normalized_type not in DRAW_TYPES:
        raise ValueError("Draw type must be either midday or evening.")

    record = DrawRecord(
        draw_type=normalized_type,
        draw_date=draw_date,
        draw_number=draw_number,
        digits=parse_number(winning_number),
        source="manual",
    )

    existing_records = [
        DrawRecord(
            draw_type=str(row["draw_type"]).strip().lower(),
            draw_date=pd.Timestamp(row["draw_date"]).date(),
            draw_number=int(row["draw_number"]) if pd.notna(row["draw_number"]) else None,
            digits=parse_number(str(row["number"])),
            source=str(row["source"]),
        )
        for _, row in load_all_records().iterrows()
    ]
    if any(
        existing.draw_type == record.draw_type and existing.draw_date == record.draw_date
        for existing in existing_records
    ):
        raise ValueError("A record for that draw type and date already exists.")
    if any(_record_equals(record, existing) for existing in existing_records):
        raise ValueError("This exact result already exists in the dataset.")

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO draw_records
                (draw_type, draw_date, draw_number, digit1, digit2, digit3, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(draw_type, draw_date) DO UPDATE SET
                draw_number = excluded.draw_number,
                digit1 = excluded.digit1,
                digit2 = excluded.digit2,
                digit3 = excluded.digit3,
                source = excluded.source
            """,
            (
                record.draw_type,
                record.draw_date.isoformat(),
                record.draw_number,
                record.digits[0],
                record.digits[1],
                record.digits[2],
                record.source,
            ),
        )
        conn.commit()

    return record


def list_records() -> pd.DataFrame:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, draw_type, draw_date, draw_number, digit1, digit2, digit3, source "
            "FROM draw_records ORDER BY draw_date DESC, id DESC"
        ).fetchall()

    if not rows:
        return pd.DataFrame(
            columns=["entry_id", "draw_type", "draw_date", "draw_number", "number", "source"]
        )

    data = [
        {
            "entry_id": row["id"],
            "draw_type": row["draw_type"],
            "draw_date": row["draw_date"],
            "draw_number": row["draw_number"] if row["draw_number"] is not None else "",
            "number": f"{row['digit1']}-{row['digit2']}-{row['digit3']}",
            "source": row["source"],
        }
        for row in rows
    ]
    return pd.DataFrame(data)


def update_record(
    entry_id: int,
    draw_type: str,
    draw_date: date,
    winning_number: str,
    draw_number: int | None = None,
) -> DrawRecord:
    normalized_type = draw_type.strip().lower()
    if normalized_type not in DRAW_TYPES:
        raise ValueError("Draw type must be either midday or evening.")

    with _connect() as conn:
        existing = conn.execute(
            "SELECT id FROM draw_records WHERE id = ?", (entry_id,)
        ).fetchone()
        if existing is None:
            raise ValueError("Record not found.")

    updated_record = DrawRecord(
        draw_type=normalized_type,
        draw_date=draw_date,
        draw_number=draw_number,
        digits=parse_number(winning_number),
        source="manual",
    )

    existing_records = [
        DrawRecord(
            draw_type=str(row["draw_type"]).strip().lower(),
            draw_date=pd.Timestamp(row["draw_date"]).date(),
            draw_number=int(row["draw_number"]) if pd.notna(row["draw_number"]) else None,
            digits=parse_number(str(row["number"])),
            source=str(row["source"]),
        )
        for _, row in load_all_records().iterrows()
    ]
    # Exclude the record being updated from the duplicate check
    with _connect() as conn:
        old_row = conn.execute(
            "SELECT draw_type, draw_date, draw_number, digit1, digit2, digit3, source "
            "FROM draw_records WHERE id = ?",
            (entry_id,),
        ).fetchone()
    old_record = DrawRecord(
        draw_type=old_row["draw_type"],
        draw_date=date.fromisoformat(old_row["draw_date"]),
        draw_number=old_row["draw_number"],
        digits=(old_row["digit1"], old_row["digit2"], old_row["digit3"]),
        source=old_row["source"],
    )
    duplicate_exists = any(
        _record_equals(updated_record, existing)
        for existing in existing_records
        if not _record_equals(existing, old_record)
    )
    if duplicate_exists:
        raise ValueError("This exact result already exists in the dataset.")
    date_slot_taken = any(
        existing.draw_type == updated_record.draw_type and existing.draw_date == updated_record.draw_date
        for existing in existing_records
        if not _record_equals(existing, old_record)
    )
    if date_slot_taken:
        raise ValueError("Another record already exists for that draw type and date.")

    with _connect() as conn:
        conn.execute(
            "UPDATE draw_records "
            "SET draw_type=?, draw_date=?, draw_number=?, digit1=?, digit2=?, digit3=?, source=? "
            "WHERE id=?",
            (
                updated_record.draw_type,
                updated_record.draw_date.isoformat(),
                updated_record.draw_number,
                updated_record.digits[0],
                updated_record.digits[1],
                updated_record.digits[2],
                updated_record.source,
                entry_id,
            ),
        )
        conn.commit()

    return updated_record


def delete_record(entry_id: int) -> None:
    with _connect() as conn:
        existing = conn.execute(
            """
            SELECT id
            FROM draw_records
            WHERE id = ?
            """,
            (entry_id,),
        ).fetchone()
        if existing is None:
            raise ValueError("Record not found.")
        conn.execute("DELETE FROM draw_records WHERE id = ?", (entry_id,))
        conn.commit()


def _record_equals(left: DrawRecord, right: DrawRecord) -> bool:
    return (
        left.draw_type == right.draw_type
        and left.draw_date == right.draw_date
        and left.draw_number == right.draw_number
        and left.digits == right.digits
    )


# Initialize DB on import.
_init_db()
