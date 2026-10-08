# Krankmeldung – Übergangslösung

Kleines Web-Tool, über das sich Mitarbeiter mit einem persönlichen Code krankmelden.
Ein Admin-Bereich zeigt neue Meldungen an und verwaltet die Mitarbeiter-Codes.
Das Tool dient nur der Ersterfassung – keine Auswertung, keine Historie.

- **Stack:** Python 3.13 · FastAPI · Jinja2 · SQLite (ein Container, keine externe DB)
- **Design:** angelehnt an hof-dinkelberg.de; Hintergrundbild „Ähren“ von
  [aszak](https://pixabay.com/users/aszak-22997580/) auf
  [Pixabay](https://pixabay.com/photos/ears-of-corn-wheat-harvest-ripe-7325780/) (`app/static/img/bg.jpg`).
  Credits stehen unten rechts auf jeder Seite (`app/templates/_credits.html`).
- **Datenschutz:** Meldungen werden automatisch gelöscht, sobald ihr Bis-Datum mehr als
  `RETENTION_DAYS` (Standard 30) Tage zurückliegt – auch ungelesene. Schriften, Bilder und Skripte
  liegen lokal, es werden keine externen Dienste geladen.

## Funktionen

**Mitarbeiter** (`/`)

1. Persönlichen Code eingeben → Begrüßung mit Namen („Nicht du?“ führt zurück)
2. Übersicht der eigenen **aktiven und zukünftigen Krankmeldungen**
   (aktiv = heute liegt im Zeitraum; vergangene werden nicht angezeigt)
3. Formular: Von (Default heute), Bis (Default heute), Art der Krankmeldung, optionale Bemerkung
4. Überschneidet sich der Zeitraum mit einer eigenen Meldung, erscheint sofort ein Hinweis.
   Absenden ist trotzdem möglich (z. B. ärztliche AU nach Selbstmeldung oder Verlängerung).
   Ohne JavaScript fragt der Server einmal nach („Trotzdem absenden“).
5. Nach dem Absenden: Bestätigung mit Animation

**Admin** (`/admin`, ein gemeinsames Passwort)

- Neue (ungelesene) Meldungen mit Zeitraum, Anzahl Kalendertage, Art, Bemerkung und Eingang
- Meldungen einzeln oder alle als gelesen markieren, wieder als ungelesen markieren
- Meldungen einzeln **löschen** (z. B. falsch abgegebene oder doppelte Meldungen)
- Gelesene Meldungen eingeklappt einsehbar
- Mitarbeiter anlegen, Name/Code ändern, deaktivieren (sperrt den Code) oder löschen
  (löscht auch alle Meldungen des Mitarbeiters)
- Mitarbeiterliste als CSV importieren/exportieren (siehe unten)
- Die Seite lädt sich jede Minute neu, solange nichts eingetippt wird

## Start

Das Image liegt öffentlich in der GitHub Container Registry:
`ghcr.io/itsmagictv/hof-krankheitstool`. Für den Betrieb werden nur `docker-compose.yml` und
eine `.env` benötigt – kein Checkout des Codes, kein Build.

```bash
cp .env.example .env        # ADMIN_PASSWORD und SECRET_KEY setzen!
docker compose up -d
```

Aktualisieren auf das neueste Image:

```bash
docker compose pull && docker compose up -d
```

Die Daten bleiben dabei erhalten (Volume). Statt `latest` kann in `docker-compose.yml` auch ein
fester Commit-Tag (z. B. `:ca90e4e`) eingetragen werden, um eine Version festzuhalten.

- Mitarbeiter-Seite: http://localhost:8000/
- Admin-Bereich:     http://localhost:8000/admin

Die Datenbank liegt im Docker-Volume `krankmeldung-data` (`/data/krankmeldung.db`).

## Konfiguration (`.env`)

| Variable | Pflicht | Bedeutung |
|---|---|---|
| `ADMIN_PASSWORD` | ja | Passwort für `/admin`. Ohne startet der Container nicht. Ändern beendet alle Admin-Sessions. |
| `SECRET_KEY` | empfohlen | Schlüssel für Session-Cookies (`openssl rand -hex 32`). Ohne gehen Sessions bei jedem Neustart verloren. |
| `COMPANY_NAME` | | Name im Seitentitel (Standard: Hof Dinkelberg) |
| `PUBLIC_URL` | | Öffentliche Adresse, z. B. `https://krank.example.de` – für den Link in der E-Mail und den CSRF-Schutz |
| `SECURE_COOKIES` | | `true`, sobald das Tool nur per HTTPS erreichbar ist (setzt auch HSTS) |
| `RETENTION_DAYS` | | Tage nach dem Bis-Datum bis zur Löschung (Standard 30) |
| `FORWARDED_ALLOW_IPS` | | IP/Netz des Reverse Proxys (Standard `127.0.0.1`), siehe Betrieb |
| `SECURITY_LOG` | | Sicherheitsereignisse loggen (Standard `true`), siehe Logging |
| `SMTP_*` | | Optionale E-Mail-Benachrichtigung, siehe `.env.example` |

## Betrieb

- **HTTPS:** Das Tool spricht nur HTTP. Bitte hinter einen Reverse Proxy (Caddy, Traefik, nginx)
  mit TLS stellen und dann `SECURE_COOKIES=true` setzen.
- **Proxy-IP:** `FORWARDED_ALLOW_IPS` auf die IP bzw. das Netz des Proxys setzen (z. B. `172.16.0.0/12`,
  wenn der Proxy im selben Docker-Netz läuft). Nur dann sieht das Rate-Limit die echte IP der
  Mitarbeiter – sonst teilen sich alle die Proxy-IP. **Nie `*` setzen**, solange Port 8000 direkt
  erreichbar ist, sonst kann jeder seine IP fälschen und das Rate-Limit umgehen.
- **nginx:** `proxy_set_header Host $host;` setzen – der CSRF-Schutz vergleicht die Herkunft
  (`Origin`) eines Formulars mit dem Host (alternativ `PUBLIC_URL` setzen).
- **E-Mail:** Sind `SMTP_HOST` und `SMTP_TO` gesetzt, wird bei jeder neuen Meldung eine Mail mit
  Name und Zeitraum verschickt – ohne Art der AU und ohne Bemerkung. Fehler beim Versand stehen im Log.
- **Logging:** Das Container-Log enthält bewusst keine personenbezogenen Daten, denn es unterliegt
  nicht der Löschfrist. Das Zugriffslog von uvicorn ist abgeschaltet (IP + Zeitpunkt einer
  Krankmeldung wären personenbezogen). Neue Meldungen erscheinen nur als „Neue Krankmeldung
  eingegangen“. Mit `SECURITY_LOG=true` (Standard) werden zusätzlich Sicherheitsereignisse mit
  gekürzter IP (`10.0.3.xxx`) protokolliert:

  ```
  SICHERHEIT Admin-Login erfolgreich (IP 10.0.3.xxx)
  SICHERHEIT Admin-Login fehlgeschlagen (IP 10.0.3.xxx)
  SICHERHEIT Zu viele falsche Admin-Passwörter – IP für 15 Minuten gesperrt (IP 10.0.3.xxx)
  SICHERHEIT Zu viele falsche Mitarbeiter-Codes – IP für 15 Minuten gesperrt (IP 10.0.3.xxx)
  ```

  Einzelne falsche Codes (Tippfehler) werden nicht geloggt. Die Logs sind in `docker-compose.yml`
  auf 2 × 5 MB begrenzt (`docker compose logs krankmeldung`). Hinweis: Ein vorgeschalteter Reverse
  Proxy schreibt meist ein eigenes Zugriffslog – dort ebenfalls abschalten oder IPs kürzen.
- **Backup:**

  ```bash
  docker compose exec krankmeldung python -c "import sqlite3; sqlite3.connect('/data/krankmeldung.db').backup(sqlite3.connect('/data/backup.db'))"
  docker compose cp krankmeldung:/data/backup.db ./krankmeldung-backup.db
  ```

  Hinweis: Das Backup enthält Gesundheitsdaten – entsprechend sicher ablegen und ebenfalls nach
  spätestens 30 Tagen löschen.

## Regeln

| Feld | Regel |
|---|---|
| Code | 6–64 Zeichen; erlaubt sind Buchstaben (ohne Umlaute), Ziffern und Sonderzeichen, keine Leerzeichen. Eindeutig, Groß-/Kleinschreibung egal. Nur aktive Mitarbeiter können sich melden. |
| Von | Default heute, max. 14 Tage zurück, max. 30 Tage voraus |
| Bis | Pflicht (Default heute), nicht vor „Von“, Zeitraum max. 1 Jahr |
| Art | Selbst krankgemeldet (ohne AU) / Ärztliche AU – Papier / Ärztliche AU – digital (eAU) |
| Bemerkung | optional, max. 1000 Zeichen |

## Mitarbeiter per CSV importieren / exportieren

Im Admin-Bereich unter „Mitarbeiter“:

- **Export** erzeugt `mitarbeiter-JJJJ-MM-TT.csv` (Semikolon, UTF-8 mit BOM, öffnet direkt in Excel).
- **Import** erwartet dasselbe Format:

  ```
  Name;Code;Aktiv
  Max Mustermann;max2026;ja
  Erika Muster;erika77;nein
  ```

  Kopfzeile und Spalte `Aktiv` sind optional (ja/nein, 1/0, x …). Komma als Trenner und
  Excel-Dateien in Windows-Kodierung werden ebenfalls erkannt. Abgleich über den Code
  (Groß-/Kleinschreibung egal): bekannter Code → Name/Status werden aktualisiert, neuer Code →
  Mitarbeiter wird angelegt. Es wird **nichts gelöscht**. Enthält die Datei einen Fehler
  (zu kurzer Code, doppelter Code, …), wird der gesamte Import abgebrochen und die fehlerhaften
  Zeilen werden angezeigt. Max. Dateigröße 1 MB.

  Hinweis: Ein Code lässt sich per Import nicht ändern – ein geänderter Code gilt als neuer
  Mitarbeiter. Codes daher direkt in der Tabelle ändern.

## Sicherheit

- Rate-Limit pro IP: 10 falsche Codes bzw. 5 falsche Admin-Passwörter → 15 Minuten gesperrt
- Admin-Session als signiertes Cookie (`HttpOnly`, `SameSite=strict`, 8 h). Wird `ADMIN_PASSWORD`
  geändert, sind alle bestehenden Sessions sofort ungültig.
- CSRF: zusätzlich zu `SameSite` werden POSTs mit fremder `Origin`/`Referer` abgelehnt
- Strikte Content-Security-Policy (kein Inline-JavaScript), `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, HSTS bei `SECURE_COOKIES=true`
- `Cache-Control: no-store` für alle Seiten – Gesundheitsdaten landen nicht im Browser-Cache
- Requests > 1 MB werden abgewiesen, bevor sie eingelesen werden
- CSV-Export schützt vor Formel-Injection in Excel (`=`, `+`, `-`, `@` werden mit `'` maskiert)
- Ein Mitarbeiter sieht nur seine eigenen Meldungen – allerdings jeder, der seinen Code kennt
- Container läuft als unprivilegierter Benutzer

## Projektstruktur

```
app/
  main.py          Routen, Validierung, Middleware (Security-Header, CSRF, Größenlimit)
  db.py            SQLite-Schema und Datenbankzugriff, Löschfrist
  templates/       Jinja2-Templates (Mitarbeiter-Seiten, Admin)
  static/          CSS, JavaScript, Schriften, Bilder
tests/             pytest-Tests
.github/workflows/ CI (Tests, pip-audit, Docker-Build mit Smoke-Test, Veröffentlichung)
docker-compose.yml      Betrieb: fertiges Image aus ghcr.io
docker-compose.dev.yml  Entwicklung: Image lokal bauen
```

## Tests & CI

```bash
pip install -r requirements-dev.txt
pytest
```

Der GitHub-Workflow (`.github/workflows/ci.yml`) läuft bei jedem Push auf `main`, bei Pull Requests
und manuell. Er führt die Tests aus, prüft die Abhängigkeiten mit `pip-audit` auf bekannte
Schwachstellen und baut das Docker-Image inkl. Smoke-Test (Health-Check, Security-Header,
kein root, Start ohne Passwort wird verweigert). Auf `main` wird das getestete Image anschließend
nach `ghcr.io` veröffentlicht (siehe oben).

## Lokale Entwicklung

Ohne Docker (schnellster Weg, lädt bei Codeänderungen automatisch neu):

```bash
python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
ADMIN_PASSWORD=test DB_PATH=./dev.db uvicorn app.main:app --reload
```

Mit Docker aus dem lokalen Code bauen – `docker-compose.dev.yml` ergänzt die Standard-Konfiguration
um `build: .` und verwendet den lokalen Image-Namen `hof-krankheitstool:dev`, damit ein
Entwicklungs-Build nie das echte `latest` aus der Registry überschreibt:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Die Datei heißt bewusst nicht `docker-compose.override.yml` – die würde Docker automatisch laden,
auch auf dem Server, und dort wieder bauen statt das fertige Image zu ziehen.

## Neues Image veröffentlichen

Automatisch: Bei jedem Push auf `main` baut der GitHub-Workflow das Image, testet es und lädt
**genau dieses getestete Image** nach `ghcr.io` hoch – als `:latest` und mit Commit-Tag (z. B.
`:ca90e4e`). Voraussetzung: Tests, `pip-audit` und Smoke-Test sind grün. Pull Requests
veröffentlichen nie. Manuell neu veröffentlichen: Actions → CI → „Run workflow“ auf `main`.

Danach auf dem Server: `docker compose pull && docker compose up -d`.

Manuell (nur als Notlösung, z. B. wenn GitHub Actions nicht verfügbar ist) – aus einem sauberen,
gepushten Stand von `main`, Login mit
`gh auth token | docker login ghcr.io -u <github-user> --password-stdin` (Token mit `write:packages`):

```bash
IMG="ghcr.io/itsmagictv/hof-krankheitstool"
SHA="$(git rev-parse --short HEAD)"
docker build \
  --label "org.opencontainers.image.source=https://github.com/itsMagictv/hof-Krankheitstool" \
  --label "org.opencontainers.image.revision=$(git rev-parse HEAD)" \
  -t "${IMG}:${SHA}" -t "${IMG}:latest" .
docker push "${IMG}:${SHA}" && docker push "${IMG}:latest"
```

Wichtig: `"${IMG}:latest"` mit geschweiften Klammern schreiben – in zsh wird `$IMG:latest`
sonst als Modifikator (`:l`, `:a` …) gelesen und der Image-Name verstümmelt.
