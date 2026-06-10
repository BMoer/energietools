# energietools demo — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT
"""Speicher-Sizing — lohnt sich ein PV-Batteriespeicher, und welche Größe?

Reine Browser-Demo (marimo/WASM). Fährt den echten Eigenverbrauchs-Dispatch (SOC,
Wirkungsgrad) über mehrere Speichergrößen und bewertet jede mit Amortisation/NPV.
PV- und Verbrauchsprofil werden synthetisiert (keine Live-PVGIS) — klar gekennzeichnet.
"""

import marimo

__generated_with = "0.23.9"
app = marimo.App(width="medium", app_title="Speicher-Sizing")


@app.cell
async def _():
    import sys

    booted = True
    if sys.platform == "emscripten":
        import micropip

        # Gemeinsames Wheel im Gallery-Root; root-relative URL funktioniert unter
        # jedem App-Unterpfad (localhost wie energietools.at).
        await micropip.install(["pydantic", "numpy"])
        await micropip.install("/wheels/energietools-0.3.0-py3-none-any.whl", deps=False)
    return (booted,)


@app.cell
def _(booted):
    import marimo as mo

    _ = booted
    return (mo,)


@app.cell
def _(booted):
    import math
    from datetime import datetime, timedelta

    from energietools.capabilities.scenarios.capability import ScenariosCapability
    from energietools.tools.h0_profile import synthesize_h0_consumption

    _ = booted
    return ScenariosCapability, datetime, math, synthesize_h0_consumption, timedelta


@app.cell
def _(datetime, math, timedelta):
    def synth_pv(kwp, specific_yield, start, end):
        """Synthetisches stündliches PV-Profil, normiert auf kWp × spez. Ertrag.

        Tagesform (Sonnenbogen) × Saisonfaktor (Sommer-Peak). Bewusst eine Näherung
        ohne Standort-Geometrie — ersetzt die (Live-)PVGIS-Anbindung für die Demo.
        """
        pts = []
        cur = start
        while cur < end:
            h = cur.hour
            doy = cur.timetuple().tm_yday
            day = max(0.0, math.sin(math.pi * (h - 6) / 12)) if 6 <= h <= 18 else 0.0
            seas = 0.55 + 0.45 * math.cos(2 * math.pi * (doy - 172) / 365)
            pts.append((cur, day * seas))
            cur += timedelta(hours=1)
        tot = sum(w for _, w in pts) or 1.0
        target = kwp * specific_yield
        return [{"kwh": target * w / tot} for _, w in pts]

    return (synth_pv,)


@app.cell
def _(mo):
    mo.md(
        """
        # 🔋 Speicher-Sizing

        Ein PV-Batteriespeicher erhöht deinen **Eigenverbrauch** und deine **Autarkie** —
        aber zahlt er sich auch? Das hängt an Speicherpreis, Strompreis-Spread und deiner
        PV-Größe. Hier läuft der **echte Eigenverbrauchs-Dispatch** (Ladezustand,
        Wirkungsgrad) über mehrere Größen, jede mit **Amortisation und Kapitalwert (NPV)**.

        > Gerechnet im Browser auf [`energietools`](https://github.com/BMoer/energietools).
        > PV- und Verbrauchsprofil sind **synthetisch** (H0 + Sonnenbogen-Näherung), weil die
        > Demo offline läuft — mit echtem Lastgang/PVGIS würde es schärfer.
        """
    )
    return


@app.cell
def _(mo):
    verbrauch = mo.ui.slider(start=2000, stop=10000, step=250, value=4500, label="**Jahresverbrauch** (kWh)", show_value=True)
    kwp = mo.ui.slider(start=2.0, stop=15.0, step=0.5, value=6.0, label="**PV-Anlage** (kWp)", show_value=True)
    speicherpreis = mo.ui.slider(start=300, stop=900, step=25, value=550, label="**Speicherpreis** (€/kWh installiert)", show_value=True)
    bezug = mo.ui.number(start=10.0, stop=50.0, step=0.5, value=25.0, label="Strom-Bezugspreis (brutto ct/kWh)")
    einspeisung = mo.ui.number(start=0.0, stop=20.0, step=0.5, value=7.0, label="Einspeisetarif (ct/kWh)")
    nutzungsdauer = mo.ui.number(start=8, stop=20, step=1, value=15, label="Nutzungsdauer (Jahre)")
    controls = mo.vstack(
        [
            mo.hstack([verbrauch, kwp], justify="start", gap=2),
            mo.hstack([speicherpreis, bezug], justify="start", gap=2),
            mo.hstack([einspeisung, nutzungsdauer], justify="start", gap=2),
        ]
    )
    controls
    return bezug, einspeisung, kwp, nutzungsdauer, speicherpreis, verbrauch


@app.cell
def _(
    ScenariosCapability,
    bezug,
    datetime,
    einspeisung,
    kwp,
    mo,
    nutzungsdauer,
    speicherpreis,
    synth_pv,
    synthesize_h0_consumption,
    verbrauch,
):
    start, end = datetime(2025, 1, 1), datetime(2026, 1, 1)
    cons = synthesize_h0_consumption(verbrauch.value, start, end)
    prod = synth_pv(kwp.value, 1000.0, start, end)

    res = ScenariosCapability().run(
        production_data=prod,
        consumption_data=cons,
        energiepreis_ct_kwh=bezug.value,
        einspeisung_ct_kwh=einspeisung.value,
        speicher_kosten_eur_pro_kwh=speicherpreis.value,
        nutzungsdauer_jahre=int(nutzungsdauer.value),
        diskontrate=0.04,
        dt_hours=1.0,
        sizes_kwh=[0, 5, 7.5, 10, 15],
    )

    d = res.data
    best = d["bestes_szenario"]

    def _f(x):
        return "—" if x is None else f"{x:.0f}"

    def _amort(x):
        return "amortisiert nie" if x is None or x == float("inf") else f"{x:.1f} J"

    zeilen = []
    for s in d["szenarien"]:
        mark = " ⭐" if s["kapazitaet_kwh"] == best["kapazitaet_kwh"] and s["kapazitaet_kwh"] > 0 else ""
        zeilen.append(
            f'| {s["kapazitaet_kwh"]:g} kWh{mark} | {s["eigenverbrauchsquote"]*100:.0f} % | '
            f'{s["autarkiegrad"]*100:.0f} % | {s["ersparnis_jahr_eur_schaetzung"]:.0f} € | '
            f'{_amort(s["amortisation_jahre"])} | {s["npv_eur"]:.0f} € |'
        )
    tabelle = "\n".join(zeilen)

    best_npv = best["npv_eur"]
    if best["kapazitaet_kwh"] == 0 or best_npv <= 0:
        kind = "warn"
        headline = (
            "Bei diesen Annahmen **amortisiert sich kein Speicher** (bester NPV ≤ 0). "
            "Senke den Speicherpreis oder erhöhe den Strompreis-Spread und sieh, ab wann es kippt."
        )
    else:
        kind = "success"
        headline = (
            f'Wirtschaftlich beste Größe: **{best["kapazitaet_kwh"]:g} kWh** '
            f'(NPV **+{best_npv:.0f} €**, Amortisation {_amort(best["amortisation_jahre"])}).'
        )

    out = mo.vstack(
        [
            mo.callout(mo.md(headline), kind=kind),
            mo.md(
                "| Speichergröße | Eigenverbrauch | Autarkie | Ersparnis/Jahr | Amortisation | NPV |\n"
                "|---|---|---|---|---|---|\n" + tabelle
            ),
            mo.md(f"<small>{d['hinweis']}</small>"),
        ]
    )
    out
    return


@app.cell
def _(mo):
    mo.md(
        """
        ---
        <small>
        **Dispatch:** echter Eigenverbrauchs-Dispatch über die `Battery`-Komponente (SOC,
        Lade-/Entladewirkungsgrad). **Finanzkennzahlen:** Standard-Formeln (Amortisation, NPV
        mit 4 % Diskontrate). **Grenzen:** PV-/Verbrauchsprofil synthetisch (keine Live-PVGIS,
        stündliche Auflösung); Erlöse sind eine **Jahres-Hochrechnung**, keine Abrechnung.<br>
        Nachrechenbar: `python -m energietools scenarios --json '{…production_data, consumption_data…}'`
        </small>
        """
    )
    return
