"""CSV-Import und -Export der Mitarbeiterliste."""
from app import db
from tests.conftest import all_employees


def upload(client, content: bytes):
    return client.post("/admin/mitarbeiter/import", files={"file": ("m.csv", content, "text/csv")})


def employees_dict():
    return {e["code"]: (e["name"], e["active"]) for e in all_employees()}


def test_export(admin, employee):
    db.create_employee("Jürgen Größe", "jg2026x")
    db.set_employee_active(employee["id"], False)
    r = admin.get("/admin/mitarbeiter/export.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert r.content.startswith("﻿".encode())  # BOM für Excel
    lines = r.content.decode("utf-8-sig").splitlines()
    assert lines[0] == "Name;Code;Aktiv"
    assert "Jürgen Größe;jg2026x;ja" in lines
    assert "Max Mustermann;Max123;nein" in lines


def test_export_schuetzt_vor_formeln(admin):
    db.create_employee('=HYPERLINK("http://evil")', "-code123")
    text = admin.get("/admin/mitarbeiter/export.csv").content.decode("utf-8-sig")
    assert "'=HYPERLINK" in text
    assert ";'-code123;" in text


def test_export_import_roundtrip(admin):
    db.create_employee("=Formel", "+code123")
    db.create_employee("Anna; mit Semikolon", "anna1234")
    exported = admin.get("/admin/mitarbeiter/export.csv").content
    r = admin.post("/admin/mitarbeiter/1/loeschen")
    r = admin.post("/admin/mitarbeiter/2/loeschen")
    r = upload(admin, exported)
    assert employees_dict() == {"+code123": ("=Formel", 1), "anna1234": ("Anna; mit Semikolon", 1)}


def test_import_legt_an_und_aktualisiert(admin, employee):
    csv = "Name;Code;Aktiv\nMax Neu;MAX123;nein\nErika;erika77;\nOtto;otto1234;ja\n".encode()
    r = upload(admin, csv)
    assert employees_dict() == {
        "Max123": ("Max Neu", 0),   # Abgleich ohne Groß-/Kleinschreibung, Code bleibt
        "erika77": ("Erika", 1),
        "otto1234": ("Otto", 1),
    }
    assert "2 angelegt, 1 aktualisiert" in r.text


def test_import_ohne_aktiv_spalte_aendert_status_nicht(admin, employee):
    db.set_employee_active(employee["id"], False)
    r = upload(admin, b"Max Neu;max123\n")
    assert employees_dict() == {"Max123": ("Max Neu", 0)}


def test_import_ohne_kopfzeile_mit_komma(admin):
    r = upload(admin, b"Anna,anna1234\nBert,bert1234,nein\n")
    assert employees_dict() == {"anna1234": ("Anna", 1), "bert1234": ("Bert", 0)}


def test_import_windows_kodierung(admin):
    r = upload(admin, "Jürgen Größe;jg2026x\n".encode("cp1252"))
    assert employees_dict() == {"jg2026x": ("Jürgen Größe", 1)}


def test_import_fehler_bricht_alles_ab(admin, employee):
    csv = b"Name;Code\nGueltig;gueltig1\nDoppelt;GUELTIG1\nKurz;abc\nX;xyz12345;vielleicht\nNurName\n"
    r = upload(admin, csv)
    assert employees_dict() == {"Max123": ("Max Mustermann", 1)}
    text = r.text
    assert "Import abgebrochen" in text
    assert "Zeile 3" in text and "Zeile 4" in text and "Zeile 5" in text and "Zeile 6" in text


def test_import_leere_datei(admin):
    r = upload(admin, b"")
    assert "Die Datei ist leer" in r.text
    r = upload(admin, b"Name;Code;Aktiv\n")
    assert "keine Mitarbeiter" in r.text


def test_import_viele_fehler_sprengen_session_nicht(admin):
    csv = "\n".join(f"Name{i};x;{'y' * 500}" for i in range(500)).encode()
    r = upload(admin, csv)
    assert len(admin.cookies.get("km_session")) < 4000
    assert "weitere Fehler" in r.text
