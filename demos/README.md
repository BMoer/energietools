# energietools — Demo-Gallery

Vier kleine, in sich geschlossene Browser-Apps, die zeigen, was das Open-Source-Toolkit
[`energietools`](../README.md) kann. Sie laufen **komplett im Browser** (marimo → WASM/Pyodide)
auf der MIT-Library + ihren datierten Daten-Snapshots — **kein Server, kein proprietärer
gridbert-Code**. Jede Zahl trägt ihren Rechenweg und ihre Quelle.

Live: **[energietools.at](https://energietools.at)**

## Die Demos

| App | Frage | Capabilities |
|---|---|---|
| 🧾 [`rechnung.py`](rechnung.py) — Rechnungs-Röntgen | Wie setzt sich meine Stromrechnung zusammen, zahle ich zu viel? | `gesamtkosten`, `netzkosten`, `tariff_catalog`, `kosten_rechenweg` |
| ⚡ [`spot.py`](spot.py) — Spot-Eignungs-Check | Lohnt sich ein dynamischer Tarif für mein Lastprofil? | `spot_analysis`, `h0_profile`, EPEX-Snapshot, `grid_fees` |
| 🔋 [`speicher.py`](speicher.py) — Speicher-Sizing | Welche PV-Batteriegröße amortisiert sich? | `scenarios` (Dispatch), `finance` |
| 🔌 [`netzkosten.py`](netzkosten.py) — Netzkosten-Lokalisator | Was kostet das Netz an meiner PLZ, wie ist es aufgeschlüsselt? | `netzkosten`, `gesamtkosten`, `grid_fees` |

## Lokal entwickeln

```bash
pip install marimo            # einmalig
python -m marimo edit demos/netzkosten.py      # interaktiv editieren (CPython)
```

Im Browser-Modus (Pyodide) ist ein WASM-Bootstrap-Cell aktiv, der `energietools` per
`micropip` aus dem gebündelten Wheel (`/wheels/…`) lädt. Lokal unter CPython ist dieser
Cell ein No-op (energietools ist bereits installiert).

## Gallery bauen

```bash
python demos/build_site.py                     # → site/  (Wheel + 4 Apps + Landing + CNAME)
python -m http.server --directory site 8000    # → http://localhost:8000/
```

Das Build:
1. baut das `energietools`-Wheel frisch aus dem Repo,
2. exportiert jede Demo nach `site/<slug>/` als selbst-enthaltenes WASM-Bundle,
3. legt **ein** gemeinsames Wheel nach `site/wheels/` (root-relative von jeder App geladen),
4. schreibt `site/index.html` (Landing), `CNAME` (`energietools.at`) und `.nojekyll`.

## Deployment

GitHub Action [`.github/workflows/demos.yml`](../.github/workflows/demos.yml) baut die
Gallery bei jedem Push auf `main` (der `demos/`, `energietools/` oder `pyproject.toml`
berührt) und deployt sie auf GitHub Pages. Vor dem Export läuft ein Smoke-Gate
(`pytest` + eine echte CLI-Rechnung), damit nie eine kaputte Rechnung online geht.

### Custom Domain (energietools.at)

- `CNAME` mit `energietools.at` liegt im Build-Output (Apex-Domain → Gallery-Root).
- DNS beim Registrar:
  - **A** `@` → `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`
  - **CNAME** `www` → `bmoer.github.io`
- In GitHub: *Settings → Pages → Custom domain* = `energietools.at`, *Enforce HTTPS* an.

## Ehrlichkeit / Grenzen

Bewusst ausgelassen (laufen nicht rein im Browser, brauchen native/Server-Pfade):
PDF-Scan (`invoice_parser`, OCR), Live-PVGIS (`pv_sim`), Live-ENTSO-E, `load_profile`
(scikit-fda). PV-/Lastprofile werden synthetisiert (H0 + Sonnenbogen-Näherung), der
EPEX-Pfad ist ein **2025-Backtest** (keine Prognose), Tarif-Ranking schließt Gas per
Namensheuristik aus (der Open-Data-Katalog hat noch kein Sparte-Feld). Jede Demo
benennt ihre Grenzen im Audit-Footer.
