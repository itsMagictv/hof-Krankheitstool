"""Admin-Bereich: Login, Meldungen, Mitarbeiterverwaltung, Löschfrist."""
from datetime import date, timedelta

import pytest

from app import db, main
from tests.conftest import ADMIN_PASSWORD, all_employees, all_reports


def add_report(employee_id, date_from=None, date_to=None, note=""):
    today = date.today()
    db.create_report(employee_id, date_from or today, date_to or today, "selbst", note)
    return all_reports()[-1]


# --- Login ---------------------------------------------------------------

def test_ohne_login_nur_loginseite(client, employee):
    add_report(employee["id"], note="geheim")
    r = client.get("/admin")
    assert r.status_code == 200
    assert 'name="password"' in r.text
    assert "geheim" not in r.text
    assert "Max Mustermann" not in r.text


def test_falsches_passwort(client):
    r = client.post("/admin/login", data={"password": "falsch"})
    assert r.status_code == 401
    assert "Falsches Passwort" in r.text


def test_login_und_logout(admin):
    assert "Neue Meldungen" in admin.get("/admin").text
    r = admin.post("/admin/logout")
    assert 'name="password"' in r.text


def test_login_rate_limit(client):
    for _ in range(5):
        client.post("/admin/login", data={"password": "falsch"})
    r = client.post("/admin/login", data={"password": ADMIN_PASSWORD})
    assert r.status_code == 429


def test_passwortwechsel_beendet_sessions(admin, monkeypatch):
    monkeypatch.setattr(main, "ADMIN_PASSWORD", "neues-passwort")
    assert 'name="password"' in admin.get("/admin").text


def test_manipulierte_session_wird_abgelehnt(client):
    client.cookies.set("km_session", "eyJhZG1pbiI6IHRydWV9.manipuliert.signatur")
    assert 'name="password"' in client.get("/admin").text


@pytest.mark.parametrize("path, data", [
    ("/admin/meldungen/1/gelesen", {}),
    ("/admin/meldungen/alle-gelesen", {}),
    ("/admin/mitarbeiter", {"name": "Hacker", "code": "hack1234"}),
    ("/admin/mitarbeiter/1", {"name": "Hacker", "code": "hack1234"}),
    ("/admin/mitarbeiter/1/aktiv", {}),
    ("/admin/mitarbeiter/1/loeschen", {}),
])
def test_aktionen_ohne_login_wirkungslos(client, employee, path, data):
    add_report(employee["id"])
    r = client.post(path, data=data, follow_redirects=False)
    assert r.status_code == 303
    [e] = all_employees()
    assert (e["name"], e["code"], e["active"]) == ("Max Mustermann", "Max123", 1)
    assert all_reports()[0]["read_at"] is None


def test_import_ohne_login_wirkungslos(client):
    r = client.post("/admin/mitarbeiter/import",
                    files={"file": ("m.csv", b"Hacker;hack1234\n")}, follow_redirects=False)
    assert r.status_code == 303
    assert all_employees() == []


def test_export_ohne_login(client, employee):
    r = client.get("/admin/mitarbeiter/export.csv", follow_redirects=False)
    assert r.status_code == 303
    assert "Max123" not in r.text


# --- Meldungen -----------------------------------------------------------

def test_ungelesene_meldungen_und_escaping(admin, employee):
    add_report(employee["id"], note="<script>alert(1)</script>")
    r = admin.get("/admin")
    assert "Max Mustermann" in r.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in r.text
    assert "<script>alert(1)" not in r.text


def test_gelesen_und_ungelesen(admin, employee):
    report = add_report(employee["id"])
    r = admin.post(f"/admin/meldungen/{report['id']}/gelesen")
    assert all_reports()[0]["read_at"] is not None
    r = admin.post(f"/admin/meldungen/{report['id']}/ungelesen")
    assert all_reports()[0]["read_at"] is None


def test_alle_gelesen(admin, employee):
    for _ in range(3):
        add_report(employee["id"])
    r = admin.post("/admin/meldungen/alle-gelesen")
    assert all(r["read_at"] for r in all_reports())


def test_loeschfrist_ab_bis_datum(client, employee):
    today = date.today()
    days = db.RETENTION_DAYS
    add_report(employee["id"], today - timedelta(days=60), today - timedelta(days=days + 1))  # weg
    add_report(employee["id"], today - timedelta(days=60), today - timedelta(days=days))      # bleibt
    add_report(employee["id"], today, today)                                                  # bleibt
    assert db.purge_old_reports() == 1
    assert [r["date_to"] for r in all_reports()] == [
        (today - timedelta(days=days)).isoformat(), today.isoformat(),
    ]


def test_loeschfrist_greift_auch_bei_ungelesenen(client, employee):
    add_report(employee["id"], date(2000, 1, 1), date(2000, 1, 2))
    db.purge_old_reports()
    assert all_reports() == []


# --- Mitarbeiter ---------------------------------------------------------

def test_mitarbeiter_anlegen(admin):
    r = admin.post("/admin/mitarbeiter", data={"name": " Erika Muster ", "code": " erika77 "})
    [e] = all_employees()
    assert (e["name"], e["code"], e["active"]) == ("Erika Muster", "erika77", 1)
    assert "Erika Muster wurde angelegt" in r.text


@pytest.mark.parametrize("code", ["Max123", "MAX123", " max123 "])
def test_doppelter_code_wird_abgelehnt(admin, employee, code):
    r = admin.post("/admin/mitarbeiter", data={"name": "Doppelt", "code": code})
    assert len(all_employees()) == 1
    assert "bereits vergeben" in r.text
    assert 'value="Doppelt"' in r.text  # Eingabe bleibt erhalten


@pytest.mark.parametrize("name, code, message", [
    ("", "gueltig1", "Namen angeben"),
    ("A", "kurz", "mindestens"),
    ("A", "x" * 65, "zu lang"),
    ("A" * 121, "gueltig1", "zu lang"),
    ("A", "mit leer", "keine Leerzeichen"),
    ("A", "jürgen1", "ohne Umlaute"),
    ("Böse\r\nBcc: x@y.de", "gueltig1", "ungültige Zeichen"),
])
def test_ungueltige_mitarbeiter(admin, name, code, message):
    r = admin.post("/admin/mitarbeiter", data={"name": name, "code": code})
    assert all_employees() == []
    assert message in r.text


def test_riesige_eingabe_sprengt_session_nicht(admin):
    r = admin.post("/admin/mitarbeiter", data={"name": "A" * 50_000, "code": "B" * 50_000})
    # Wäre das Session-Cookie > 4 KB, wäre der Admin jetzt ausgeloggt
    assert len(admin.cookies.get("km_session")) < 4000
    assert "Neue Meldungen" in admin.get("/admin").text


def test_mitarbeiter_bearbeiten(admin, employee):
    r = admin.post(f"/admin/mitarbeiter/{employee['id']}", data={"name": "Max M.", "code": "neu12345"})
    [e] = all_employees()
    assert (e["name"], e["code"]) == ("Max M.", "neu12345")


def test_eigenen_code_behalten_ist_erlaubt(admin, employee):
    r = admin.post(f"/admin/mitarbeiter/{employee['id']}", data={"name": "Max M.", "code": "MAX123"})
    assert all_employees()[0]["code"] == "MAX123"


def test_bearbeiten_mit_fremdem_code(admin, employee):
    db.create_employee("Erika", "erika77")
    r = admin.post(f"/admin/mitarbeiter/{employee['id']}", data={"name": "Max", "code": "ERIKA77"})
    assert all_employees()[0]["code"] == "Max123"
    assert "bereits vergeben" in r.text


def test_bearbeiten_unbekannter_mitarbeiter(admin):
    r = admin.post("/admin/mitarbeiter/999", data={"name": "X", "code": "gueltig1"})
    assert all_employees() == []
    assert "gibt es nicht mehr" in r.text


def test_deaktivieren_und_aktivieren(admin, employee):
    r = admin.post(f"/admin/mitarbeiter/{employee['id']}/aktiv")
    assert all_employees()[0]["active"] == 0
    r = admin.post(f"/admin/mitarbeiter/{employee['id']}/aktiv")
    assert all_employees()[0]["active"] == 1


def test_loeschen_entfernt_auch_meldungen(admin, employee):
    add_report(employee["id"])
    r = admin.post(f"/admin/mitarbeiter/{employee['id']}/loeschen")
    assert all_employees() == []
    assert all_reports() == []
