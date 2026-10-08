"""SQLite-Zugriff. Bewusst ohne ORM – das Datenmodell ist winzig."""

import os
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta

DB_PATH = os.environ.get("DB_PATH", "/data/krankmeldung.db")
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "30"))

REPORT_TYPES = {
    "selbst": "Selbst krankgemeldet (ohne AU)",
    "arzt_analog": "Ärztliche AU – Papier",
    "arzt_digital": "Ärztliche AU – digital (eAU)",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS employees (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    code        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS reports (
    id           INTEGER PRIMARY KEY,
    employee_id  INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    date_from    TEXT NOT NULL,
    date_to      TEXT NOT NULL,
    type         TEXT NOT NULL,
    note         TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    read_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_reports_read ON reports(read_at);
CREATE INDEX IF NOT EXISTS idx_reports_date_to ON reports(date_to);
"""


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)


def purge_old_reports() -> int:
    """Löscht Meldungen, deren Bis-Datum länger als RETENTION_DAYS zurückliegt."""
    cutoff = (date.today() - timedelta(days=RETENTION_DAYS)).isoformat()
    with connect() as conn:
        cur = conn.execute("DELETE FROM reports WHERE date_to < ?", (cutoff,))
        return cur.rowcount


# --- Mitarbeiter ---------------------------------------------------------

def find_employee_by_code(code: str):
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM employees WHERE code = ? AND active = 1", (code.strip(),)
        ).fetchone()


def get_employee(employee_id: int):
    with connect() as conn:
        return conn.execute("SELECT * FROM employees WHERE id = ?", (employee_id,)).fetchone()


def list_employees():
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM employees ORDER BY active DESC, name COLLATE NOCASE"
        ).fetchall()


def code_taken(code: str, exclude_id: int | None = None) -> bool:
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM employees WHERE code = ? AND id IS NOT ?",
            (code.strip(), exclude_id),
        ).fetchone()
        return row is not None


def create_employee(name: str, code: str):
    with connect() as conn:
        conn.execute("INSERT INTO employees (name, code) VALUES (?, ?)", (name.strip(), code.strip()))


def update_employee(employee_id: int, name: str, code: str):
    with connect() as conn:
        conn.execute(
            "UPDATE employees SET name = ?, code = ? WHERE id = ?",
            (name.strip(), code.strip(), employee_id),
        )


def set_employee_active(employee_id: int, active: bool):
    with connect() as conn:
        conn.execute("UPDATE employees SET active = ? WHERE id = ?", (int(active), employee_id))


def delete_employee(employee_id: int):
    with connect() as conn:
        conn.execute("DELETE FROM employees WHERE id = ?", (employee_id,))


# --- Meldungen -----------------------------------------------------------

def create_report(employee_id: int, date_from: date, date_to: date, type_: str, note: str):
    with connect() as conn:
        conn.execute(
            "INSERT INTO reports (employee_id, date_from, date_to, type, note) VALUES (?, ?, ?, ?, ?)",
            (employee_id, date_from.isoformat(), date_to.isoformat(), type_, note.strip()),
        )


def list_reports(unread: bool):
    condition = "r.read_at IS NULL" if unread else "r.read_at IS NOT NULL"
    order = "r.created_at ASC" if unread else "r.read_at DESC"
    with connect() as conn:
        return conn.execute(
            f"""SELECT r.*, e.name AS employee_name
                FROM reports r JOIN employees e ON e.id = r.employee_id
                WHERE {condition} ORDER BY {order}"""
        ).fetchall()


def get_report(report_id: int):
    with connect() as conn:
        return conn.execute(
            """SELECT r.*, e.name AS employee_name
               FROM reports r JOIN employees e ON e.id = r.employee_id
               WHERE r.id = ?""",
            (report_id,),
        ).fetchone()


def list_reports_for_employee(employee_id: int, ending_after: date):
    """Meldungen eines Mitarbeiters, deren Bis-Datum nicht vor `ending_after` liegt."""
    with connect() as conn:
        return conn.execute(
            """SELECT * FROM reports WHERE employee_id = ? AND date_to >= ?
               ORDER BY date_from""",
            (employee_id, ending_after.isoformat()),
        ).fetchall()


def delete_report(report_id: int):
    with connect() as conn:
        conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))


def mark_read(report_id: int | None = None):
    with connect() as conn:
        if report_id is None:
            conn.execute(
                "UPDATE reports SET read_at = datetime('now','localtime') WHERE read_at IS NULL"
            )
        else:
            conn.execute(
                "UPDATE reports SET read_at = datetime('now','localtime') WHERE id = ? AND read_at IS NULL",
                (report_id,),
            )


def mark_unread(report_id: int):
    with connect() as conn:
        conn.execute("UPDATE reports SET read_at = NULL WHERE id = ?", (report_id,))


def import_employees(rows: list[tuple[str, str, bool | None]]) -> tuple[int, int]:
    """Legt neue Mitarbeiter an bzw. aktualisiert bestehende (Abgleich über den Code).
    Läuft in einer Transaktion. Gibt (angelegt, aktualisiert) zurück."""
    created = updated = 0
    with connect() as conn:
        for name, code, active in rows:
            existing = conn.execute("SELECT id FROM employees WHERE code = ?", (code,)).fetchone()
            if existing:
                if active is None:
                    conn.execute("UPDATE employees SET name = ? WHERE id = ?", (name, existing["id"]))
                else:
                    conn.execute(
                        "UPDATE employees SET name = ?, active = ? WHERE id = ?",
                        (name, int(active), existing["id"]),
                    )
                updated += 1
            else:
                conn.execute(
                    "INSERT INTO employees (name, code, active) VALUES (?, ?, ?)",
                    (name, code, 1 if active is None else int(active)),
                )
                created += 1
    return created, updated
