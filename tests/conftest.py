import os
import tempfile

# Muss vor dem Import der App gesetzt sein
os.environ.setdefault("ADMIN_PASSWORD", "test-passwort")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DB_PATH", os.path.join(tempfile.mkdtemp(), "import.db"))
for var in ("SMTP_HOST", "SMTP_TO"):
    os.environ.pop(var, None)

import pytest
from fastapi.testclient import TestClient

from app import db, main

ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    main.code_limiter.reset()
    main.login_limiter.reset()
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def admin(client):
    r = client.post("/admin/login", data={"password": ADMIN_PASSWORD}, follow_redirects=False)
    assert r.status_code == 303
    return client


@pytest.fixture
def employee(client):
    db.create_employee("Max Mustermann", "Max123")
    return db.find_employee_by_code("Max123")


def all_reports():
    with db.connect() as conn:
        return conn.execute("SELECT * FROM reports ORDER BY id").fetchall()


def all_employees():
    with db.connect() as conn:
        return conn.execute("SELECT * FROM employees ORDER BY id").fetchall()
