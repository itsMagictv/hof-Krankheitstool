# Krankmeldung – Übergangslösung

Kleines Web-Tool, über das sich Mitarbeiter mit einem persönlichen Code krankmelden.
Ein Admin-Bereich zeigt neue Meldungen an und verwaltet die Mitarbeiter-Codes.

- **Stack:** Python 3.13 · FastAPI · Jinja2 · SQLite (ein Container, keine externe DB)
- **Design:** angelehnt an hof-dinkelberg.de; Hintergrundbild von Pixabay (`app/static/img/bg.jpg`)
- **Datenschutz:** Meldungen werden automatisch gelöscht, sobald ihr Bis-Datum mehr als
  `RETENTION_DAYS` (Standard 30) Tage zurückliegt. Keine externen Ressourcen (Schriften lokal).

## Start

```bash
cp .env.example .env        # ADMIN_PASSWORD und SECRET_KEY setzen!
docker compose up -d --build
```

- Mitarbeiter-Seite: http://localhost:8000/
- Admin-Bereich:     http://localhost:8000/admin

Die Datenbank liegt im Docker-Volume `krankmeldung-data` (`/data/krankmeldung.db`).

## Betrieb

- **HTTPS:** Das Tool spricht nur HTTP. Bitte hinter einen Reverse Proxy (Caddy, Traefik, nginx)
  mit TLS stellen und dann `SECURE_COOKIES=true` setzen.
- **Proxy-IP:** `FORWARDED_ALLOW_IPS` auf die IP bzw. das Netz des Proxys setzen (z. B. `172.16.0.0/12`,
  wenn der Proxy im selben Docker-Netz läuft). Nur dann sieht das Rate-Limit die echte IP der
  Mitarbeiter – sonst teilen sich alle die Proxy-IP. **Nie `*` setzen**, solange Port 8000 direkt
  erreichbar ist, sonst kann jeder seine IP fälschen und das Rate-Limit umgehen.
- **nginx:** `proxy_set_header Host $host;` setzen – der CSRF-Schutz vergleicht die Herkunft
  (`Origin`) eines Formulars mit dem Host (alternativ `PUBLIC_URL` setzen).
- **Rate-Limit:** 10 falsche Codes bzw. 5 falsche Admin-Passwörter pro IP → 15 Minuten gesperrt.
- **E-Mail:** Optional. Sind `SMTP_HOST` und `SMTP_TO` gesetzt, wird bei jeder neuen Meldung eine
  Mail mit Name und Zeitraum verschickt (ohne Art der AU und ohne Bemerkung).
- **Backup:** `docker compose exec krankmeldung python -c "import sqlite3; sqlite3.connect('/data/krankmeldung.db').backup(sqlite3.connect('/data/backup.db'))"`

## Mitarbeiter per CSV importieren / exportieren

Im Admin-Bereich unter „Mitarbeiter“:

- **Export** erzeugt `mitarbeiter-JJJJ-MM-TT.csv` (Semikolon, UTF-8 mit BOM, öffnet direkt in Excel).
- **Import** erwartet dasselbe Format:

  ```
  Name;Code;Aktiv
  Max Mustermann;max2026;ja
  Erika Muster;erika77;nein
  ```

  Kopfzeile und Spalte `Aktiv` sind optional, Komma als Trenner und Excel-Dateien in
  Windows-Kodierung werden ebenfalls erkannt. Abgleich über den Code (Groß-/Kleinschreibung egal):
  bekannter Code → Name/Status werden aktualisiert, neuer Code → Mitarbeiter wird angelegt.
  Es wird **nichts gelöscht**. Enthält die Datei einen Fehler (zu kurzer Code, doppelter Code, …),
  wird der gesamte Import abgebrochen und die fehlerhaften Zeilen werden angezeigt.

  Hinweis: Ein Code lässt sich per Import nicht ändern – ein geänderter Code gilt als neuer Mitarbeiter.

## Regeln

| Feld | Regel |
|---|---|
| Code | 6–64 Zeichen, Buchstaben ohne Umlaute/Ziffern/Sonderzeichen, keine Leerzeichen, eindeutig (Groß-/Kleinschreibung egal), nur aktive Mitarbeiter |
| Von | Default heute, max. 14 Tage zurück, max. 30 Tage voraus |
| Bis | Pflicht (Default heute), nicht vor „Von“ |
| Art | Selbst krankgemeldet / Ärztliche AU Papier / eAU |
| Bemerkung | optional, max. 1000 Zeichen |

Wird ein Mitarbeiter gelöscht, werden auch seine Meldungen gelöscht. Deaktivieren sperrt nur den Code.

## Sicherheit

- Rate-Limit pro IP für Codes und Admin-Passwort
- Admin-Session als signiertes Cookie (`HttpOnly`, `SameSite=strict`, 8 h). Wird `ADMIN_PASSWORD`
  geändert, sind alle bestehenden Sessions sofort ungültig.
- CSRF: zusätzlich zu `SameSite` werden POSTs mit fremder `Origin`/`Referer` abgelehnt
- Strikte Content-Security-Policy (kein Inline-JavaScript), `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, `Cache-Control: no-store` für alle Seiten (Gesundheitsdaten
  landen nicht im Browser-Cache)
- Requests > 1 MB werden abgewiesen, bevor sie eingelesen werden
- CSV-Export schützt vor Formel-Injection in Excel (`=`, `+`, `-`, `@` werden mit `'` maskiert)
- Container läuft als unprivilegierter Benutzer

## Tests & CI

```bash
pip install -r requirements-dev.txt
pytest
```

Der GitHub-Workflow (`.github/workflows/ci.yml`) führt bei jedem Push/PR die Tests aus, prüft die
Abhängigkeiten mit `pip-audit` auf bekannte Schwachstellen und baut das Docker-Image inkl. Smoke-Test.

## Lokale Entwicklung

```bash
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
ADMIN_PASSWORD=test DB_PATH=./dev.db uvicorn app.main:app --reload
```
