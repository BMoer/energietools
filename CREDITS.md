# Credits & Attribution

energietools steht unter der MIT-Lizenz (siehe [LICENSE](LICENSE),
Copyright 2026 Benjamin Mörzinger).

## pvtool / batterystorage-sim (Simulationsbaukasten)

Teile der Schicht „Rechnen" gehen auf die Batteriespeicher-Engine **`pvtool`**
zurück, entwickelt von **Jakob (GitHub: holzjfk-a11y)** im Repo
`batterystorage-sim` (Package `Solis_API/pvtool/`). Jakob hat der Übernahme unter
MIT zugestimmt und wird als **Co-Autor** geführt.

### Was portiert wurde (mit Herkunftsvermerk im Datei-Header)

- **Batterie-Eigenverbrauchs-Dispatch** - `energietools/components/battery.py`
  (SOC-/Wirkungsgrad-Logik) und der Runner
  `energietools/capabilities/scenarios/dispatch.py`. Auf die diskrete
  Component-Schnittstelle und immutable State umgesetzt.
- **Wärmepumpen-COP (Carnot-Fraktion)** - `energietools/components/heatpump.py`.
  Standard-Physik (Carnot-Wirkungsgrad × Gütegrad), nach dem pvtool-Ansatz.
- **Preis-getriebener Batterie-Dispatch** (spot_optimized / arbitrage, Tages-
  Perzentil-Schwellen + FCR-SOC-Reserve) - `energietools/capabilities/scenarios/dispatch.py`
  (`simulate_battery`). Pandas-/numpy-frei über die Battery-Komponente.
- **Greedy Peak-Shaving** (Leistungspreis/Demand-Charge) -
  `energietools/capabilities/scenarios/peak_shaving.py`. Der `optimal`-Modus
  (CVXPY/LP) wurde NICHT übernommen.
- **Komponierbares Lastprofil** (Wärmepumpen-/EV-/Warmwasser-Last + Außentemp-
  Modell) - `energietools/tools/load_builder.py`. Der Haushalt nutzt das
  bestehende `h0_profile`, die COP die `HeatPump`-Komponente.
- **Regelenergie-Auswertung** (Balancing-Preis-Summary, FCR/aFRR-Kapazitätserlös)
  - `energietools/tools/regelenergie.py`. Die stochastische FCR-Aktivierungs-
  Simulation wurde NICHT übernommen (nicht-deterministisch).

Die Web-App **Simba** (`apps/simba/`, ursprünglich `Simba-webapp`) stammt
ebenfalls von Jakob und wurde von ihrem `pvtool`-Backend auf energietools
re-wired (Rechenkern), die Live-Beschaffung bleibt übergangsweise hybrid bei
pvtool. Alle obigen Ports tragen einen Herkunftsvermerk im Datei-Header.

### Was clean-room reimplementiert wurde (nicht portiert)

Aus lizenz-unabhängigen, öffentlichen Quellen neu geschrieben - kein pvtool-Code:

- **Netzentgelte** - `energietools/capabilities/netz/` (per_kwh-Modul, ehem. `grid_fees/`). Operator- und
  länderparametrisiert; die österreichischen Zahlen stammen aus dem auditierten,
  gequellten `data/netz`-Snapshot (Systemnutzungsentgelte-Verordnung
  BGBl. II Nr. 305/2025, Netzbetreiber-Preisblätter, ElAbgG/EAG), nicht aus pvtool.
- **Finanzkennzahlen ROI/NPV/LCOE** - `energietools/capabilities/finance/`.
  Standard-Finanzformeln.

> Hinweis zur Auditierbarkeit: Wo pvtool und der bereits im Repo vorhandene,
> gequellte `data/netz`-Snapshot voneinander abwichen (z.B. Elektrizitätsabgabe
> 2026, NE7-Arbeitspreise), ist der gequellte Snapshot maßgeblich - nicht die
> pvtool-Konstanten.

## Relizenzierung AGPL → MIT (gridbert-Konsolidierung)

Der Owner (Benjamin Mörzinger) hat folgende selbst geschriebene Module aus
**gridbert** (AGPL-3.0-only) nach energietools (MIT) **neu formuliert** — kein
AGPL-Header wurde in den MIT-Baum übernommen, die Logik wurde unter MIT neu
geschrieben:

- **Spot/Floater-Backtest-Mathematik** (PRIO-1 S3) — `energietools/tools/cost_engine.py`,
  `energietools/tools/spot_pricing.py`, `energietools/tools/h0_profile.py`. Offline
  (EPEX-Serie wird hineingereicht); die Beschaffung (aWATTar-Fetch) bleibt in gridbert.
  `build_price_at` wurde modellfrei (Primitiven) umformuliert. Die EPEX-Snapshot-Daten
  (`data/spot/`) sind aus der öffentlichen aWATTar-Marketdata-API abgeleitet.
- **Per-Szenario-Kosten-Engine** (PRIO-1 S5-Prep) — `energietools/cost.py`
  (`gesamtkosten_szenario`/`energie_rechenweg`). Konsolidiert die bereits unter MIT
  vorhandenen Bausteine (basisgenaue Gebrauchsabgabe, Netzentgelt-Snapshot, Spot-Backtest,
  Rabatt-Logik aus `kosten_rechenweg`) zum vollen Szenario-Kosten-Pfad inkl. Neukunden-
  rabatt + Spot/Floater. Die separate-Block-Formel spiegelt gridberts `_tariff_from_row`,
  neu unter MIT formuliert (kein AGPL-Header übernommen).

## Vorarbeiten

Einzelne deterministische Werkzeuge (`spot_analysis`, `load_profile`) tragen
Herkunftsvermerke auf frühere eigene Projekte (lastgang-analysator) in ihren
Datei-Headern.
