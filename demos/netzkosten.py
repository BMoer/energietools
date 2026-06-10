# energietools demo — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT
"""Netzkosten-Lokalisator — PLZ + Verbrauch → regulierte Netzkosten mit Rechenweg.

Reine Browser-Demo (marimo/WASM): lädt ausschließlich die MIT-Library ``energietools``
und ihre gebündelten, datierten Daten-Snapshots. Kein Server, kein gridbert-Code.
Jede Zahl trägt ihren Rechenweg und die Quelle (Preisblatt-URL / Verordnung).
"""

import marimo

__generated_with = "0.23.9"
app = marimo.App(width="medium", app_title="Netzkosten-Lokalisator")


@app.cell
async def _():
    # WASM-Bootstrap: im Browser (Pyodide) energietools aus dem gebündelten Wheel laden.
    # Lokal (CPython) ist energietools bereits installiert → no-op.
    import sys

    booted = True
    if sys.platform == "emscripten":  # Pyodide
        import micropip

        # Ein einziges, gemeinsames Wheel liegt im Gallery-Root (/wheels/…). Die
        # root-relative URL wird gegen die Origin aufgelöst → funktioniert unter jedem
        # App-Unterpfad (localhost wie unter der eigenen Domain energietools.at).
        await micropip.install(["pydantic"])
        await micropip.install("/wheels/energietools-0.3.0-py3-none-any.whl", deps=False)
    return (booted,)


@app.cell
def _(booted):
    import marimo as mo

    _ = booted  # erzwingt: Bootstrap läuft zuerst
    return (mo,)


@app.cell
def _(booted):
    # Nur den netz-Pfad importieren — minimale Pyodide-Abhängigkeiten (pydantic).
    from energietools.capabilities.netz import (
        GesamtkostenCapability,
        NetzkostenCapability,
    )

    _ = booted
    return GesamtkostenCapability, NetzkostenCapability


@app.cell
def _(mo):
    mo.md(
        """
        # 🔌 Netzkosten-Lokalisator

        Was kostet dich das **Stromnetz** an deiner Adresse — und wie setzt sich diese Zahl
        zusammen? Der Netzanteil ist rund **ein Drittel** der Stromrechnung, ist reguliert
        und hängt am **Netzbetreiber deiner PLZ** (nicht am Stromlieferanten). Hier wird er
        PLZ-scharf aufgelöst und **lückenlos aufgeschlüsselt** — jede Komponente mit Quelle.

        > Läuft komplett in deinem Browser auf der Open-Source-Library
        > [`energietools`](https://github.com/BMoer/energietools). Kein Server, keine erfundenen Zahlen:
        > unbekannte PLZ liefern **kein** geschätztes Ergebnis, sondern einen ehrlichen Hinweis.
        """
    )
    return


@app.cell
def _(mo):
    plz = mo.ui.text(value="1010", label="**PLZ**", placeholder="z.B. 1010")
    verbrauch = mo.ui.slider(
        start=1000, stop=15000, step=100, value=3500,
        label="**Jahresverbrauch** (kWh)", show_value=True,
    )
    energiepreis = mo.ui.number(
        start=1.0, stop=80.0, step=0.1, value=9.5,
        label="Energiepreis netto (ct/kWh)",
    )
    grundgebuehr = mo.ui.number(
        start=0.0, stop=60.0, step=0.5, value=4.5,
        label="Grundgebühr netto (€/Monat)",
    )
    controls = mo.vstack(
        [
            mo.hstack([plz, verbrauch], justify="start", gap=2),
            mo.hstack([energiepreis, grundgebuehr], justify="start", gap=2),
        ]
    )
    controls
    return energiepreis, grundgebuehr, plz, verbrauch


@app.cell
def _(
    GesamtkostenCapability,
    NetzkostenCapability,
    energiepreis,
    grundgebuehr,
    mo,
    plz,
    verbrauch,
):
    netz = NetzkostenCapability().run(plz=plz.value, verbrauch_kwh=verbrauch.value)
    ges = GesamtkostenCapability().run(
        plz=plz.value,
        verbrauch_kwh=verbrauch.value,
        energiepreis_netto_ct_kwh=energiepreis.value,
        grundgebuehr_netto_eur_monat=grundgebuehr.value,
    )

    vnb = netz.data["netzbetreiber"] if netz.ok else None

    def _eur(x):
        return f"{x:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")

    if not vnb:
        out = mo.callout(
            mo.md(
                f"""
                **Für PLZ {plz.value} liegt (noch) kein eindeutiger Netzbereich im Open-Data-Snapshot.**

                Das passiert bei **geteilten PLZ** (mehrere Netzbetreiber an einer PLZ) oder bei
                Netzbereichen, die der Snapshot noch nicht abdeckt (aktuell **NE7-Haushalt**, 14
                Netzbereiche). energietools **schätzt dann bewusst nicht** — es gibt keine
                erfundene Zahl, sondern diesen Hinweis. Probier eine eindeutige PLZ wie
                **1010** (Wien), **8020** (Graz), **5020** (Salzburg) oder **3100** (St. Pölten).
                """
            ),
            kind="warn",
        )
    else:
        k = netz.data["rechenweg"]["komponenten"]
        g = ges.data["rechenweg"]
        zeilen = [
            ("Netznutzung Arbeitspreis", f'{k["netznutzung_arbeitspreis_ct_kwh"]} ct/kWh'),
            ("Netzverlust", f'{k["netzverlust_ct_kwh"]} ct/kWh'),
            ("EAG-Förderbeitrag (AP + Verlust)", f'{round(k["eag_foerderbeitrag_ap_ct_kwh"] + k["eag_foerderbeitrag_verlust_ct_kwh"], 3)} ct/kWh'),
            ("Elektrizitätsabgabe", f'{k["elektrizitaetsabgabe_haushalt_ct_kwh"]} ct/kWh'),
            ("**Arbeitspreis gesamt**", f'**{k["arbeitspreis_summe_ct_kwh"]} ct/kWh**'),
            ("Netznutzung Pauschale", _eur(k["netznutzung_pauschale_eur_jahr"]) + "/Jahr"),
            ("EAG-Förderpauschale", _eur(k["eag_foerderpauschale_eur_jahr"]) + "/Jahr"),
            ("Netto/Jahr", _eur(k["netto_eur_jahr"])),
            (f'USt ×{k["ust_faktor"]}', ""),
            ("**Netzkosten brutto/Jahr**", f'**{_eur(k["brutto_eur_jahr"])}**'),
        ]
        tabelle = "\n".join(f"| {a} | {b} |" for a, b in zeilen)

        # gesamtkosten_eur_jahr_brutto enthält den Netzanteil bereits — NICHT addieren.
        gesamt = ges.data["gesamtkosten_eur_jahr_brutto"]
        netz_anteil = (
            g["netzkosten_brutto_eur"] / gesamt * 100 if gesamt > 0 else 0
        )

        out = mo.vstack(
            [
                mo.hstack(
                    [
                        mo.stat(value=_eur(netz.data["netzkosten_eur_jahr_brutto"]), label=f"Netzkosten/Jahr · {vnb}", bordered=True),
                        mo.stat(value=_eur(gesamt), label="Gesamt-Stromkosten/Jahr (Energie+Netz+Abgaben+USt)", bordered=True),
                        mo.stat(value=f"{netz_anteil:.0f} %", label="Netzanteil an der Rechnung", bordered=True),
                    ],
                    justify="start",
                    gap=1,
                ),
                mo.md(f"### Rechenweg Netzkosten — {vnb}\n\n| Komponente | Wert |\n|---|---|\n{tabelle}"),
                mo.accordion(
                    {
                        "🔎 Rechenweg Gesamtkosten (Energie + Netz + Gebrauchsabgabe + USt)": mo.md(
                            f"""
                            | Block | Betrag |
                            |---|---|
                            | Energie netto | {_eur(g["energie_netto_eur"])} |
                            | Grundgebühr netto | {_eur(g["grund_netto_eur"])} |
                            | Energie brutto (×{g["ust_faktor"]}) | {_eur(g["energie_brutto_eur"])} |
                            | Gebrauchsabgabe (Rate {g["gebrauchsabgabe_rate"]}) | {_eur(g["gebrauchsabgabe_eur"])} |
                            | Netzkosten brutto | {_eur(g["netzkosten_brutto_eur"])} |
                            | **Gesamt brutto/Jahr** | **{_eur(gesamt)}** |
                            """
                        )
                    }
                ),
            ]
        )

    out
    return netz


@app.cell
def _(mo, netz):
    # Audit-Footer: Quelle + Gültigkeit + Provenance des Daten-Snapshots.
    import json
    from importlib import resources

    manifest = json.loads(
        resources.files("energietools.data.netz").joinpath("MANIFEST.json").read_text("utf-8")
    )
    quelle = netz.data.get("quelle") if netz.ok else ""
    gueltig = netz.data.get("gueltig_ab") if netz.ok else ""
    quelle_md = f"[offizielles Preisblatt / Verordnung]({quelle})" if quelle else "—"

    mo.md(
        f"""
        ---
        <small>
        **Daten-Snapshot:** netz · Stand je Eintrag · **gültig ab:** {gueltig or "—"} · **Quelle:** {quelle_md}<br>
        **Provenance:** {manifest.get("provenance", "")}<br>
        **Lizenz:** {manifest.get("license", "MIT")} · {manifest.get("disclaimer", "")}<br>
        Jede Zahl offline nachrechenbar: `python -m energietools netzkosten --json '{{"plz":"1010","verbrauch_kwh":3500}}'`
        </small>
        """
    )
    return


if __name__ == "__main__":
    app.run()
