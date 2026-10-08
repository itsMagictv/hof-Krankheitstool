"""Sicherheits-Log: Ereignisse mit gekürzter IP, ohne Codes/Passwörter/Namen."""
import logging

import pytest

from app import main
from tests.conftest import ADMIN_PASSWORD

LOGGER = "krankmeldung.security"


@pytest.mark.parametrize("ip, expected", [
    ("192.168.10.57", "192.168.10.xxx"),
    ("10.0.3.1", "10.0.3.xxx"),
    ("2001:db8:abcd:1234:5678::1", "2001:db8:abcd::xxx"),
    ("::1", "::xxx"),
    ("testclient", "unbekannt"),
    ("unknown", "unbekannt"),
])
def test_ip_wird_gekuerzt(ip, expected):
    assert main.anonymize_ip(ip) == expected


def security_lines(caplog):
    return [r.getMessage() for r in caplog.records if r.name == LOGGER]


def test_erfolgreicher_login_wird_geloggt(client, caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER):
        client.post("/admin/login", data={"password": ADMIN_PASSWORD})
    assert security_lines(caplog) == ["SICHERHEIT Admin-Login erfolgreich (IP unbekannt)"]


def test_fehlgeschlagener_login_ohne_passwort_im_log(client, caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER):
        client.post("/admin/login", data={"password": "geheimer-versuch"})
    assert security_lines(caplog) == ["SICHERHEIT Admin-Login fehlgeschlagen (IP unbekannt)"]
    assert "geheimer-versuch" not in caplog.text


def test_login_sperre_wird_einmal_geloggt(client, caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER):
        for _ in range(8):
            client.post("/admin/login", data={"password": "falsch"})
    lines = security_lines(caplog)
    assert lines.count("SICHERHEIT Admin-Login fehlgeschlagen (IP unbekannt)") == 4
    assert sum("Admin-Passwörter" in l and "gesperrt" in l for l in lines) == 1
    # Weitere Versuche während der Sperre fluten das Log nicht
    assert len(lines) == 5


def test_code_sperre_wird_geloggt_ohne_codes(client, employee, caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER):
        for i in range(12):
            client.post("/", data={"code": f"versuch{i}"})
    lines = security_lines(caplog)
    assert len(lines) == 1
    assert "Mitarbeiter-Codes" in lines[0] and "gesperrt" in lines[0]
    assert "versuch" not in caplog.text


def test_einzelne_falsche_codes_werden_nicht_geloggt(client, employee, caplog):
    # Tippfehler von Mitarbeitern sind kein Sicherheitsereignis
    with caplog.at_level(logging.INFO, logger=LOGGER):
        client.post("/", data={"code": "vertippt"})
    assert security_lines(caplog) == []


def test_meldung_erzeugt_keinen_sicherheitseintrag(client, employee, caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER):
        client.post("/", data={"code": "max123"})
    assert security_lines(caplog) == []


def test_abschaltbar(client, monkeypatch, caplog):
    monkeypatch.setattr(main, "SECURITY_LOG", False)
    with caplog.at_level(logging.INFO, logger=LOGGER):
        client.post("/admin/login", data={"password": "falsch"})
        client.post("/admin/login", data={"password": ADMIN_PASSWORD})
    assert security_lines(caplog) == []
