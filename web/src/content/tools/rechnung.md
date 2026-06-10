---
name: Rechnungs-Röntgen
operator: Ben Mörzinger
contact: https://moerzinger.eu
contactLabel: moerzinger.eu
description: Stromrechnung in Energie / Netz / Abgaben / USt zerlegen — mit Tarifvergleich.
hosting: hosted
url: /rechnung/
engineUsage: >-
  Nutzt aus der Engine: `gesamtkosten`/`netzkosten` (auditierter Rechenweg),
  den Open-Data-Tarifkatalog und `kosten_rechenweg`. Eigener Teil: die UI und der
  Ranking-Loop über den Katalog (Vergleich/Ranking ist bewusst keine Engine-
  Capability — die Engine liefert die Kosten je Tarif, das Ranking baut die App).
tags: [tarifvergleich, rechnung, haushalt, österreich]
order: 1
featured: true
---

Eine Stromrechnung ist drei Rechnungen in einer: **Energie** (Lieferant),
**Netz** (reguliert) und **Abgaben & Steuern**. Das Rechnungs-Röntgen zerlegt sie
lückenlos und stellt den eigenen Tarif gegen die günstigsten Strom-Fixpreis-Tarife
im Open-Data-Katalog.

Manuelle Eingabe der Eckwerte (kein PDF-Upload in dieser Demo), gerechnet im Browser
auf `energietools`. Gas wird per Namensheuristik ausgeschlossen, Spot-/Floater-Tarife
werden nicht gerankt — beides offen im Audit-Footer benannt.
