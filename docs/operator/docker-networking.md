# Docker-Netzwerk für den FamilyOS-Proxy

FamilyOS nutzt neben dem normalen Compose-Netz ein kleines dediziertes `familyos_proxy`-Netz. Dieses Netz hat genau einen Zweck: Django soll eingehende `X-Forwarded-For`-Header nur vom eigenen Caddy-Peer akzeptieren und nicht pauschal einem ganzen privaten Docker-Adressbereich vertrauen.

## Standardvertrag

Neue Installationen verwenden standardmäßig bzw. über den Setup-Wizard ein zusammengehöriges Tupel:

```env
FAMILYOS_PROXY_SUBNET=172.28.254.0/28
FAMILYOS_PROXY_DYNAMIC_RANGE=172.28.254.0/29
FAMILYOS_CADDY_IP=172.28.254.14
AUTH_TRUSTED_PROXY_CIDRS=172.28.254.14/32
```

Dabei gilt:

- `FAMILYOS_PROXY_SUBNET` ist das gesamte dedizierte Proxy-Netz.
- `FAMILYOS_PROXY_DYNAMIC_RANGE` ist der Bereich, aus dem Docker dynamische Container-Adressen vergibt.
- `FAMILYOS_CADDY_IP` liegt bewusst **außerhalb** dieses dynamischen Bereichs, aber innerhalb des Subnetzes.
- `AUTH_TRUSTED_PROXY_CIDRS` muss exakt auf dieselbe Caddy-Adresse mit `/32` zeigen.

Dadurch kann ein dynamisch gestarteter Backend-Container niemals dieselbe Adresse erhalten wie der statisch gepinnte Caddy-Container.

## Automatische Auswahl im Setup

`scripts/setup.sh` testet mehrere kleine Kandidaten direkt beim Docker-Daemon. Docker lehnt überlappende Pools ab; der erste erfolgreich temporär angelegte Kandidat wird wieder entfernt und anschließend in `.env` persistiert.

Beim erneuten Setup wird ein bereits vollständig konfiguriertes Tupel beibehalten, damit eine funktionierende Installation nicht unnötig auf ein anderes internes Netz wechselt.

## Bestehende Installation mit `Pool overlaps`

Typischer Fehler:

```text
failed to create network familyos_proxy:
invalid pool request: Pool overlaps with other one on this address space
```

Dann zunächst vorhandene Docker-Netze anzeigen:

```bash
docker network inspect $(docker network ls -q) \
  --format '{{.Name}}: {{range .IPAM.Config}}{{.Subnet}} {{end}}'
```

Wähle anschließend ein freies `/28` und halte die vier Werte konsistent. Beispiel:

```env
FAMILYOS_PROXY_SUBNET=172.28.254.0/28
FAMILYOS_PROXY_DYNAMIC_RANGE=172.28.254.0/29
FAMILYOS_CADDY_IP=172.28.254.14
AUTH_TRUSTED_PROXY_CIDRS=172.28.254.14/32
```

Danach das Compose-Netz neu erstellen:

```bash
docker compose down
docker network rm rapporter_familyos_proxy 2>/dev/null || true
docker compose up -d --build
```

## Bestehende Installation mit `Address already in use`

Wenn das Subnetz selbst gültig ist, aber eine feste Caddy-IP im dynamischen Docker-Pool liegt, kann Docker dieselbe Adresse bereits an einen anderen Container vergeben haben.

Der aktuelle Compose-Vertrag verhindert das mit `FAMILYOS_PROXY_DYNAMIC_RANGE`. Bei älteren `.env`-Dateien die Variable ergänzen und Caddy auf eine Adresse außerhalb des dynamischen Bereichs setzen.

## Kontrolle

Aufgelöste Compose-Konfiguration prüfen:

```bash
docker compose config | grep -A10 -B3 familyos_proxy
```

Laufende Adressen prüfen:

```bash
docker network inspect rapporter_familyos_proxy \
  --format '{{range .Containers}}{{.Name}} -> {{.IPv4Address}}{{println}}{{end}}'
```

Erwartet ist beispielsweise:

```text
rapporter-backend-1 -> 172.28.254.2/28
rapporter-caddy-1 -> 172.28.254.14/28
```

## Sicherheitsregel

`AUTH_TRUSTED_PROXY_CIDRS` darf nicht bequem auf das gesamte Docker-Subnetz erweitert werden. FamilyOS vertraut absichtlich nur dem gepinnten Caddy-Peer. Bei einem Subnetzwechsel müssen Caddy-IP und Trusted-CIDR daher gemeinsam geändert werden.
