---
name: Spot-Eignungs-Check
operator: Ben Mörzinger
contact: https://moerzinger.eu
contactLabel: moerzinger.eu
description: Lohnt sich ein dynamischer Tarif für mein Lastprofil? Backtest gegen EPEX 2025.
hosting: hosted
url: /tools/spot/
engineUsage: >-
  Nutzt aus der Engine: den gebündelten EPEX-AT-Snapshot, `spot_analysis`
  (Profilkostenfaktor), das H0-Profil und den Netzanteil aus `grid_fees`.
  Eigener Teil: die UI. Reiner Backtest, keine Prognose.
tags: [spot, dynamischer-tarif, haushalt, österreich]
order: 2
---

Dynamische (Spot-)Tarife folgen dem Börsenstrompreis Stunde für Stunde. Ob sie sich
lohnen, hängt am **Verbrauchsprofil** — der **Profilkostenfaktor** macht das messbar.

Backtest gegen den gebündelten EPEX-AT-Snapshot 2025 (8.760 Stunden), gerechnet im
Browser auf `energietools`. Ohne Smart-Meter-Daten wird ein H0-Standardlastprofil
synthetisiert — eine faire Näherung, **keine Prognose** künftiger Preise.
