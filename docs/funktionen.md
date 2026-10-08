# Funktionen

[← zurück zur README](../README.md)

## Mitarbeiter (`/`)

1. Persönlichen Code eingeben → Begrüßung mit Namen („Nicht du?“ führt zurück)
2. Übersicht der eigenen **aktiven und zukünftigen Krankmeldungen**
   (aktiv = heute liegt im Zeitraum; vergangene werden nicht angezeigt)
3. Formular: Von (Default heute), Bis (Default heute), Art der Krankmeldung, optionale Bemerkung
4. Überschneidet sich der Zeitraum mit einer eigenen Meldung, erscheint sofort ein Hinweis.
   Absenden ist trotzdem möglich (z. B. ärztliche AU nach Selbstmeldung oder Verlängerung).
   Ohne JavaScript fragt der Server einmal nach („Trotzdem absenden“).
5. Nach dem Absenden: Bestätigung mit Animation

## Admin (`/admin`)

Anmeldung mit einem gemeinsamen Passwort (`ADMIN_PASSWORD`).

- Neue (ungelesene) Meldungen mit Zeitraum, Anzahl Kalendertage, Art, Bemerkung und Eingang
- Meldungen einzeln oder alle als gelesen markieren, wieder als ungelesen markieren
- Meldungen einzeln **löschen** (z. B. falsch abgegebene oder doppelte Meldungen)
- Gelesene Meldungen eingeklappt einsehbar
- Mitarbeiter anlegen, Name/Code ändern, deaktivieren (sperrt den Code) oder löschen
  (löscht auch alle Meldungen des Mitarbeiters)
- Mitarbeiterliste als CSV importieren/exportieren (siehe unten)
- Die Seite lädt sich jede Minute neu, solange nichts eingetippt wird

Meldungen werden automatisch gelöscht, sobald ihr Bis-Datum mehr als `RETENTION_DAYS`
(Standard 30) Tage zurückliegt – auch ungelesene.

## Eingaberegeln

| Feld | Regel |
|---|---|
| Code | 6–64 Zeichen; erlaubt sind Buchstaben (ohne Umlaute), Ziffern und Sonderzeichen, keine Leerzeichen. Eindeutig, Groß-/Kleinschreibung egal. Nur aktive Mitarbeiter können sich melden. |
| Von | Default heute, max. 14 Tage zurück, max. 30 Tage voraus |
| Bis | Pflicht (Default heute), nicht vor „Von“, Zeitraum max. 1 Jahr |
| Art | Selbst krankgemeldet (ohne AU) / Ärztliche AU – Papier / Ärztliche AU – digital (eAU) |
| Bemerkung | optional, max. 1000 Zeichen |

## Mitarbeiter per CSV importieren / exportieren

Im Admin-Bereich unter „Mitarbeiter“.

**Export** erzeugt `mitarbeiter-JJJJ-MM-TT.csv` (Semikolon, UTF-8 mit BOM, öffnet direkt in Excel).

**Import** erwartet dasselbe Format:

```
Name;Code;Aktiv
Max Mustermann;max2026;ja
Erika Muster;erika77;nein
```

- Kopfzeile und Spalte `Aktiv` sind optional (ja/nein, 1/0, x …).
- Komma als Trenner und Excel-Dateien in Windows-Kodierung werden ebenfalls erkannt.
- Abgleich über den Code (Groß-/Kleinschreibung egal): bekannter Code → Name/Status werden
  aktualisiert, neuer Code → Mitarbeiter wird angelegt. Es wird **nichts gelöscht**.
- Enthält die Datei einen Fehler (zu kurzer Code, doppelter Code, …), wird der gesamte Import
  abgebrochen und die fehlerhaften Zeilen werden angezeigt.
- Max. Dateigröße 1 MB.

Ein Code lässt sich per Import nicht ändern – ein geänderter Code gilt als neuer Mitarbeiter.
Codes daher direkt in der Tabelle ändern.
