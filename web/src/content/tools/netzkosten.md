---
name: Netzkosten-Lokalisator
operator: Ben Mörzinger
contact: https://moerzinger.eu
contactLabel: moerzinger.eu
description: Regulierte Netzkosten PLZ-scharf — lückenloser Rechenweg mit Preisblatt-Quelle.
hosting: hosted
url: /tools/netzkosten/
engineUsage: >-
  Nutzt aus der Engine: den auditierten Netzentgelt-Snapshot (data/netz) und die
  Capabilities `netzkosten`/`gesamtkosten`/`grid_fees` inkl. PLZ→VNB-Auflösung und
  lückenlosem Rechenweg. Eigener Teil: nur die Browser-Oberfläche (marimo/WASM).
  Es gibt keine proprietäre Rechenlogik — das ist der auditierbare Kern selbst.
tags: [netzentgelt, haushalt, österreich, rechenweg]
order: 4
---

Der **Stromnetz-Anteil** ist rund ein Drittel der Stromrechnung, reguliert und
hängt am Netzbetreiber deiner PLZ — nicht am Lieferanten. Der Netzkosten-Lokalisator
löst ihn PLZ-scharf auf und schlüsselt jede Komponente auf (Netznutzung, Netzverlust,
EAG-Förderbeitrag, Elektrizitätsabgabe, Pauschalen, USt) — jede Zahl mit Stand-Datum
und Link aufs offizielle Preisblatt.

Läuft komplett im Browser auf der Open-Source-Library `energietools`. Bei geteilten
PLZ wird **bewusst nicht geschätzt**, sondern ein ehrlicher Hinweis ausgegeben.
