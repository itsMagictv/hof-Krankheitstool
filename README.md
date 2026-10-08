# Krankmeldung – Übergangslösung

Kleines Web-Tool, über das sich Mitarbeiter mit einem persönlichen Code krankmelden.
Ein Admin-Bereich zeigt neue Meldungen an und verwaltet die Mitarbeiter.
Gedacht nur für die Ersterfassung – keine Auswertung, keine Historie.

- Krankmeldung per persönlichem Code: Zeitraum, Art (selbst / AU Papier / eAU), Bemerkung
- Admin: neue Meldungen sichten, als gelesen markieren, löschen; Mitarbeiter verwalten, CSV-Import/-Export
- Datenschutz: Meldungen werden 30 Tage nach ihrem Ende automatisch gelöscht
- Ein Container mit SQLite – Python · FastAPI · Jinja2

## Schnellstart

```bash
cp .env.example .env        # ADMIN_PASSWORD und SECRET_KEY setzen
docker compose up -d
```

- Mitarbeiter: http://localhost:8000/
- Admin: http://localhost:8000/admin

Aktualisieren: `docker compose pull && docker compose up -d`

Für den Betrieb hinter einem Reverse Proxy unbedingt [Betrieb → Reverse Proxy & HTTPS](docs/betrieb.md#reverse-proxy--https) beachten.

## Dokumentation

|                                                |                                                                     |
| ---------------------------------------------- | ------------------------------------------------------------------- |
| [Funktionen](docs/funktionen.md)               | Ablauf für Mitarbeiter und Admin, Eingaberegeln, CSV-Format         |
| [Betrieb](docs/betrieb.md)                     | Installation, Konfiguration, Reverse Proxy, E-Mail, Logging, Backup |
| [Sicherheit & Datenschutz](docs/sicherheit.md) | Schutzmaßnahmen und Umgang mit Gesundheitsdaten                     |
| [Entwicklung](docs/entwicklung.md)             | Lokal starten, Tests & CI, neues Image veröffentlichen              |

## Credits

Hintergrundbild „Ähren“ von [aszak](https://pixabay.com/users/aszak-22997580/) auf
[Pixabay](https://pixabay.com/photos/ears-of-corn-wheat-harvest-ripe-7325780/).
© 2026 Hof Dinkelberg GmbH
