# energietools demo — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT
"""Rechnungs-Röntgen — deine Stromrechnung in Energie / Netz / Abgaben / USt zerlegt.

Reine Browser-Demo (marimo/WASM). Manuelle Eingabe der Rechnungs-Eckwerte (kein
PDF-Upload/OCR in dieser Demo). Zerlegt die Gesamtkosten mit lückenlosem Rechenweg
und stellt deinen Tarif gegen die günstigsten Strom-Fixpreis-Tarife des Open-Data-Katalogs.
"""

import marimo

__generated_with = "0.23.9"
app = marimo.App(width="medium", app_title="Rechnungs-Röntgen")


@app.cell
async def _():
    import sys

    booted = True
    if sys.platform == "emscripten":
        import micropip

        # Gemeinsames Wheel im Gallery-Root; root-relative URL funktioniert unter
        # jedem App-Unterpfad (localhost wie energietools.at).
        await micropip.install(["pydantic"])
        await micropip.install("/wheels/energietools-0.3.0-py3-none-any.whl", deps=False)
    return (booted,)


@app.cell
def _(booted):
    import marimo as mo

    _ = booted
    return (mo,)


@app.cell
def _(booted):
    from energietools.capabilities.netz import GesamtkostenCapability, NetzkostenCapability
    from energietools.capabilities.tariffs import TariffCatalog, kosten_rechenweg

    _ = booted
    return GesamtkostenCapability, NetzkostenCapability, TariffCatalog, kosten_rechenweg


@app.cell
def _(mo):
    mo.md(
        """
        # 🧾 Rechnungs-Röntgen

        Eine Stromrechnung ist drei Rechnungen in einer: **Energie** (dein Lieferant),
        **Netz** (reguliert, dein Netzbetreiber), **Abgaben & Steuern** (Gebrauchsabgabe,
        Elektrizitätsabgabe, 20 % USt). Hier wird sie **lückenlos zerlegt** — und dein
        Tarif gegen die günstigsten **Strom-Fixpreis-Tarife** im Open-Data-Katalog gestellt.

        > Läuft im Browser auf [`energietools`](https://github.com/BMoer/energietools). Diese
        > Demo nutzt **manuelle Eingabe** der Rechnungs-Eckwerte — der automatische PDF-Scan
        > (`invoice_parser`) ist absichtlich nicht Teil dieser rein-deterministischen Demo.
        """
    )
    return


@app.cell
def _(mo):
    plz = mo.ui.text(value="1010", label="**PLZ**")
    verbrauch = mo.ui.slider(start=1000, stop=12000, step=100, value=3500, label="**Jahresverbrauch** (kWh)", show_value=True)
    energiepreis = mo.ui.number(start=1.0, stop=60.0, step=0.1, value=12.0, label="Dein **Energiepreis** netto (ct/kWh)")
    grundgebuehr = mo.ui.number(start=0.0, stop=40.0, step=0.5, value=5.0, label="Deine **Grundgebühr** netto (€/Monat)")
    nur_oeko = mo.ui.checkbox(value=False, label="nur Ökostrom im Vergleich")
    controls = mo.vstack(
        [
            mo.hstack([plz, verbrauch], justify="start", gap=2),
            mo.hstack([energiepreis, grundgebuehr], justify="start", gap=2),
            nur_oeko,
        ]
    )
    controls
    return energiepreis, grundgebuehr, nur_oeko, plz, verbrauch


@app.cell
def _(
    GesamtkostenCapability,
    NetzkostenCapability,
    TariffCatalog,
    energiepreis,
    grundgebuehr,
    kosten_rechenweg,
    mo,
    nur_oeko,
    plz,
    verbrauch,
):
    def _eur(x):
        return f"{x:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")

    ges = GesamtkostenCapability().run(
        plz=plz.value,
        verbrauch_kwh=verbrauch.value,
        energiepreis_netto_ct_kwh=energiepreis.value,
        grundgebuehr_netto_eur_monat=grundgebuehr.value,
    )
    netz_res = NetzkostenCapability().run(plz=plz.value, verbrauch_kwh=verbrauch.value)
    g = ges.data["rechenweg"]
    vnb = netz_res.data["netzbetreiber"]
    netz_eur = netz_res.data["netzkosten_eur_jahr_brutto"]
    gab_rate = g["gebrauchsabgabe_rate"]  # PLZ→Gebrauchsabgabe-Satz aus der gesamtkosten-Engine

    # Deine Rechnung mit DERSELBEN Engine bewerten wie die Vergleichstarife
    # (kosten_rechenweg + Netz) — sonst wäre der Vergleich inkonsistent.
    deine_rw = kosten_rechenweg(
        verbrauch_kwh=verbrauch.value,
        netto_ep_ct=energiepreis.value,
        netto_gg_eur_monat=grundgebuehr.value,
        gebrauchsabgabe_rate=gab_rate,
    )
    deine_gesamt = deine_rw.brutto_jahreskosten_eur + deine_rw.gebrauchsabgabe_eur + netz_eur

    # --- Tarif-Ranking: nur Strom-Fixpreis (Gas per Namensheuristik raus) ---
    def _is_strom(t):
        return "gas" not in t.tarif_name.lower() and "gas" not in t.lieferant.lower()

    cat = TariffCatalog.load()
    kandidaten = [
        t for t in cat.all()
        if _is_strom(t) and t.tariftyp == "Fixpreis" and t.energiepreis_ct_kwh > 0
        and (t.ist_oekostrom or not nur_oeko.value)
    ]
    ranking = []
    for t in kandidaten:
        rw = kosten_rechenweg(
            verbrauch_kwh=verbrauch.value,
            netto_ep_ct=t.energiepreis_ct_kwh,
            netto_gg_eur_monat=t.grundgebuehr_eur_monat,
            gebrauchsabgabe_rate=gab_rate,
            rabatt_ct_kwh=t.neukundenrabatt_ct_kwh,
            rabatt_pauschal_eur=t.neukundenrabatt_eur,
        )
        energie_brutto = rw.brutto_jahreskosten_eur + rw.gebrauchsabgabe_eur
        ranking.append((energie_brutto + netz_eur, t, energie_brutto))
    ranking.sort(key=lambda r: r[0])

    breakdown = mo.md(
        f"""
        ### Deine Rechnung — Rechenweg
        | Block | Betrag/Jahr |
        |---|---|
        | Energie netto ({energiepreis.value} ct/kWh × {verbrauch.value} kWh) | {_eur(deine_rw.netto_energie_eur)} |
        | Grundgebühr netto ({grundgebuehr.value} €/Monat × 12) | {_eur(deine_rw.netto_grund_eur)} |
        | USt (× 1,20) auf Energie + Grund | {_eur(deine_rw.ust_eur)} |
        | Energie + Grund brutto | {_eur(deine_rw.brutto_jahreskosten_eur)} |
        | Gebrauchsabgabe (Rate {gab_rate}) | {_eur(deine_rw.gebrauchsabgabe_eur)} |
        | Netzkosten brutto · {vnb or "PLZ nicht eindeutig"} | {_eur(netz_eur)} |
        | **Gesamt brutto/Jahr** | **{_eur(deine_gesamt)}** |
        """
    )

    if not ranking:
        vergleich = mo.callout(mo.md("Keine passenden Vergleichstarife (Filter zu eng?)."), kind="warn")
    else:
        guenstigster_total, gt, gt_energie = ranking[0]
        ersparnis = deine_gesamt - guenstigster_total
        zeilen = "\n".join(
            f'| {i+1} | {t.lieferant[:26]} · {t.tarif_name[:24]} | {_eur(total)} | {"✅" if t.ist_oekostrom else "—"} | {"⏳" if t.hat_bindung else "frei"} |'
            for i, (total, t, _e) in enumerate(ranking[:5])
        )
        spar_kind = "success" if ersparnis > 30 else "info"
        spar_txt = (
            f"Günstigster Strom-Fixpreis: **{gt.lieferant} · {gt.tarif_name}** — "
            f"**{_eur(guenstigster_total)}/Jahr**. Gegenüber deiner Rechnung: "
            + (f"**{_eur(ersparnis)}/Jahr sparen**." if ersparnis > 0 else "deine Rechnung ist bereits günstiger.")
        )
        vergleich = mo.vstack(
            [
                mo.callout(mo.md(spar_txt), kind=spar_kind),
                mo.md(
                    f"### Günstigste Strom-Fixpreis-Tarife ({len(ranking)} verglichen, PLZ {plz.value})\n"
                    "| # | Tarif | Gesamt/Jahr | Öko | Bindung |\n|---|---|---|---|---|\n" + zeilen
                ),
            ]
        )

    out = mo.vstack([breakdown, vergleich])
    out
    return (cat,)


@app.cell
def _(cat, mo):
    import json
    from importlib import resources

    manifest = json.loads(
        resources.files("energietools.data.tariffs").joinpath("MANIFEST.json").read_text("utf-8")
    )
    m = cat.manifest
    mo.md(
        f"""
        ---
        <small>
        **Daten-Snapshot:** Tarifkatalog v{getattr(m, "catalog_version", "?")} ·
        {getattr(m, "tariff_count", len(cat.all()))} Tarife · Netto-Listenpreise<br>
        **Provenance:** {manifest.get("provenance", "")}<br>
        **Lizenz:** {manifest.get("license", "MIT")} · {manifest.get("disclaimer", "")}<br>
        **Ehrliche Grenzen dieser Demo:** (1) der Open-Data-Katalog hat **kein Sparte-Feld** →
        Gas wird per **Namensheuristik** ausgeschlossen; (2) **Spot-/Floater-Tarife** werden nicht
        gerankt (brauchen eine eigene Spot-Rechnung → siehe Spot-Eignungs-Check); (3) keine
        Anbieter-Namensnormalisierung; (4) bei **geteilten PLZ** liefert das Netz fail-open kein
        Ergebnis statt einer erfundenen Zahl.
        </small>
        """
    )
    return
