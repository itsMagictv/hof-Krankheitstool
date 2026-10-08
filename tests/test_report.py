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
    ok = {"confirm_overlap": "1"}  # die Meldungen überschneiden sich untereinander
    assert submit(client, date_from=(TODAY - timedelta(days=main.MAX_PAST_DAYS)).isoformat(), **ok).status_code == 303
    assert submit(client, date_to=TODAY.isoformat(), **ok).status_code == 303  # eintägig
    assert submit(client, note="x" * main.MAX_NOTE_LENGTH, **ok).status_code == 303


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


# --- Aktive Meldungen & Überschneidungen ----------------------------------

def add_report(employee_id, start_offset, end_offset, type_="selbst"):
    from app import db
    db.create_report(employee_id, TODAY + timedelta(days=start_offset),
                     TODAY + timedelta(days=end_offset), type_, "")


def my_reports_box(html):
    if 'id="my-reports-title"' not in html:
        return ""
    return html.split('id="my-reports-title"')[1].split("</section>")[0]


def fmt(offset):
    return (TODAY + timedelta(days=offset)).strftime("%d.%m.%Y")


def test_keine_meldungen_keine_uebersicht(client, employee):
    add_report(employee["id"], -5, -1)  # nur vergangene
    assert my_reports_box(client.post("/", data={"code": "max123"}).text) == ""


def test_aktive_und_zukuenftige_meldungen_werden_angezeigt(client, employee):
    add_report(employee["id"], -2, 1, "arzt_analog")   # aktiv
    add_report(employee["id"], 0, 0)                   # aktiv (nur heute)
    add_report(employee["id"], -5, -1)                 # vorbei
    add_report(employee["id"], 1, 2)                   # ab morgen
    add_report(employee["id"], 5, 7, "arzt_digital")   # in 5 Tagen
    box = my_reports_box(client.post("/", data={"code": "max123"}).text)
    assert f"{fmt(-2)} – {fmt(1)}" in box
    assert "Ärztliche AU – Papier" in box
    assert f"{fmt(0)} – {fmt(0)}" in box
    assert f"{fmt(1)} – {fmt(2)}" in box
    assert f"{fmt(5)} – {fmt(7)}" in box
    assert fmt(-5) not in box
    assert box.count("is-active") == 2
    assert box.count("is-future") == 2
    assert "Ab morgen" in box
    assert "In 5 Tagen" in box
    assert "· 1 Kalendertag<" in box  # Einzahl
    # Reihenfolge nach Beginn
    assert box.index(fmt(-2)) < box.index(f"{fmt(0)} – {fmt(0)}") < box.index(fmt(5))


def test_nur_eigene_meldungen_sichtbar(client, employee):
    from app import db
    db.create_employee("Erika", "erika777")
    other = db.find_employee_by_code("erika777")
    add_report(other["id"], 0, 3)
    html = client.post("/", data={"code": "max123"}).text
    assert my_reports_box(html) == ""
    assert fmt(3) not in html  # auch nicht in den Daten für den Überschneidungs-Hinweis


def test_ueberschneidung_muss_bestaetigt_werden(client, employee):
    add_report(employee["id"], 0, 1)
    r = submit(client)  # heute bis +2
    assert r.status_code == 409
    assert "bereits eine Krankmeldung vor" in r.text
    assert f"{fmt(0)} – {fmt(1)}" in r.text
    assert "Trotzdem absenden" in r.text
    assert 'name="confirm_overlap" id="confirm_overlap" value="1"' in r.text
    assert len(all_reports()) == 1

    r = submit(client, confirm_overlap="1")
    assert r.status_code == 303
    assert len(all_reports()) == 2


def test_ohne_ueberschneidung_keine_rueckfrage(client, employee):
    add_report(employee["id"], -3, -1)   # endet gestern
    add_report(employee["id"], 3, 4)     # beginnt nach dem neuen Zeitraum
    assert submit(client).status_code == 303


def test_ueberschneidung_an_den_raendern(client, employee):
    add_report(employee["id"], 2, 4)     # beginnt am Bis-Tag der neuen Meldung
    assert submit(client).status_code == 409


def test_meldung_anderer_mitarbeiter_ist_keine_ueberschneidung(client, employee):
    from app import db
    db.create_employee("Erika", "erika777")
    add_report(db.find_employee_by_code("erika777")["id"], 0, 2)
    assert submit(client).status_code == 303


def test_hinweis_daten_fuer_javascript(client, employee):
    add_report(employee["id"], 0, 1)
    html = client.post("/", data={"code": "max123"}).text
    # JSON im data-Attribut, HTML-escaped
    assert "data-reports=\"[{&#34;from&#34;: &#34;" in html
    assert 'id="overlap-hint"' in html


def test_log_enthaelt_keine_mitarbeiterdaten(client, employee, caplog):
    # Logs unterliegen nicht der Löschfrist – sie dürfen keinen Personenbezug haben
    with caplog.at_level("DEBUG", logger="krankmeldung"):
        assert submit(client, note="Bemerkung-XYZ").status_code == 303
    text = caplog.text
    assert "Neue Krankmeldung eingegangen" in text
    for secret in ("Max", "max123", "Bemerkung-XYZ", f"ID {employee['id']}"):
        assert secret.lower() not in text.lower()
