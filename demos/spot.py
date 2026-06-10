# energietools demo — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT
"""Spot-Eignungs-Check — lohnt sich ein dynamischer (Spot-)Tarif für MEIN Profil?

Reine Browser-Demo (marimo/WASM). Rechnet ein H0-Lastprofil gegen den gebündelten,
datierten EPEX-AT-Snapshot (2025) — offline, deterministisch, mit Profilkostenfaktor
und ehrlichem Fix-vs-Spot-Vergleich. Kein Live-Call, keine Prognose: ein Backtest.
"""

import marimo

__generated_with = "0.23.9"
app = marimo.App(width="medium", app_title="Spot-Eignungs-Check")


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
    from datetime import datetime

    from energietools.capabilities.netz import default_network_fee_ct_kwh
    from energietools.capabilities.spot.data import load_epex_prices
    from energietools.tools.h0_profile import synthesize_h0_consumption
    from energietools.tools.spot_analysis import analyze_spot_tariff

    _ = booted
    return (
        analyze_spot_tariff,
        datetime,
        default_network_fee_ct_kwh,
        load_epex_prices,
        synthesize_h0_consumption,
    )


@app.cell
def _(mo):
    mo.md(
        """
        # ⚡ Spot-Eignungs-Check

        Dynamische (Spot-)Tarife folgen dem **Börsenstrompreis** Stunde für Stunde.
        Ob sie sich lohnen, hängt **an deinem Verbrauchsprofil**: Wer dann verbraucht,
        wenn Strom billig ist, gewinnt — wer abends seine Lastspitze hat, eher nicht.
        Der **Profilkostenfaktor** macht genau das messbar.

        > Backtest gegen den gebündelten **EPEX-AT-Snapshot 2025** (8.760 Stunden), im
        > Browser auf [`energietools`](https://github.com/BMoer/energietools) gerechnet.
        > Ohne Smart-Meter-Daten wird ein **H0-Standardlastprofil** synthetisiert — eine
        > faire Näherung, **keine Prognose** künftiger Preise.
        """
    )
    return


@app.cell
def _(mo):
    verbrauch = mo.ui.slider(
        start=1000, stop=12000, step=100, value=3500,
        label="**Jahresverbrauch** (kWh)", show_value=True,
    )
    fixpreis = mo.ui.slider(
        start=15.0, stop=45.0, step=0.5, value=30.0,
        label="**Dein aktueller Fix-Tarif** (all-in brutto ct/kWh)", show_value=True,
    )
    aufschlag = mo.ui.number(
        start=0.0, stop=6.0, step=0.1, value=1.5,
        label="Spot-Aufschlag Lieferant (netto ct/kWh)",
    )
    controls = mo.vstack([verbrauch, fixpreis, aufschlag])
    controls
    return aufschlag, fixpreis, verbrauch


@app.cell
def _(
    analyze_spot_tariff,
    aufschlag,
    datetime,
    default_network_fee_ct_kwh,
    fixpreis,
    load_epex_prices,
    mo,
    synthesize_h0_consumption,
    verbrauch,
):
    prices = [dict(p) for p in load_epex_prices()]
    cons = synthesize_h0_consumption(
        verbrauch.value, datetime(2025, 1, 1), datetime(2026, 1, 1)
    )
    netz_ct = default_network_fee_ct_kwh()
    res = analyze_spot_tariff(
        cons,
        spot_prices=prices,
        fix_preis_ct=fixpreis.value,
        aufschlag_ct=aufschlag.value,
        netz_ct=netz_ct,
    )

    def _eur(x):
        return f"{x:,.0f} €".replace(",", ".")

    ersparnis = res.ersparnis_vs_fix_eur
    pkf = res.profilkostenfaktor_pct
    if ersparnis > 50:
        kind, headline = "success", f"Spot lohnt sich — ca. **{_eur(ersparnis)}/Jahr** günstiger."
    elif ersparnis > 0:
        kind, headline = "info", f"Spot ist nur **{_eur(ersparnis)}/Jahr** günstiger — knapp, mit Preisrisiko."
    else:
        kind, headline = "warn", f"Fix ist für dich **{_eur(-ersparnis)}/Jahr** günstiger."

    stats = mo.hstack(
        [
            mo.stat(value=f"{pkf:+.1f} %", label="Profilkostenfaktor (− ist gut)", bordered=True),
            mo.stat(value=f"{res.avg_spot_volumengewichtet_ct:.2f} ct", label="dein volumengew. Spotpreis", bordered=True),
            mo.stat(value=f"{res.avg_spot_zeitgewichtet_ct:.2f} ct", label="Flachprofil-Schnitt (zeitgew.)", bordered=True),
            mo.stat(value=_eur(res.voll_kosten_eur), label="Spot all-in/Jahr", bordered=True),
            mo.stat(value=_eur(res.fix_kosten_eur), label="Fix all-in/Jahr", bordered=True),
        ],
        justify="start", gap=1, wrap=True,
    )

    pkf_erklaerung = (
        "Dein Profil liegt **über** dem Flachprofil-Schnitt — du verbrauchst eher in "
        "teuren Stunden (klassischer Abend-Peak)."
        if pkf > 0
        else "Dein Profil liegt **unter** dem Flachprofil-Schnitt — du verbrauchst eher in günstigen Stunden."
    )

    monate = "\n".join(
        f"| {m.monat} | {m.verbrauch_kwh:.0f} | {m.avg_spot_ct:.2f} | {m.voll_kosten_eur:.0f} € |"
        for m in res.monthly_breakdown
    )

    out = mo.vstack(
        [
            mo.callout(mo.md(headline), kind=kind),
            stats,
            mo.md(f"**Profilkostenfaktor {pkf:+.1f} %.** {pkf_erklaerung}"),
            mo.accordion(
                {
                    "📅 Monatliche Aufschlüsselung (Spot all-in)": mo.md(
                        "| Monat | kWh | ⌀ Spot ct/kWh | Spot all-in |\n|---|---|---|---|\n" + monate
                    )
                }
            ),
        ]
    )
    out
    return (netz_ct,)


@app.cell
def _(mo, netz_ct):
    import json
    from importlib import resources

    manifest = json.loads(
        resources.files("energietools.data.spot").joinpath("MANIFEST.json").read_text("utf-8")
    )
    mo.md(
        f"""
        ---
        <small>
        **Daten-Snapshot:** EPEX-AT Spotpreise **2025** (8.760 h, netto) · Netzanteil aus dem
        netz-Snapshot: **{netz_ct:.3f} ct/kWh** (Default-Netzbetreiber, gequellt)<br>
        **Provenance:** {manifest.get("provenance", "")}<br>
        **Lizenz:** {manifest.get("license", "MIT")} · {manifest.get("disclaimer", "")}<br>
        **Methode/Grenzen:** Backtest auf 2025-Preisen (keine Prognose); H0-Profil ist eine
        Näherung — mit echten Smart-Meter-Werten wird das Ergebnis schärfer. Lieferanten-Aufschlag
        & sonstige Abgaben sind vereinfachte Defaults dieses Modells.
        </small>
        """
    )
    return
