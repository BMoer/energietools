# energietools

Ein Open-Source-Toolkit (MIT) für den österreichischen Energiemarkt. energietools
ist der **auditierbare Kern**: Wissen, Daten und Rechnung, die von außen
nachvollziehbar sein sollen. Die Beschaffung (Scraper, Pipelines, Credentials, das
Produkt) bleibt proprietär; hier liegen nur das kuratierte Wissen, die publizierten
Daten-Snapshots und die deterministische Rechnung.

## Was energietools sein soll

Ein Agent-Toolkit aus **drei Schichten**, die ein Agent orchestriert, statt selbst
zu rechnen:

- **Wissen (Second Brain).** Ein nach Andrej Karpathys LLM-Wiki gebautes
  Markdown-Wiki (`wiki/`). Es erklärt, was die Dinge *bedeuten*: wie sich
  Gesamtenergiekosten zusammensetzen, wie Energiegemeinschaften funktionieren, was
  die Netzebenen sind. Kuratiert und verdichtet, kein Daten-Dump.
- **Daten (Open Data).** Datierte, gequellte Snapshots öffentlich verfügbarer Daten
  (`energietools/data/`): Tarife, Netzentgelte, aktive Förderungen. Jeder Snapshot
  trägt Stand-Datum und Quelle.
- **Rechnen (Simulationsbaukasten + Capabilities).** Verschaltbare physikalische
  Komponenten (PV, Batterie, E-Auto, Wärmepumpe, Gaskessel), die man zu einem System
  zusammensteckt und über einen konfigurierbaren Optimierer rechnet - plus die
  auditierbaren Capabilities (Tarifvergleich, Netzentgelt, Finanzkennzahlen).

**Der rote Faden:** der Agent liest *Wissen*, zieht den passenden *Daten*-Snapshot,
rechnet deterministisch über den *Baukasten*. Kein Rechnen im LLM, wo es still
falsch wird. Das Wiki sagt, was etwas bedeutet; die Daten liefern die aktuelle
Zahl; der Baukasten rechnet sie nachvollziehbar.

> **Audit-Prinzip.** Jede produzierte Zahl ist nachrechenbar: datierte, gequellte
> Snapshots statt Live-Scrape, ein lückenloser `Rechenweg` pro Ergebnis, keine
> stillen Defaults (fehlende Eingaben werfen einen `CapabilityError`). Schätzungen
> sind als solche gekennzeichnet, nicht als Abrechnung ausgegeben.

## Die drei Schichten im Gebrauch

### Wissen - `wiki/`
Ein Ordner aus Markdown-Seiten, **kein Server**. Zeig einen Agenten (oder dich
selbst) auf `wiki/index.md` bzw. den maschinenlesbaren Index `wiki/llms.txt`. Jede
Seite erklärt ein Konzept selbst-enthalten, mit Querlinks, `Berechnet von` (Link
zur zuständigen Capability) und `Quellen` + `Stand`. Einstieg:
[`wiki/netz/netzentgelte.md`](wiki/netz/netzentgelte.md) als ausgearbeitete Vorlage.

### Daten - `energietools/data/`
Versionierte First-Party-Snapshots: der Tarifkatalog (`data/tariffs/`), die
Netzentgelt-/Abgaben-Parameter (`data/netz/`) und aktive Förderungen
(`data/foerderungen.json`). Jeder Snapshot hat ein `MANIFEST.json` mit Provenance,
`Stand`, Lizenz und Verweisen auf [METHODIK.md](METHODIK.md) (wie erhoben +
validiert) und [NETZKOSTEN_UND_GEBUEHREN.md](NETZKOSTEN_UND_GEBUEHREN.md) (was die
Zahlen bedeuten). Die Scraper, die diese Daten erzeugen, sind **nicht** Teil dieses
Repos.

### Rechnen - Library + Baukasten
`pip install` und losrechnen - mit Rechenweg:

```python
from energietools.capabilities.tariffs import compare_against_catalog

# Vergleiche deinen Tarif gegen den Open-Data-Katalog - offline, auditierbar.
result = compare_against_catalog(
    verbrauch_kwh=3200,
    aktueller_lieferant="Wien Energie",
    aktueller_energiepreis_ct_kwh=25.0,   # brutto, aus deiner Rechnung
    aktuelle_grundgebuehr_eur_monat=6.0,  # brutto
    gebrauchsabgabe_rate=0.07,            # Wien
    plz="1060",
)
print(f"Max Ersparnis: {result.max_ersparnis_eur:.0f} EUR / Jahr")
# Jeder Tarif trägt einen vollständigen Rechenweg:
print(result.beste_fix[0].rechenweg.model_dump())
```

## Simulationsbaukasten (Schicht „Rechnen")

Drei Bausteine, verschaltbar:

1. **Komponenten** (`energietools/components/`) - jede mit gemeinsamer
   Schnittstelle (Energie rein/raus, Zustand): PV und Batterie mit echtem
   Verhalten; E-Auto, Gaskessel und der Wärmepumpen-Dispatch als erkennbare
   Platzhalter (das COP-Modell der Wärmepumpe ist real).
2. **System** (`energietools/system/`) - steckt Komponenten zusammen und
   bilanziert den Energiefluss diskret.
3. **Optimierer** (`energietools/optimizer/`) - konfigurierbare Zielfunktion
   (ökonomisch, Eigenverbrauch, Autarkie). Bewerten geht; der Löser für
   nicht-triviale Optima ist Platzhalter.

```python
from energietools.components import PVSystem, Battery, StepContext
from energietools.system import EnergySystem

system = EnergySystem([PVSystem(kwp=5.0), Battery.new(10.0)])
res = system.run([4000.0], [StepContext(dt_hours=8760.0)])
print(f"Eigenverbrauch {res.self_consumption_rate:.0%}, Autarkie {res.self_sufficiency_rate:.0%}")
```

Erste Auflösung ist **diskret** (eine Ingenieursrechnung, keine Zeitreihen); die
Komponenten-Schnittstelle ist so angelegt, dass die spätere Zeitreihen-Variante ein
Superset ist - ein Skalar ist ein Ein-Punkt-Profil.

## Capabilities

Jede Fähigkeit hat eine Form - `run(**kwargs) -> CapabilityResult` - und
registriert sich selbst in der CLI. Auflisten: `python -m energietools list`.

| Capability | Beschreibung |
|------------|--------------|
| `tariff_catalog` / `tariff_compare` / `tariff_advice` | Open-Data-Tarifkatalog abfragen, Tarif vergleichen, Rechnung → Vergleich (mit Rechenweg) |
| `netzkosten` / `gesamtkosten` / `netz_verfuegbar` / `tarifvergleich_inkl_netz` | Regulierte Netz-/Gesamtkosten je PLZ, Verfügbarkeit, Vergleich inkl. Netz |
| `grid_fees` | Netzentgelt je Betreiber/Land (per kWh), §16b-Speicherbefreiung, voller Rechenweg |
| `finance` | Investitionskennzahlen ROI/NPV/LCOE (Standard-Finanzformeln) |
| `scenarios` | Batterie-Größen-Sweep mit Eigenverbrauchs-Dispatch + ROI (ersetzt das alte `battery_sim`) |
| `heatpump` | Heizkostenvergleich Wärmepumpe vs. Gas (Carnot-COP, diskret) |
| `community_metrics` | Energiegemeinschafts-Kennzahlen (Eigenverbrauch/Autarkie/Reststrom/Überschuss) |
| `pv_sim` / `spot_analysis` / `load_profile` / `energy_monitor` / `beg_advisor` / `web_search` | Weitere deterministische Werkzeuge |

```bash
python -m energietools list
python -m energietools grid_fees --json '{"verbrauch_kwh": 3500}'
python -m energietools finance --json '{"investition_eur": 9000, "jaehrlicher_ertrag_eur": 850, "nutzungsdauer_jahre": 15, "diskontrate": 0.04}'
```

## Installation

```bash
pip install energietools            # Kern
pip install energietools[all]       # alle optionalen Abhängigkeiten
pip install energietools[analysis]  # FDA-Anomalien, Spotpreise
pip install energietools[pdf]       # PDF-Rechnungs-Parsing
pip install energietools[search]    # Web-Suche
pip install energietools[excel]     # Excel-Support
```

energietools bündelt **keinen** LLM-Client. Fähigkeiten, die ein LLM brauchen (der
Rechnungs-Scan `invoice_parser`), bekommen einen Provider injiziert (Protokoll:
`energietools.tools.llm_protocol.LLMProvider`); der konkrete Client lebt in der
aufrufenden Anwendung.

## Vertrauen & Herkunft

- [METHODIK.md](METHODIK.md) - wie die Daten erhoben und validiert werden:
  First-Party- + gesetzliche Quellen, der Cross-Check gegen die
  Systemnutzungsentgelte-Verordnung (BGBl. II Nr. 305/2025), Fail-open-Disziplin,
  Reviewer-Checkliste.
- [NETZKOSTEN_UND_GEBUEHREN.md](NETZKOSTEN_UND_GEBUEHREN.md) - die
  Wissens-Referenz: wie sich ein österreichischer Strompreis zusammensetzt
  (Netzkosten, Abgaben, Steuern), mit Rechenweg und Beispiel.

## Grenze offen / proprietär

Öffentlich (MIT): Wissen, deterministische Rechnung, Daten-Snapshots. Proprietär
(bleibt in gridbert): Beschaffung, Scraper, Pipelines, Credentials, Produkt.
Connectoren gehören nicht in den öffentlichen Kern.

## Lizenz & Attribution

MIT - siehe [LICENSE](LICENSE). Teile des Simulationsbaukastens (Batterie-Dispatch,
Wärmepumpen-COP) sind aus `pvtool` portiert; Finanz- und Netzentgelt-Logik sind
Clean-Room-Reimplementierungen. Herkunft und Mit-Autorschaft: siehe
[CREDITS.md](CREDITS.md).

Offene Punkte und Platzhalter: [TODO.md](TODO.md).
