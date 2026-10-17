# Shopping-Referenzdaten betreiben

Status: #785 Slice E — Operator-Flow für optionale öffentliche Einkauf-Referenzpakete.

## Einstieg

Die Paketverwaltung ist ausschließlich in der getrennten Superadmin-PWA verfügbar:

`/superadmin/?section=reference-data`

Sie ist kein Familienfeature, keine Root-Navigation der normalen App und besitzt keinen eigenen Auth-Stack. Sie verwendet die bestehende Superadmin-Sitzung und deren Fresh-Reauthentication-/Rate-Limit-Vertrag.

## Grundsatz

Shopping funktioniert mit **0 installierten Paketen** vollständig weiter. Referenzpakete sind optionale Suggestions-/Lookup-Daten und niemals Wahrheit für `ShoppingItem`, Household-Memory, gelernte Einkaufsreihenfolge, abgeschlossene Sessions oder Finanzdaten.

Die Paketverwaltung akzeptiert ausschließlich:

- serverseitig registrierte interne Source-Adapter; oder
- einen expliziten, autorisierten ZIP-Upload im Operator-Flow.

Es gibt **keinen freien URL-Import**. Eine `source_url` im Manifest ist Provenienz-Metadatum und wird von diesem Flow nicht abgerufen.

## Geführter Ablauf

### 1. Paket

Der Operator wählt ein ZIP-Paket lokal aus. Das Backend erzwingt die Slice-B-Limits für Paketgröße, Datei- und Entry-Anzahl, unkomprimierte Größe, Kompressionsverhältnis, Pfade, Dateitypen, Symlinks und Verschlüsselung.

Strukturell unsichere Archive werden verworfen, bevor ein Registry-Eintrag entsteht.

### 2. Rechte und Provenienz

Vor einer Runtime-Aktivierung sind mindestens sichtbar:

- `dataset_id`, Version und Typ;
- Lizenz;
- Attribution;
- Redistribution-Entscheidung (`adopt`, `adapt`, `defer`, `deny`);
- Quelle und Source-Revision;
- Locale/Land/Region;
- Dependencies.

`defer` und `deny` dürfen validiert/previewt werden, sind aber nicht runtime-fähig. Der Operator kann diese Sperre nicht über die UI umgehen.

### 3. Validation und Preview

Der bestehende Staging-/Validation-Service prüft Schema, Privacy, Rechte, Checksums, Record-Counts, Dependencies und die typisierten Runtime-Records. Die Preview zeigt technische Counts, Checksum und Blocker.

Die UI erzeugt keinen zweiten Importpfad. Sie ruft direkt den kanonischen `stage_reference_package(..., source_adapter="operator_upload")`-Vertrag auf.

### 4. Aktivierung

Aktivieren, Deaktivieren und Rollback sind explizite Operator-Aktionen. Sie verwenden:

- Fresh-Reauthentication/Rate-Limit aus der Superadmin-Sicherheitsarchitektur;
- einen kurzen semantischen Lease pro `dataset_id`;
- `expected_revision` als Compare-and-Swap gegen parallele Operator-/Worker-Aktionen;
- die atomaren Slice-C-Services;
- append-only technische Activation-History.

Eine bisher aktive Version bleibt gültig, bis die neue Aktivierung atomar committed ist.

## States

Der Operator-Flow unterscheidet explizit:

- `staged`
- `validating`
- `preview`
- `activating`
- `active`
- `failed`
- `stale`
- `disabled`
- `rollback`

Ein fehlgeschlagenes Update deaktiviert nicht automatisch den letzten gültigen aktiven Stand.

## Rollback und Disable

`Disable` entfernt keine Registry-, Historien-, Shopping- oder Finance-Daten. Ein Rollback nutzt die technische Activation-History und kann nur auf eine vorhandene, weiterhin validierte, rights-safe Vorgängerversion zurückgehen.

Pakete werden im Operator-Flow nicht hart gelöscht. Ein späterer Uninstall-/Retention-Slice muss historische Referenzen und Shopping-Snapshots ausdrücklich berücksichtigen.

## API

Superadmin-only:

- `GET /api/superadmin/reference-datasets/` — bounded Registry-Liste, optional nach Typ/State/Dataset-ID filterbar;
- `GET /api/superadmin/reference-datasets/<uuid>/` — Detail, Manifest, andere aktive Version und bounded technische History;
- `POST /api/superadmin/reference-datasets/validate/` — Multipart-ZIP, fester Adapter `operator_upload`;
- `POST /api/superadmin/reference-datasets/<uuid>/activate/`;
- `POST /api/superadmin/reference-datasets/<uuid>/disable/`;
- `POST /api/superadmin/reference-datasets/<uuid>/rollback/`.

Runtime-Mutationen erwarten `expected_revision`.

## Typische Fehler

| Code | Bedeutung / Operator-Aktion |
| --- | --- |
| `malformed_archive` | ZIP ist strukturell ungültig; Paket neu erzeugen. |
| `package_size` | Paket überschreitet das Upload-Limit. |
| `checksum_mismatch` | Paketinhalt stimmt nicht mit Manifest überein; Source-Artefakt neu bauen. |
| `missing_dependency` | Benötigte Paketversion zuerst validieren/aktivieren. |
| `rights_blocked` | Redistribution-Rechte erlauben keine Runtime-Aktivierung. |
| `runtime_blocked` | Validation hat das Paket explizit als nicht runtime-fähig markiert. |
| `revision_conflict` | Ansicht ist veraltet; Details neu laden und Aktion bewusst wiederholen. |
| `lease_busy` | Ein anderer Worker/Operator bearbeitet dieselbe Dataset-ID; nach Ablauf/Abschluss neu laden. |
| `reauth_required` | Superadmin-Identität im eingebetteten Reauth-Schritt erneut bestätigen. |

## Datenschutz und Audit

Öffentliche Referenzdaten dürfen keine Family-/User-IDs, privaten Artikelnamen, Haushaltswege, privaten Korrekturen oder Beobachtungen enthalten. Die Runtime-Record-Tabellen besitzen keine Beziehung zu Family/User/ShoppingItem/ShoppingList.

Operator-Audit enthält nur technische Dataset-Ziele und Aktionsarten. Activation-History speichert technische `reason_code`s, Versionswechsel und Revisionen — keinen freien Nutzertext und keine Haushaltsinhalte.

## Betrieb und Updates

Dieser Slice führt keinen neuen Daemon und keinen automatischen Scheduler ein. Größere automatisierte Update-Jobs müssen das bestehende Worker-/Lease-Prinzip verwenden und denselben Staging-/Validation-/Activation-Vertrag aufrufen.

Bei Incidents gilt:

1. letzten gültigen aktiven Stand nicht vorschnell deaktivieren;
2. Validation-/Rights-/Dependency-Blocker im Preview prüfen;
3. bei `revision_conflict` oder `lease_busy` Registry neu laden statt Zustände manuell in der DB zu ändern;
4. Rollback nur über den kanonischen Service ausführen;
5. keine Paketdateien oder private Haushaltsdaten in allgemeine Telemetrie kopieren.
