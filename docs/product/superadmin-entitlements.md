# Superadmin: Lizenz & Zugriff

Stand: 2026-10-14 · Issue #83 · Entitlement-Core #227 · Roadmap #223

## Zweck

Superadmins können im Familiendetail unter **Lizenz & Zugriff** einen expliziten familienweiten Lizenz-Override setzen. Der Flow ist eine Bedienoberfläche über dem kanonischen Entitlement-Core; er führt kein zweites Plan-, Billing- oder Capability-Modell ein.

Der erste sichtbare Produktvertrag kennt `Light`, `Premium` und `VIP`. Diese Auswahl ist bewusst nur die aktuelle Produktprojektion. Weitere Tiers, Offers und Provider sollen später zentral ergänzt werden können, ohne Fachmodule oder die Superadmin-Navigation neu zu modellieren.

## Priorität der Zustände

Ohne expliziten Override gilt der kanonische Billing-/Grant-Zustand. Ein Superadmin-Override ist die einzige administrative Schicht, die den daraus berechneten Lizenzgrad bewusst ersetzen darf.

Ein Override ändert oder löscht keine Subscription-, Lifetime-, Legacy- oder Promotion-Grants. Wird er widerrufen oder läuft er ab, berechnet der Resolver automatisch wieder den nächsten gültigen Zustand aus den unveränderten darunterliegenden Grants.

Beispiele:

- aktive Premium-Subscription + Light-Override → effektiv Light; nach Entfernen wieder Premium
- Lifetime-VIP + zeitlich begrenzter Premium-Override → effektiv Premium; nach Ablauf wieder VIP
- keine weiteren gültigen Grants + entfernter Override → Light

## Datenverlust-Verbot

Ein Wechsel des Lizenzgrads löscht niemals Familien- oder Premium-Daten. Beim Downgrade können Premium-Create-/Write-/Automation-Aktionen über den zentralen Capability-Resolver eingeschränkt werden; gespeicherte fachliche Daten bleiben erhalten. Reaktivierung benötigt deshalb keine Datenmigration.

Das UI nennt diese Eigenschaft ausdrücklich und verwendet keine destruktive Downgrade-Aktion.

## Bedienung

1. Superadmin öffnet **Familien** und das Familiendetail.
2. **Lizenz & Zugriff** zeigt effektiven Lizenzgrad, Quelle, Fallback und Datenhaltungsregel.
3. Unter **Lizenzgrad ändern** wird Light, Premium oder VIP gewählt.
4. Optional kann ein Ablaufzeitpunkt gesetzt werden.
5. Ein auditierbarer Grund ist verpflichtend.
6. **Override speichern** aktiviert die Ausnahme.
7. **Override entfernen** benötigt ebenfalls einen Grund und stellt automatisch den nächsten kanonischen Zustand wieder her.

Billing/Provider bleibt fachlich und visuell ein separater Bereich. Einzelne Capability-Keys werden im ersten Slice nicht manuell geschaltet.

## Sicherheit und Audit

Nur Superadmins dürfen den Mutations-Endpunkt verwenden. Grant und Revocation laufen über die bestehenden #227 Services und damit über die vorhandene Entitlement-Historie sowie den #204 Audit-Stream.

Fresh Re-Auth ist im API-Vertrag als eigener Mutationspfad vorbereitet, wird für diesen ersten Slice aber noch nicht erzwungen. Eine spätere Aktivierung kann an derselben Stelle erfolgen, ohne Endpoint oder UI-Flow zu ersetzen.

## API

Familiendetail:

`GET /api/superadmin/families/<family_id>/`

liefert zusätzlich `entitlement_control` mit effektivem Zustand, aktivem Override, erlaubten sichtbaren Tiers, automatischem Fallback und Security-Hinweisen.

Override setzen/ersetzen:

`PUT /api/superadmin/families/<family_id>/entitlement-override/`

Payload:

```json
{
  "tier": "premium",
  "reason": "Support-Freischaltung",
  "ends_at": "2026-11-01T12:00:00Z"
}
```

`ends_at` ist optional.

Override entfernen:

`DELETE /api/superadmin/families/<family_id>/entitlement-override/`

Payload:

```json
{
  "reason": "Support-Freischaltung beendet"
}
```

## Nicht-Ziele

- keine Payment-Provider-Konfiguration
- keine Rohbearbeitung von Billingobjekten
- kein Capability-Mischpult
- keine Datenbereinigung beim Downgrade
- keine Annahme, dass Light/Premium/VIP dauerhaft die einzigen Tiers bleiben
