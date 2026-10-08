"""Security-Header, CSRF-Schutz, Größenlimit."""
from app import main
from tests.conftest import all_employees


def test_security_header(client):
    r = client.get("/")
    csp = r.headers["content-security-policy"]
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"


def test_kein_inline_javascript(client, employee):
    # Die CSP blockiert Inline-Skripte – also dürfen auch keine im HTML stehen
    for html in (client.get("/").text, client.post("/", data={"code": "max123"}).text):
        assert "<script>" not in html
        assert " onclick=" not in html and " onsubmit=" not in html and " onchange=" not in html


def test_admin_ohne_inline_javascript(admin, employee):
    html = admin.get("/admin").text
    assert "<script>" not in html
    assert " onsubmit=" not in html and " onchange=" not in html and ' style="' not in html


def test_seiten_werden_nicht_gecacht(admin):
    assert admin.get("/admin").headers["cache-control"] == "no-store"
    assert admin.get("/admin/mitarbeiter/export.csv").headers["cache-control"] == "no-store"


def test_statische_dateien_duerfen_gecacht_werden(client):
    r = client.get("/static/style.css")
    assert r.status_code == 200
    assert r.headers.get("cache-control") != "no-store"


def test_fremde_origin_wird_abgelehnt(admin):
    r = admin.post("/admin/mitarbeiter", data={"name": "CSRF", "code": "csrf1234"},
                   headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert all_employees() == []


def test_fremder_referer_wird_abgelehnt(admin):
    r = admin.post("/admin/mitarbeiter", data={"name": "CSRF", "code": "csrf1234"},
                   headers={"Referer": "https://evil.example/seite"})
    assert r.status_code == 403


def test_eigene_origin_ist_erlaubt(admin):
    r = admin.post("/admin/mitarbeiter", data={"name": "Ok", "code": "okok1234"},
                   headers={"Origin": "http://testserver"}, follow_redirects=False)
    assert r.status_code == 303
    assert len(all_employees()) == 1


def test_origin_hinter_proxy_mit_forwarded_host(admin):
    r = admin.post("/admin/mitarbeiter", data={"name": "Ok", "code": "okok1234"},
                   headers={"Origin": "https://krank.example.de", "X-Forwarded-Host": "krank.example.de"},
                   follow_redirects=False)
    assert r.status_code == 303


def test_zu_grosse_anfrage(client):
    r = client.post("/admin/mitarbeiter/import",
                    files={"file": ("gross.csv", b"x" * (main.MAX_BODY_BYTES + 10))})
    assert r.status_code == 413


def test_keine_api_doku(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
