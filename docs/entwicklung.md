# Entwicklung

[← zurück zur README](../README.md)

## Projektstruktur

```
app/
  main.py               Routen, Validierung, Middleware (Security-Header, CSRF, Größenlimit)
  db.py                 SQLite-Schema und Datenbankzugriff, Löschfrist
  templates/            Jinja2-Templates (Mitarbeiter-Seiten, Admin)
    _credits.html       Credits unten rechts auf jeder Seite (Foto, Copyright)
  static/               CSS, JavaScript, Schriften, Bilder
tests/                  pytest-Tests
docs/                   Dokumentation
.github/workflows/      CI: Tests, pip-audit, Docker-Build mit Smoke-Test, Veröffentlichung
docker-compose.yml      Betrieb: fertiges Image aus ghcr.io
docker-compose.dev.yml  Entwicklung: Image lokal bauen
```

## Lokal starten

Voraussetzung: Python 3.13 (wie im Docker-Image).

Ohne Docker (schnellster Weg, lädt bei Codeänderungen automatisch neu):

```bash
python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
ADMIN_PASSWORD=test DB_PATH=./dev.db uvicorn app.main:app --reload
```

Mit Docker aus dem lokalen Code:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

`docker-compose.dev.yml` ergänzt die Standard-Konfiguration um `build: .` und verwendet den
lokalen Image-Namen `hof-krankheitstool:dev`, damit ein Entwicklungs-Build nie das echte
`latest` aus der Registry überschreibt. Die Datei heißt bewusst nicht
`docker-compose.override.yml` – die würde Docker automatisch laden, auch auf dem Server, und dort
wieder bauen statt das fertige Image zu ziehen.

## Tests & CI

```bash
pytest
```

Der GitHub-Workflow (`.github/workflows/ci.yml`) läuft bei jedem Push auf `main`, bei Pull
Requests und manuell:

1. Tests und Prüfung der Abhängigkeiten mit `pip-audit`
2. Docker-Image bauen und Smoke-Test (Health-Check, Security-Header, kein root,
   Start ohne Passwort wird verweigert)
3. Nur auf `main`: Veröffentlichung des getesteten Images (siehe unten)

## Neues Image veröffentlichen

**Automatisch:** Bei jedem Push auf `main` lädt der Workflow **genau das getestete Image** nach
`ghcr.io` hoch – als `:latest` und mit Commit-Tag (z. B. `:ca90e4e`). Voraussetzung: alle
vorherigen Schritte sind grün. Pull Requests veröffentlichen nie. Erneut veröffentlichen:
Actions → CI → „Run workflow“ auf `main`.

Danach auf dem Server: `docker compose pull && docker compose up -d`.

**Manuell** (nur als Notlösung, z. B. wenn GitHub Actions nicht verfügbar ist) – aus einem
sauberen, gepushten Stand von `main`, Login mit
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

`"${IMG}:latest"` unbedingt mit geschweiften Klammern schreiben – in zsh wird `$IMG:latest`
sonst als Modifikator (`:l`, `:a` …) gelesen und der Image-Name verstümmelt.
