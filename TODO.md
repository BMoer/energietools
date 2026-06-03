# TODO - bewusst offene Lücken

Dieses Repo ist ein **erster horizontaler Durchstich**: die Struktur ist
vollständig (alle drei Schichten, alle Komponenten existieren), die Tiefe ist
selektiv. Hier stehen die bewusst offen gelassenen Punkte - erkennbar, nicht
versteckt. Platzhalter im Code werfen `NotImplementedError` mit einem Docstring,
der mit `PLATZHALTER:` beginnt.

## Platzhalter im Code (Struktur da, Verhalten offen)

- [ ] **E-Auto** (`energietools/components/ev.py`) - Ladebedarf je Intervall als
  Last melden: ungesteuert vs. PV-/preisgesteuertes Laden, Anwesenheits-/Fahrprofil,
  Ziel-SOC.
- [ ] **Gaskessel** (`energietools/components/gas_boiler.py`) - Wärmebedarf aus Gas
  decken (Wirkungsgrad, Gaspreis), Baseline/bivalenter Backup zur Wärmepumpe;
  bilanziert auf dem Wärme-Bus (der Wärme-Bus selbst fehlt noch im `system/`).
- [ ] **Wärmepumpen-Dispatch** (`energietools/components/heatpump.py`, `step`) - der
  COP ist real (`cop()`); offen ist der 2-Pass-Lastgang (Wärmebedarf → COP → Last,
  thermischer Speicher, Bivalenzpunkt, Gas-Baseline, PV-Deckung). Braucht ein Zeitprofil.
- [ ] **Optimierer-Löser** (`energietools/optimizer/optimizer.py`, `optimize`) -
  Bewerten (`evaluate`) geht; die Suche nach dem Optimum einer Zielfunktion braucht
  einen echten Solver. Solver-Wahl (CVXPY/Pyomo) offen.

## Architektur-Entscheidungen

- [ ] **Auflösung diskret → Zeitreihe.** v1 ist diskret (ein Skalar = ein
  Ein-Punkt-Profil). Die Zeitreihen-Variante als **Superset** des Komponenten-
  Interface entwerfen, nicht als Rewrite - `Component.step` N-fach durchlaufen,
  Zustand weiterreichen. `StepContext.dt_hours` trägt schon die Intervalllänge.
- [ ] **Abbildung pvtool-Dispatch auf den allgemeinen Baukasten.** Aktuell liegt die
  pvtool-Dispatch-Logik als erste funktionierende Referenz unter `capabilities/
  scenarios/` (über die `Battery`-Komponente). Offen: ob die Szenarien (Eigenverbrauch,
  Spot, Arbitrage, Peak-Shaving) als **Optimierer-Strategien** modelliert werden oder
  eigenständige Capabilities bleiben.
- [ ] **Wärme-Bus im System.** `system/` bilanziert nur den elektrischen Bus;
  Konverter (Gaskessel) und der thermische Pfad der Wärmepumpe brauchen einen
  zweiten (Wärme-)Bus.

## Netzentgelte (grid_fees)

- [ ] **NE3-NE6 befüllen.** `grid_fees` trägt strukturell alle Netzebenen, v1 nutzt
  den gequellten NE7-Haushalt-Snapshot (`data/netz/`). NE3-NE6 (für gewerbliche/
  Einspeise-Szenarien) sind noch nicht hinterlegt - aus dem E-Control-Preisblatt
  ergänzen, nicht raten.
- [ ] **Länder-Dimension (DE/CH).** `country` ist parametrisiert; nur `AT` ist
  befüllt. `country != "AT"` liefert fail-open `None`. DE/CH später ergänzen
  (`data/grid_fees/` je Land), ohne Rewrite.
- [ ] **Netzbetreiber-Abdeckung.** `data/netz` deckt 14 Netzbereiche; weitere VNB
  und deren Doppeltarif (HT/NT) ergänzen.

## Finanzen (finance)

- [ ] **pv_sim/beg auf finance umstellen.** Die naive `amortisation_jahre` wurde aus
  `models/pv.py` entfernt und `models/battery.py` (mit `battery_sim`) gelöscht;
  `scenarios` nutzt bereits `finance`. Offen: `pv_sim` und `beg_advisor` ebenfalls
  über `finance` rechnen lassen (statt lokaler Inline-Berechnung).

## Daten & Provenance

- [ ] **Welche gridbert-Open-Data-Quellen kommen dazu (v2).** Bewusste Auswahl durch
  Ben - existiert, ist öffentlich, aber noch nicht gemerged (Gas-Netzentgelte,
  weitere Förderungen, …). Kein Rateversuch.
- [ ] **Welche Berechnungslogiken aus gridbert übernommen werden.** Ebenfalls
  bewusste Auswahl durch Ben.
- [ ] **Provenance-Lücken schließen.** `plz_netzbereich.json`, `vnb_attribution.json`
  und `beg_providers.json` tragen kein eigenes `_meta` (nur via Layer-MANIFEST
  gezählt); `foerderungen.json` hat ein `_meta`, aber kein eigenes `MANIFEST` mit
  `provenance`/`license`. Eigene MANIFESTs/Meta ergänzen (Stand + Quelle je Snapshot).
- [ ] **Wiki aktuell halten.** Ingest-Mechanismus aus offiziellen Datenquellen
  (Förderungen monatlich, Tarife und Netzentgelte nach E-Control-Zyklus). Wie genau,
  ist offen.

## Wiki-Inhalte

- [ ] **Kategorie-Seiten ausarbeiten.** `wiki/netz/netzentgelte.md` ist die
  vollständig ausgearbeitete Vorlage; die übrigen Kategorie-Seiten (markt, tarife,
  steuern, foerderung, messung, wirtschaftlichkeit, gas) sind Gerüst und werden
  bewusst aufgebaut und gepflegt (nicht aus dem Vault gekippt).

## Connectoren & Integration

- [ ] **`BaseConnector`-Protokoll.** Höchstens das Protokoll gehört in den
  öffentlichen Kern; konkrete Implementierungen (Solis, Wiener Netze, …) bleiben
  proprietär. Noch nicht angelegt.
- [ ] **MCP-Server als optionaler Connector.** Wiki und Baukasten als Tools für
  beliebige Agents - später.
