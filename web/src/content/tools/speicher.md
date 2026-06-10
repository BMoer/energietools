---
name: Speicher-Sizing
operator: Ben Mörzinger
contact: https://moerzinger.eu
contactLabel: moerzinger.eu
description: PV-Batteriegröße mit echtem Dispatch und auditierbarem ROI (NPV/Amortisation).
hosting: hosted
url: /speicher/
engineUsage: >-
  Nutzt aus der Engine: den Eigenverbrauchs-Dispatch (`scenarios`, SOC/Wirkungsgrad
  über die Battery-Komponente) und die Finanzkennzahlen (`finance`: NPV/Amortisation/
  LCOE). Eigener Teil: die UI und das synthetische PV-Profil (offline statt Live-PVGIS).
tags: [batteriespeicher, pv, wirtschaftlichkeit, österreich]
order: 3
---

Ein PV-Batteriespeicher erhöht Eigenverbrauch und Autarkie — aber zahlt er sich aus?
Der Speicher-Sizing-Rechner fährt den **echten Eigenverbrauchs-Dispatch** (Ladezustand,
Wirkungsgrad) über mehrere Größen und bewertet jede mit **Amortisation und Kapitalwert**.

Gerechnet im Browser auf `energietools`. PV- und Verbrauchsprofil sind synthetisch
(H0 + Sonnenbogen-Näherung), weil die Demo offline läuft — mit echtem Lastgang/PVGIS
würde es schärfer.
