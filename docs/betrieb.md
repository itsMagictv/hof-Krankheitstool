# Betrieb

[← zurück zur README](../README.md)

## Installation & Update

Das Image liegt öffentlich in der GitHub Container Registry:
`ghcr.io/itsmagictv/hof-krankheitstool`. Benötigt werden nur `docker-compose.yml` und eine
`.env` – kein Checkout des Codes, kein Build.

```bash
cp .env.example .env        # ADMIN_PASSWORD und SECRET_KEY setzen!
docker compose up -d
```

Aktualisieren auf das neueste Image (die Daten im Volume bleiben erhalten):

```bash
docker compose pull && docker compose up -d
```

Statt `latest` kann in `docker-compose.yml` auch ein fester Commit-Tag (z. B. `:ca90e4e`)
eingetragen werden, um eine Version festzuhalten.

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
| `FORWARDED_ALLOW_IPS` | | IP/Netz des Reverse Proxys (Standard `127.0.0.1`), siehe unten |
| `SECURITY_LOG` | | Sicherheitsereignisse loggen (Standard `true`), siehe [Logging](#logging) |
| `SMTP_*` | | Optionale E-Mail-Benachrichtigung, siehe `.env.example` |

## Reverse Proxy & HTTPS

- **HTTPS:** Das Tool spricht nur HTTP. Bitte hinter einen Reverse Proxy (Caddy, Traefik, nginx)
  mit TLS stellen und dann `SECURE_COOKIES=true` setzen.
- **Proxy-IP:** `FORWARDED_ALLOW_IPS` auf die IP bzw. das Netz des Proxys setzen (z. B.
  `172.16.0.0/12`, wenn der Proxy im selben Docker-Netz läuft). Nur dann sieht das Rate-Limit die
  echte IP der Mitarbeiter – sonst teilen sich alle die Proxy-IP. **Nie `*` setzen**, solange
  Port 8000 direkt erreichbar ist, sonst kann jeder seine IP fälschen und das Rate-Limit umgehen.
- **nginx:** `proxy_set_header Host $host;` setzen – der CSRF-Schutz vergleicht die Herkunft
  (`Origin`) eines Formulars mit dem Host (alternativ `PUBLIC_URL` setzen).
- **Proxy-Log:** Der Proxy schreibt meist ein eigenes Zugriffslog mit IP und Zeitpunkt jeder
  Krankmeldung – dort abschalten oder IPs kürzen (siehe [Logging](#logging)).

## E-Mail-Benachrichtigung

Sind `SMTP_HOST` und `SMTP_TO` gesetzt, wird bei jeder neuen Meldung eine Mail mit Name und
Zeitraum verschickt – ohne Art der AU und ohne Bemerkung. Fehler beim Versand stehen im Log.
Alle `SMTP_*`-Variablen sind in `.env.example` beschrieben.

## Logging

Das Container-Log enthält bewusst keine personenbezogenen Daten, denn es unterliegt nicht der
Löschfrist. Das Zugriffslog von uvicorn ist abgeschaltet (IP + Zeitpunkt einer Krankmeldung wären
personenbezogen). Neue Meldungen erscheinen nur als „Neue Krankmeldung eingegangen“.

Mit `SECURITY_LOG=true` (Standard) werden zusätzlich Sicherheitsereignisse mit gekürzter IP
protokolliert – nie Codes, Passwörter oder Namen:

```
SICHERHEIT Admin-Login erfolgreich (IP 10.0.3.xxx)
SICHERHEIT Admin-Login fehlgeschlagen (IP 10.0.3.xxx)
SICHERHEIT Zu viele falsche Admin-Passwörter – IP für 15 Minuten gesperrt (IP 10.0.3.xxx)
SICHERHEIT Zu viele falsche Mitarbeiter-Codes – IP für 15 Minuten gesperrt (IP 10.0.3.xxx)
```

Einzelne falsche Codes (Tippfehler) werden nicht geloggt. Die Logs sind in `docker-compose.yml`
auf 2 × 5 MB begrenzt. Anzeigen mit `docker compose logs krankmeldung`.

## Backup

```bash
docker compose exec krankmeldung python -c "import sqlite3; sqlite3.connect('/data/krankmeldung.db').backup(sqlite3.connect('/data/backup.db'))"
docker compose cp krankmeldung:/data/backup.db ./krankmeldung-backup.db
```

Das Backup enthält Gesundheitsdaten – entsprechend sicher ablegen und ebenfalls nach spätestens
30 Tagen löschen.
