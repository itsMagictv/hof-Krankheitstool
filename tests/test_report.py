"""Krankmeldung durch Mitarbeiter."""
from datetime import date, timedelta

import pytest

from app import main
from tests.conftest import all_reports

TODAY = date.today()


def submit(client, **overrides):
    data = {
        "code": "max123",
        "date_from": TODAY.isoformat(),
        "date_to": (TODAY + timedelta(days=2)).isoformat(),
        "type": "arzt_digital",
        "note": "",
    }
    data.update(overrides)
    return client.post("/meldung", data=data, follow_redirects=False)


def test_startseite(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Persönlicher Code" in r.text


def test_unbekannter_code(client, employee):
    r = client.post("/", data={"code": "falsch1"})
    assert r.status_code == 400
    assert "unbekannt" in r.text


def test_code_ohne_gross_kleinschreibung_und_leerzeichen(client, employee):
    r = client.post("/", data={"code": "  MAX123 "})
    assert r.status_code == 200
    assert "Hallo Max Mustermann" in r.text
    # Von und Bis sind mit heute vorbelegt
    assert r.text.count(f'value="{TODAY.isoformat()}"') == 2


def test_deaktivierter_code_wird_abgelehnt(client, employee):
    from app import db
    db.set_employee_active(employee["id"], False)
    assert client.post("/", data={"code": "max123"}).status_code == 400
    assert submit(client).status_code == 400
    assert all_reports() == []


def test_meldung_wird_gespeichert(client, employee):
    r = submit(client, note="Bin ab Freitag wieder da")
    assert r.status_code == 303
    assert r.headers["location"] == "/gesendet"
    [report] = all_reports()
    assert report["employee_id"] == employee["id"]
    assert report["type"] == "arzt_digital"
    assert report["note"] == "Bin ab Freitag wieder da"
    assert report["read_at"] is None


def test_gesendet_seite(client):
    r = client.get("/gesendet")
    assert r.status_code == 200
    assert "Krankmeldung gesendet" in r.text


@pytest.mark.parametrize("overrides, message", [
    ({"date_to": (TODAY - timedelta(days=1)).isoformat()}, "nicht vor dem Von-Datum"),
    ({"date_from": (TODAY - timedelta(days=main.MAX_PAST_DAYS + 1)).isoformat()}, "zurückliegen"),
    ({"date_from": (TODAY + timedelta(days=main.MAX_FUTURE_DAYS + 1)).isoformat(),
      "date_to": (TODAY + timedelta(days=main.MAX_FUTURE_DAYS + 2)).isoformat()}, "in der Zukunft"),
    ({"date_to": (TODAY + timedelta(days=main.MAX_DURATION_DAYS)).isoformat()}, "zu lang"),
    ({"date_from": "kein-datum"}, "gültiges Von- und Bis-Datum"),
    ({"date_to": ""}, "gültiges Von- und Bis-Datum"),
    ({"type": "erfunden"}, "Art der Krankmeldung"),
    ({"type": ""}, "Art der Krankmeldung"),
    ({"note": "x" * (main.MAX_NOTE_LENGTH + 1)}, "Bemerkung ist zu lang"),
])
def test_ungueltige_meldung(client, employee, overrides, message):
    r = submit(client, **overrides)
    assert r.status_code == 400
    assert message in r.text
    assert all_reports() == []


def test_grenzwerte_sind_erlaubt(client, employee):
    assert submit(client, date_from=(TODAY - timedelta(days=main.MAX_PAST_DAYS)).isoformat()).status_code == 303
    assert submit(client, date_to=TODAY.isoformat()).status_code == 303  # eintägig
    assert submit(client, note="x" * main.MAX_NOTE_LENGTH).status_code == 303


def test_fehlerhafte_eingaben_bleiben_erhalten(client, employee):
    r = submit(client, type="", note="Meine Notiz")
    assert "Meine Notiz" in r.text


def test_rate_limit_fuer_codes(client, employee):
    for i in range(10):
        assert client.post("/", data={"code": f"falsch{i}"}).status_code == 400
    r = client.post("/", data={"code": "max123"})
    assert "Zu viele Fehlversuche" in r.text
    # Auch das Absenden ist gesperrt
    assert submit(client).status_code == 400
    assert all_reports() == []
