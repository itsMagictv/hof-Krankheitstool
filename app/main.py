import asyncio
import csv
import hashlib
import hmac
import io
import logging
import os
import re
import secrets
import smtplib
import sqlite3
import ssl
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import db

log = logging.getLogger("krankmeldung")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

BASE_DIR = Path(__file__).parent
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
COMPANY_NAME = os.environ.get("COMPANY_NAME", "Hof Dinkelberg")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip("/")
SECURE_COOKIES = os.environ.get("SECURE_COOKIES", "false").lower() == "true"
MAX_PAST_DAYS = 14      # "Von" darf höchstens so weit in der Vergangenheit liegen
MAX_FUTURE_DAYS = 30    # ... und höchstens so weit in der Zukunft
MAX_DURATION_DAYS = 366
MAX_NOTE_LENGTH = 1000
MIN_CODE_LENGTH = 6
MAX_CODE_LENGTH = 64
MAX_NAME_LENGTH = 120
MAX_BODY_BYTES = 1_000_000
CODE_PATTERN = re.compile(r"^[!-~]+$")  # druckbares ASCII ohne Leerzeichen
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")

if not ADMIN_PASSWORD:
    raise RuntimeError("ADMIN_PASSWORD muss gesetzt sein (siehe .env.example).")
if not os.environ.get("SECRET_KEY"):
    log.warning("SECRET_KEY nicht gesetzt – Admin-Sessions gehen bei jedem Neustart verloren.")


# --- Rate-Limit gegen Durchprobieren von Codes / Passwort ------------------

class RateLimiter:
    def __init__(self, max_failures: int, window_seconds: int):
        self.max_failures = max_failures
        self.window = window_seconds
        self.failures: dict[str, deque] = {}
        self.lock = threading.Lock()

    def _prune(self, key: str) -> deque | None:
        q = self.failures.get(key)
        if q is None:
            return None
        cutoff = time.monotonic() - self.window
        while q and q[0] < cutoff:
            q.popleft()
        if not q:
            del self.failures[key]
            return None
        return q

    def blocked(self, key: str) -> bool:
        with self.lock:
            q = self._prune(key)
            return q is not None and len(q) >= self.max_failures

    def fail(self, key: str):
        with self.lock:
            self.failures.setdefault(key, deque()).append(time.monotonic())

    def reset(self):
        with self.lock:
            self.failures.clear()


code_limiter = RateLimiter(max_failures=10, window_seconds=15 * 60)
login_limiter = RateLimiter(max_failures=5, window_seconds=15 * 60)


def client_ip(request: Request) -> str:
    # Hinter einem Reverse Proxy setzt uvicorn (--proxy-headers) hier die echte IP,
    # sofern der Proxy in FORWARDED_ALLOW_IPS steht.
    return request.client.host if request.client else "unknown"


# --- E-Mail (optional) ----------------------------------------------------

def send_notification(name: str, date_from: date, date_to: date):
    host = os.environ.get("SMTP_HOST")
    to = os.environ.get("SMTP_TO")
    if not host or not to:
        return

    def _send():
        try:
            msg = EmailMessage()
            msg["Subject"] = f"Neue Krankmeldung: {name}"
            msg["From"] = os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER") or to
            msg["To"] = to
            body = (
                f"{name} hat sich krankgemeldet.\n"
                f"Zeitraum: {date_from:%d.%m.%Y} – {date_to:%d.%m.%Y}\n\n"
                "Details im Admin-Bereich"
                + (f": {PUBLIC_URL}/admin" if PUBLIC_URL else ".")
                + "\n"
            )
            msg.set_content(body)

            port = int(os.environ.get("SMTP_PORT", "587"))
            mode = os.environ.get("SMTP_TLS", "starttls").lower()
            user = os.environ.get("SMTP_USER")
            password = os.environ.get("SMTP_PASSWORD")
            ctx = ssl.create_default_context()
            if mode == "ssl":
                server = smtplib.SMTP_SSL(host, port, context=ctx, timeout=20)
            else:
                server = smtplib.SMTP(host, port, timeout=20)
                if mode == "starttls":
                    server.starttls(context=ctx)
            with server:
                if user:
                    server.login(user, password or "")
                server.send_message(msg)
        except Exception:
            log.exception("E-Mail-Benachrichtigung fehlgeschlagen")

    threading.Thread(target=_send, daemon=True).start()


# --- Middleware -----------------------------------------------------------

class BodySizeLimitMiddleware:
    """Weist zu große Requests ab, bevor FastAPI Formulare/Uploads einliest –
    das passiert nämlich noch vor jeder Login-Prüfung im Endpoint."""

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        length = dict(scope["headers"]).get(b"content-length")
        if length is not None and (not length.isdigit() or int(length) > self.max_bytes):
            response = PlainTextResponse("Anfrage zu groß.", status_code=413)
            return await response(scope, receive, send)

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    # Bei Chunked-Uploads ohne Content-Length: Verbindung als beendet melden
                    return {"type": "http.disconnect"}
            return message

        await self.app(scope, limited_receive, send)


def host_of(value: str | None) -> str | None:
    if not value:
        return None
    return urlsplit(value).netloc.lower() or None


SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
        "font-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


# --- App ------------------------------------------------------------------

async def purge_loop():
    while True:
        try:
            deleted = db.purge_old_reports()
            if deleted:
                log.info("%d alte Meldung(en) gelöscht", deleted)
        except Exception:
            log.exception("Löschlauf fehlgeschlagen")
        await asyncio.sleep(6 * 60 * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    task = asyncio.create_task(purge_loop())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # CSRF-Schutz zusätzlich zu SameSite=strict: Cross-Origin-POSTs ablehnen.
    if request.method == "POST":
        origin = host_of(request.headers.get("origin")) or host_of(request.headers.get("referer"))
        allowed = {
            (request.headers.get("host") or "").lower(),
            (request.headers.get("x-forwarded-host") or "").lower(),
            host_of(PUBLIC_URL) or "",
        } - {""}
        if origin is not None and origin not in allowed:
            return PlainTextResponse("Ungültige Herkunft der Anfrage.", status_code=403)

    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    if not request.url.path.startswith("/static/"):
        # Seiten mit Gesundheitsdaten nicht im Browser-/Proxy-Cache ablegen
        response.headers["Cache-Control"] = "no-store"
    if SECURE_COOKIES:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    return response


app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="km_session",
    max_age=8 * 60 * 60,
    same_site="strict",
    https_only=SECURE_COOKIES,
)
app.add_middleware(BodySizeLimitMiddleware, max_bytes=MAX_BODY_BYTES)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["company_name"] = COMPANY_NAME
templates.env.globals["report_types"] = db.REPORT_TYPES


def fmt_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return value or ""


def fmt_datetime(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError):
        return value or ""


def day_count(date_from: str, date_to: str) -> int:
    return (date.fromisoformat(date_to) - date.fromisoformat(date_from)).days + 1


templates.env.filters["date"] = fmt_date
templates.env.filters["datetime"] = fmt_datetime
templates.env.globals["day_count"] = day_count
templates.env.globals["min_code_length"] = MIN_CODE_LENGTH


def render(request: Request, name: str, status_code: int = 200, **ctx):
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def shorten(value: str, limit: int = 40) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


# --- Mitarbeiter-Seite ----------------------------------------------------

def check_code(request: Request, code: str):
    """Gibt (employee, error) zurück."""
    ip = client_ip(request)
    if code_limiter.blocked(ip):
        return None, "Zu viele Fehlversuche. Bitte in 15 Minuten erneut versuchen."
    code = code.strip()
    employee = db.find_employee_by_code(code) if 0 < len(code) <= MAX_CODE_LENGTH else None
    if employee is None:
        code_limiter.fail(ip)
        return None, "Dieser Code ist unbekannt. Bitte prüfe deine Eingabe."
    return employee, None


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return render(request, "index.html")


def render_form(request: Request, employee, code: str, values: dict, status_code: int = 200, **ctx):
    today = date.today()
    # Alle Meldungen, mit denen sich eine neue Meldung überschneiden könnte
    reports = db.list_reports_for_employee(employee["id"], today - timedelta(days=MAX_PAST_DAYS))
    # Aktive (heute im Zeitraum) und zukünftige Meldungen für die Übersicht
    upcoming = [
        {
            "date_from": r["date_from"],
            "date_to": r["date_to"],
            "type": r["type"],
            "active": r["date_from"] <= today.isoformat(),
            "days": day_count(r["date_from"], r["date_to"]),
            "starts_in": (date.fromisoformat(r["date_from"]) - today).days,
        }
        for r in reports if r["date_to"] >= today.isoformat()
    ]
    existing = [
        {"from": r["date_from"], "to": r["date_to"], "text": f"{fmt_date(r['date_from'])} – {fmt_date(r['date_to'])}"}
        for r in reports
    ]
    return render(
        request, "form.html", status_code=status_code,
        employee=employee, code=code.strip(), values=values,
        upcoming_reports=upcoming, existing_reports=existing, **ctx,
    )


def overlapping(reports, d_from: date, d_to: date):
    return [r for r in reports if r["date_from"] <= d_to.isoformat() and d_from.isoformat() <= r["date_to"]]


@app.post("/", response_class=HTMLResponse)
def enter_code(request: Request, code: str = Form("")):
    employee, error = check_code(request, code)
    if error:
        return render(request, "index.html", status_code=400, error=error)
    today = date.today().isoformat()
    return render_form(
        request, employee, code,
        {"date_from": today, "date_to": today, "type": "", "note": ""},
    )


def validate_report(date_from: str, date_to: str, type_: str, note: str):
    """Gibt (d_from, d_to, errors) zurück."""
    errors = []
    d_from = d_to = None
    try:
        d_from = date.fromisoformat(date_from)
        d_to = date.fromisoformat(date_to)
    except ValueError:
        errors.append("Bitte gib ein gültiges Von- und Bis-Datum an.")
    else:
        today = date.today()
        if d_to < d_from:
            errors.append("Das Bis-Datum darf nicht vor dem Von-Datum liegen.")
        if d_from < today - timedelta(days=MAX_PAST_DAYS):
            errors.append(f"Das Von-Datum darf höchstens {MAX_PAST_DAYS} Tage zurückliegen.")
        if d_from > today + timedelta(days=MAX_FUTURE_DAYS):
            errors.append(f"Das Von-Datum darf höchstens {MAX_FUTURE_DAYS} Tage in der Zukunft liegen.")
        if (d_to - d_from).days >= MAX_DURATION_DAYS:
            errors.append("Der Zeitraum ist zu lang.")
    if type_ not in db.REPORT_TYPES:
        errors.append("Bitte wähle die Art der Krankmeldung aus.")
    if len(note) > MAX_NOTE_LENGTH:
        errors.append(f"Die Bemerkung ist zu lang (max. {MAX_NOTE_LENGTH} Zeichen).")
    return d_from, d_to, errors


@app.post("/meldung", response_class=HTMLResponse)
def submit_report(
    request: Request,
    code: str = Form(""),
    date_from: str = Form(""),
    date_to: str = Form(""),
    type: str = Form(""),
    note: str = Form(""),
    confirm_overlap: str = Form(""),
):
    employee, error = check_code(request, code)
    if error:
        return render(request, "index.html", status_code=400, error=error)

    values = {"date_from": date_from, "date_to": date_to, "type": type, "note": note}
    d_from, d_to, errors = validate_report(date_from, date_to, type, note)
    if errors:
        return render_form(request, employee, code, values, status_code=400, errors=errors)

    # Überschneidung ist erlaubt (z. B. ärztliche AU nach Selbstmeldung), muss aber bestätigt werden.
    # Mit JavaScript sieht der Mitarbeiter den Hinweis schon vorher und bestätigt mit dem Absenden.
    if confirm_overlap != "1":
        clashes = overlapping(db.list_reports_for_employee(employee["id"], d_from), d_from, d_to)
        if clashes:
            return render_form(
                request, employee, code, values, status_code=409,
                overlap=[f"{fmt_date(r['date_from'])} – {fmt_date(r['date_to'])}" for r in clashes],
            )

    db.create_report(employee["id"], d_from, d_to, type, note)
    log.info("Neue Krankmeldung (Mitarbeiter-ID %s)", employee["id"])
    send_notification(employee["name"], d_from, d_to)
    return RedirectResponse("/gesendet", status_code=303)


@app.get("/gesendet", response_class=HTMLResponse)
def sent(request: Request):
    return render(request, "sent.html")


# --- Admin ----------------------------------------------------------------

def admin_token() -> str:
    # Hängt vom Passwort ab: Wird ADMIN_PASSWORD geändert, sind alle Sessions ungültig.
    return hmac.new(SECRET_KEY.encode(), ADMIN_PASSWORD.encode(), hashlib.sha256).hexdigest()


def is_admin(request: Request) -> bool:
    token = request.session.get("admin")
    return isinstance(token, str) and hmac.compare_digest(token, admin_token())


def flash(request: Request, message: str, kind: str = "ok", details: list[str] | None = None):
    # Die Session steckt im Cookie (max. ~4 KB) – daher Länge begrenzen.
    request.session["flash"] = {
        "message": shorten(message, 300),
        "kind": kind,
        "details": [shorten(d, 160) for d in (details or [])[:10]],
    }


def back_to_admin(anchor: str = "") -> RedirectResponse:
    return RedirectResponse(f"/admin{anchor}", status_code=303)


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    if not is_admin(request):
        return render(request, "admin_login.html")
    return render(
        request, "admin.html",
        unread=db.list_reports(unread=True),
        read=db.list_reports(unread=False),
        employees=db.list_employees(),
        flash=request.session.pop("flash", None),
        draft=request.session.pop("employee_draft", None),
        retention_days=db.RETENTION_DAYS,
    )


@app.post("/admin/login")
def admin_login(request: Request, password: str = Form("")):
    ip = client_ip(request)
    if login_limiter.blocked(ip):
        return render(request, "admin_login.html", status_code=429,
                      error="Zu viele Fehlversuche. Bitte in 15 Minuten erneut versuchen.")
    if not hmac.compare_digest(password.encode(), ADMIN_PASSWORD.encode()):
        login_limiter.fail(ip)
        return render(request, "admin_login.html", status_code=401, error="Falsches Passwort.")
    request.session.clear()
    request.session["admin"] = admin_token()
    return back_to_admin()


@app.post("/admin/logout")
def admin_logout(request: Request):
    request.session.clear()
    return back_to_admin()


@app.post("/admin/meldungen/{report_id:int}/gelesen")
def report_read(request: Request, report_id: int):
    if is_admin(request):
        db.mark_read(report_id)
    return back_to_admin()


@app.post("/admin/meldungen/{report_id:int}/ungelesen")
def report_unread(request: Request, report_id: int):
    if is_admin(request):
        db.mark_unread(report_id)
    return back_to_admin()


@app.post("/admin/meldungen/{report_id:int}/loeschen")
def report_delete(request: Request, report_id: int):
    if is_admin(request):
        report = db.get_report(report_id)
        if report:
            db.delete_report(report_id)
            flash(request, f"Meldung von {report['employee_name']} "
                           f"({fmt_date(report['date_from'])} – {fmt_date(report['date_to'])}) wurde gelöscht.")
    return back_to_admin()


@app.post("/admin/meldungen/alle-gelesen")
def reports_all_read(request: Request):
    if is_admin(request):
        db.mark_read()
    return back_to_admin()


def employee_format_error(name: str, code: str) -> str | None:
    if not name:
        return "Bitte einen Namen angeben."
    if len(name) > MAX_NAME_LENGTH:
        return f"Der Name ist zu lang (max. {MAX_NAME_LENGTH} Zeichen)."
    if CONTROL_CHARS.search(name):
        return "Der Name enthält ungültige Zeichen."
    if len(code) < MIN_CODE_LENGTH:
        return f"Der Code muss mindestens {MIN_CODE_LENGTH} Zeichen lang sein."
    if len(code) > MAX_CODE_LENGTH:
        return f"Der Code ist zu lang (max. {MAX_CODE_LENGTH} Zeichen)."
    if not CODE_PATTERN.match(code):
        return "Der Code darf nur Buchstaben ohne Umlaute, Ziffern und Sonderzeichen enthalten (keine Leerzeichen)."
    return None


def validate_employee(name: str, code: str, exclude_id: int | None = None) -> str | None:
    name, code = name.strip(), code.strip()
    if error := employee_format_error(name, code):
        return error
    if db.code_taken(code, exclude_id):
        return f"Der Code „{code}“ ist bereits vergeben (Groß-/Kleinschreibung wird nicht unterschieden)."
    return None


CODE_TAKEN_RACE = "Der Code ist bereits vergeben."


@app.post("/admin/mitarbeiter")
def employee_create(request: Request, name: str = Form(""), code: str = Form("")):
    if not is_admin(request):
        return back_to_admin()
    error = validate_employee(name, code)
    if not error:
        try:
            db.create_employee(name, code)
        except sqlite3.IntegrityError:
            error = CODE_TAKEN_RACE
    if error:
        flash(request, error, "error")
        request.session["employee_draft"] = {
            "name": name[:MAX_NAME_LENGTH], "code": code[:MAX_CODE_LENGTH],
        }
    else:
        request.session.pop("employee_draft", None)
        flash(request, f"{name.strip()} wurde angelegt.")
    return back_to_admin("#mitarbeiter")


@app.post("/admin/mitarbeiter/{employee_id:int}")
def employee_update(request: Request, employee_id: int, name: str = Form(""), code: str = Form("")):
    if not is_admin(request):
        return back_to_admin()
    if db.get_employee(employee_id) is None:
        flash(request, "Diesen Mitarbeiter gibt es nicht mehr.", "error")
        return back_to_admin("#mitarbeiter")
    error = validate_employee(name, code, exclude_id=employee_id)
    if not error:
        try:
            db.update_employee(employee_id, name, code)
        except sqlite3.IntegrityError:
            error = CODE_TAKEN_RACE
    if error:
        flash(request, error, "error")
    else:
        flash(request, f"{name.strip()} wurde gespeichert.")
    return back_to_admin("#mitarbeiter")


@app.post("/admin/mitarbeiter/{employee_id:int}/aktiv")
def employee_toggle(request: Request, employee_id: int):
    if is_admin(request):
        employee = db.get_employee(employee_id)
        if employee:
            db.set_employee_active(employee_id, not employee["active"])
            state = "aktiviert" if not employee["active"] else "deaktiviert"
            flash(request, f"{employee['name']} wurde {state}.")
    return back_to_admin("#mitarbeiter")


@app.post("/admin/mitarbeiter/{employee_id:int}/loeschen")
def employee_delete(request: Request, employee_id: int):
    if is_admin(request):
        employee = db.get_employee(employee_id)
        if employee:
            db.delete_employee(employee_id)
            flash(request, f"{employee['name']} und alle zugehörigen Meldungen wurden gelöscht.")
    return back_to_admin("#mitarbeiter")


# --- CSV-Import/-Export ---------------------------------------------------

CSV_HEADER = ["Name", "Code", "Aktiv"]
TRUE_VALUES = {"1", "ja", "j", "yes", "y", "true", "x", "aktiv"}
FALSE_VALUES = {"0", "nein", "n", "no", "false", "inaktiv", "deaktiviert"}
FORMULA_PREFIXES = ("=", "+", "-", "@")


def csv_escape(value: str) -> str:
    """Verhindert, dass Excel Werte wie '=HYPERLINK(...)' als Formel ausführt."""
    return "'" + value if value.startswith(FORMULA_PREFIXES) else value


def csv_unescape(value: str) -> str:
    if value.startswith("'") and value[1:].startswith(FORMULA_PREFIXES):
        return value[1:]
    return value


@app.get("/admin/mitarbeiter/export.csv")
def employee_export(request: Request):
    if not is_admin(request):
        return back_to_admin()
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(CSV_HEADER)
    for e in db.list_employees():
        writer.writerow([csv_escape(e["name"]), csv_escape(e["code"]), "ja" if e["active"] else "nein"])
    # BOM, damit Excel Umlaute korrekt erkennt
    content = "﻿" + buf.getvalue()
    filename = f"mitarbeiter-{date.today().isoformat()}.csv"
    return Response(
        content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def parse_employee_csv(raw: bytes) -> tuple[list[tuple[str, str, bool | None]], list[str]]:
    """Liest eine CSV mit den Spalten Name;Code[;Aktiv]. Gibt (rows, errors) zurück."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")  # ältere Excel-Exporte
    lines = text.splitlines()
    if not lines:
        return [], ["Die Datei ist leer."]
    delimiter = ";" if lines[0].count(";") >= lines[0].count(",") else ","

    rows, errors, seen = [], [], {}
    for lineno, fields in enumerate(csv.reader(lines, delimiter=delimiter), start=1):
        fields = [csv_unescape(f.strip()) for f in fields]
        if not any(fields):
            continue
        if lineno == 1 and fields[0].lower() == "name":
            continue  # Kopfzeile
        if len(fields) < 2:
            errors.append(f"Zeile {lineno}: Name und Code erforderlich.")
            continue
        name, code = fields[0], fields[1]
        active = None
        if len(fields) > 2 and fields[2]:
            value = fields[2].lower()
            if value in TRUE_VALUES:
                active = True
            elif value in FALSE_VALUES:
                active = False
            else:
                errors.append(f"Zeile {lineno}: „{shorten(fields[2], 20)}“ ist kein gültiger Wert für Aktiv (ja/nein).")
                continue
        if error := employee_format_error(name, code):
            errors.append(f"Zeile {lineno}: {error}")
            continue
        key = code.lower()
        if key in seen:
            errors.append(f"Zeile {lineno}: Code „{shorten(code, 20)}“ kommt bereits in Zeile {seen[key]} vor.")
            continue
        seen[key] = lineno
        rows.append((name, code, active))
    if not rows and not errors:
        errors.append("Die Datei enthält keine Mitarbeiter.")
    return rows, errors


@app.post("/admin/mitarbeiter/import")
async def employee_import(request: Request, file: UploadFile = File(...)):
    if not is_admin(request):
        return back_to_admin()
    raw = await file.read(MAX_BODY_BYTES + 1)
    if len(raw) > MAX_BODY_BYTES:
        flash(request, "Die Datei ist zu groß (max. 1 MB).", "error")
        return back_to_admin("#mitarbeiter")
    rows, errors = parse_employee_csv(raw)
    if errors:
        extra = f" (+ {len(errors) - 10} weitere Fehler)" if len(errors) > 10 else ""
        flash(request, f"Import abgebrochen – es wurde nichts geändert.{extra}", "error", errors)
        return back_to_admin("#mitarbeiter")
    created, updated = db.import_employees(rows)
    flash(request, f"Import erfolgreich: {created} angelegt, {updated} aktualisiert.")
    return back_to_admin("#mitarbeiter")


@app.get("/health")
def health():
    return {"status": "ok"}
