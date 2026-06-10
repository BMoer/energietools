# Simba — PV-Speicher-Simulator (auf energietools)

FastAPI-App (Backend + statische UI) von **Jakob Kreisel** (holzjfk-a11y),
re-wired auf die MIT-Library [`energietools`](../../README.md). Demonstriert in der
Gallery ([energietools.at](https://energietools.at)), dass **verschiedene Autor:innen**
Apps auf demselben Kern publishen.

> Ursprünglich gegen `pvtool` (batterystorage-sim) gebaut. Der **Rechenkern** ist
> jetzt energietools; die **Live-Beschaffung** bleibt übergangsweise hybrid bei pvtool.

## Auf energietools re-wired (verifiziert, boot-getestet)

| Endpoint | energietools |
|---|---|
| `POST /api/simulate` self_consumption · spot_optimized · arbitrage | `capabilities.scenarios.dispatch.simulate_battery` |
| `POST /api/simulate` peak_shaving | `capabilities.scenarios.peak_shaving.run_peak_shaving` |
| ROI (alle Szenarien) | `capabilities.finance.FinanceCapability` |
| `GET /api/grid-fees` | `capabilities.netz.per_kwh` (NE7-Haushalt) |
| `GET /api/grid-operators` | `capabilities.netz.data.load_alle_vnb` (fixt zugleich `list_operators`, das in pvtool fehlte) |
| `GET /api/balancing-prices` Summary | `tools.regelenergie.summarise_balancing_prices` |
| `GET /api/health` | energietools-Import-Probe |

UI-Schemas + API-Vertrag bleiben **unverändert** (das bestehende `static/index.html`
funktioniert weiter). Einheiten (EUR ↔ ct) werden nur im Service-Layer konvertiert.

## Noch hybrid bei pvtool (lazy importiert)

Beschaffung/Live + die volle Wärmepumpen-Summary (2-Pass-Thermalspeicher):
`/api/spot-prices` (aWATTar live), `/api/balancing-prices`+`/api/connect/entsoe`
(ENTSO-E), `/api/connect/solis`, `/api/connect/pvgis` (PVGIS-Stundenserie),
`/api/simulate` heatpump. **Diese Endpunkte brauchen vendored pvtool** unter
`vendor/pvtool/` — ohne pvtool bootet die App, nur sie sind dann nicht verfügbar.
Der Last-Teil von `/connect/pvgis` ist als `tools.load_builder.build_load` bereits
nach energietools portiert und kann als Nächstes umgehängt werden.

## Sicherheit (gefixt)

- `/api/connect/solis/defaults` gibt das Solis-`key_secret` **nicht mehr im Klartext**
  zurück (nur `has_key_secret: bool`).
- CORS: konkrete Origins statt `*` (über `SIMBA_CORS_ORIGINS` konfigurierbar).

## Lokal starten

```bash
pip install -e ../..                      # energietools aus dem Monorepo
pip install -r backend/requirements.txt
cd backend
PVTOOL_DATA_DIR="$(pwd)/data" PVTOOL_UPLOAD_DIR="$(pwd)/data" \
  uvicorn app.main:app --reload           # → http://localhost:8000
```

## Deployment

Eigener Container (Fly.io / Render), `backend/Dockerfile` + `docker-compose.yml`.
Empfohlen: Subdomain `simba.energietools.at`, von der Gallery als externe Karte
verlinkt (Astro-Verzeichnis unter `web/`, Eintrag `web/src/content/tools/simba.md`
mit `hosting: external`).
Solis-Credentials nur als Secret, nie im Image.
