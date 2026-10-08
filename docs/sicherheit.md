# Sicherheit & Datenschutz

[← zurück zur README](../README.md)

## Datenschutz

- Meldungen werden automatisch gelöscht, sobald ihr Bis-Datum mehr als `RETENTION_DAYS`
  (Standard 30) Tage zurückliegt – auch ungelesene.
- Die E-Mail-Benachrichtigung enthält nur Name und Zeitraum, nicht die Art der AU und keine Bemerkung.
- Logs enthalten keine personenbezogenen Daten, Sicherheitsereignisse nur mit gekürzter IP
  (siehe [Betrieb → Logging](betrieb.md#logging)).
- `Cache-Control: no-store` für alle Seiten – Gesundheitsdaten landen nicht im Browser-Cache.
- Schriften, Bilder und Skripte liegen lokal, es werden keine externen Dienste geladen.
- Ein Mitarbeiter sieht nur seine eigenen Meldungen – allerdings jeder, der seinen Code kennt.

## Schutzmaßnahmen

- Rate-Limit pro IP: 10 falsche Codes bzw. 5 falsche Admin-Passwörter → 15 Minuten gesperrt
- Admin-Session als signiertes Cookie (`HttpOnly`, `SameSite=strict`, 8 h). Der Token darin ist
  per PBKDF2 vom Passwort abgeleitet: Wird `ADMIN_PASSWORD` geändert, sind alle bestehenden
  Sessions sofort ungültig.
- CSRF: zusätzlich zu `SameSite` werden POSTs mit fremder `Origin`/`Referer` abgelehnt
- Strikte Content-Security-Policy (kein Inline-JavaScript), `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, HSTS bei `SECURE_COOKIES=true`
- Requests > 1 MB werden abgewiesen, bevor sie eingelesen werden
- CSV-Export schützt vor Formel-Injection in Excel (`=`, `+`, `-`, `@` werden mit `'` maskiert)
- Container läuft als unprivilegierter Benutzer
- Abhängigkeiten werden in der CI mit `pip-audit` auf bekannte Schwachstellen geprüft

Für einen sicheren Betrieb hinter einem Reverse Proxy siehe
[Betrieb → Reverse Proxy & HTTPS](betrieb.md#reverse-proxy--https).
