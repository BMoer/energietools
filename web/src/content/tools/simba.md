---
name: Simba — PV-Speicher-Simulator
operator: Jakob Kreisel
contact: https://github.com/holzjfk-a11y
contactLabel: github.com/holzjfk-a11y
description: PV + Batterie + Wärmepumpe simulieren — Eigenverbrauch, Spot, Arbitrage, Peak-Shaving.
hosting: external
url: https://simba.energietools.at
engineUsage: >-
  Nutzt aus der Engine: die Batterie-Dispatch-Strategien (`scenarios.simulate_battery`
  für self_consumption/spot/arbitrage), Peak-Shaving (`run_peak_shaving`), die
  Finanzkennzahlen (`finance`) und die Netzentgelte (`netz`). Eigener Teil: die
  FastAPI-/Frontend-App und die Live-Beschaffung (aWATTar/ENTSO-E/Solis/PVGIS),
  die übergangsweise hybrid bleibt. Der Dispatch-/COP-Kern wurde aus Jakobs `pvtool`
  in die offene Engine zurückgeführt (siehe CREDITS.md).
tags: [batteriespeicher, pv, wärmepumpe, gewerbe, spot]
order: 5
---

**Simba** simuliert PV-Anlage + Batteriespeicher (+ Wärmepumpe) über mehrere
Strategien — Eigenverbrauch, Spot-Optimierung, Arbitrage und Peak-Shaving — und
bewertet jede Speichergröße mit ROI.

Die App von **Jakob Kreisel** ist der Beweis, dass verschiedene Autor:innen auf
demselben offenen Fundament publishen: der Rechenkern läuft auf `energietools`,
die App und ihre Live-Connectoren betreibt Jakob selbst.

> Läuft auf Jakobs eigener Domain. Über „Tool öffnen" gehst du direkt dorthin —
> Anfragen laufen an Jakob, nicht an den Seitenbetreiber.
