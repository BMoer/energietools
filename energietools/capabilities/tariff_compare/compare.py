# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Vergleichs-Kern des Tarifvergleichs (B.1-Port aus dem Produkt).

Vergleicht einen aktuellen Tarif (Brutto-Rechnungswerte) gegen Tarif-Zeilen
einer :class:`TariffSource` (netto Listenpreise): Loop, Differenz, Ranking,
best-per-category. Die per-Szenario-KOSTEN-Mathematik (Energie inkl.
Rabatt/Spot + Gebrauchsabgabe + Netzkosten) kommt aus der EINEN auditierbaren
Kosten-Engine ``energietools.cost.gesamtkosten_szenario`` — jede €-Zahl trägt
ihren Rechenweg.

Schnitt (Durchstich 1, ARCHITECTURE-2.0 §3.2 B.1):
- Die VNB-Auflösung (Zählpunkt → VKZ → Netzbetreiber) bleibt beim Konsumenten;
  der Kern nimmt einen **vorgelösten** ``nb_key`` entgegen (``None`` → Auflösung
  über die PLZ in der Kosten-Engine).
- Die ``service_area``-Vorfilterung der Zeilen bleibt ebenfalls beim
  Konsumenten. Die Lieferanten-Regionalprüfung (``ist_lieferant_verfuegbar``,
  eigener Bestand dieses Toolkits) läuft hier — wie bisher im Produkt.
- Leerer Vergleich ist KEIN Fehler (eigener ok/leer-Vertrag, keine
  EControlUnavailableError-Back-Compat).

Netzkosten und Gebrauchsabgabe sind reguliert/anbieterunabhängig und fließen
NICHT in den Vergleich/das Ranking ein (eigene Blöcke im Ergebnis).
"""

from __future__ import annotations

import logging
from datetime import datetime

from energietools.capabilities.providers.abdeckung import (
    ist_lieferant_verfuegbar,
    versorger_abdeckung,
)
from energietools.capabilities.tariff_compare.protocols import SpotPriceSource, TariffSource
from energietools.cost import gesamtkosten_szenario
from energietools.models import (
    Rechenweg,
    RegionalAusgeschlossen,
    Tariff,
    TariffComparison,
    VersorgerAbdeckungBlock,
)

log = logging.getLogger(__name__)

_UST = 1.2
_NETZ_HINWEIS = (
    "Netzkosten und Gebrauchsabgabe sind reguliert/anbieterunabhängig und werden "
    "als eigene Blöcke ausgewiesen (nicht in den Energie-Jahreskosten enthalten)"
)


def _tariff_from_row(
    row: dict,
    jahresverbrauch_kwh: float,
    spot_prices: list[dict],
    plz: str,
    nb_key: str | None,
    *,
    mit_gebrauchsabgabe: bool = True,
    quelle: str = "extern",
) -> Tariff | None:
    """Baut einen gerechneten Tariff aus einer Tarif-Zeile (netto Listenpreise).

    Die Kosten (Energie inkl. Neukundenrabatt/Spot, Gebrauchsabgabe als eigener
    Block, Netzkosten) kommen aus der Kosten-Engine; ``nb_key`` ist der vom
    Konsumenten vorgelöste Netzbetreiber. ``mit_gebrauchsabgabe=False`` (Gas)
    nullt den GA-Block — die Strom-Gebrauchsabgabe gilt nicht für Gas. Returns
    ``None``, wenn der Tarif nicht rechenbar ist (Spot/Floater ohne EPEX-Daten).
    """
    res = gesamtkosten_szenario(
        plz=plz,
        verbrauch_kwh=jahresverbrauch_kwh,
        netto_ep_ct=float(row.get("energiepreis_ct_kwh") or 0.0),
        netto_gg_eur_monat=float(row.get("grundgebuehr_eur_monat") or 0.0),
        tariftyp=row.get("tariftyp", "Fixpreis"),
        spot_aufschlag_ct=float(row.get("spot_aufschlag_ct") or 0.0),
        neukundenrabatt_ct_kwh=float(row.get("neukundenrabatt_ct_kwh") or 0.0),
        neukundenrabatt_eur=float(row.get("neukundenrabatt_eur") or 0.0),
        spot_prices=spot_prices,
        nb_key=nb_key,
        quelle=quelle,
    )
    if res is None:
        return None

    gab_eur = res["gebrauchsabgabe_eur"] if mit_gebrauchsabgabe else 0.0
    rw_felder = {**res["rechenweg"].model_dump(), "hinweis": _NETZ_HINWEIS}
    if not mit_gebrauchsabgabe:
        rw_felder["gebrauchsabgabe_eur"] = 0.0
        rw_felder["gebrauchsabgabe_rate"] = 0.0
    rechenweg = Rechenweg(**rw_felder)

    return Tariff(
        lieferant=row["lieferant"],
        tarif_name=row["tarif_name"],
        energy_type=row.get("energy_type") or "POWER",
        energiepreis_ct_kwh=round(res["effektiver_ep_netto_ct"] * _UST, 2),
        grundgebuehr_eur_monat=round(rechenweg.grundgebuehr_netto_eur_monat * _UST, 2),
        jahreskosten_eur=res["jahreskosten_energie_brutto_eur"],
        gebrauchsabgabe_eur=gab_eur,
        ist_oekostrom=bool(row.get("ist_oekostrom")),
        ist_biogas=bool(row.get("ist_biogas")),
        tariftyp=row.get("tariftyp", "Fixpreis"),
        preismodell=row.get("tariftyp", ""),
        energiequellen_erneuerbar_pct=float(row.get("energiequellen_erneuerbar_pct") or 0.0),
        preisgarantie_monate=row.get("preisgarantie_monate"),
        hat_bindung=bool(row.get("hat_bindung")),
        preisanpassung=row.get("preisanpassung", ""),
        # Rabatt-Präsentation aus dem auditierbaren Rechenweg ableiten (brutto-Total).
        neukundenrabatt_eur=round(rechenweg.neukundenrabatt_netto_eur * _UST, 2),
        neukundenrabatt_ct_kwh=round(float(row.get("neukundenrabatt_ct_kwh") or 0.0), 4),
        neukundenrabatt_name=row.get("neukundenrabatt_name", ""),
        jahreskosten_ohne_rabatt_eur=round(rechenweg.netto_gesamt_eur * _UST, 2),
        wechsel_link=row.get("wechsel_link", ""),
        spot_aufschlag_ct=float(row.get("spot_aufschlag_ct") or 0.0),
        spot_index=row.get("spot_index", ""),
        # Zielgruppe: fail-closed — fehlt der Key (Bestandszeile), gilt "standard".
        zielgruppe=row.get("zielgruppe") or "standard",
        unterbrechbar=bool(row.get("unterbrechbar")),
        quelle=quelle,
        rechenweg=rechenweg,
    )


def _passt_zielgruppe(tarif_zielgruppe: str, gesucht: str) -> bool:
    """Trennt Standard- und Heizstrom-/WP-Vergleich strikt.

    Standard-Vergleich sieht NUR ``standard``-Tarife (fail-closed: unbekannte/
    leere Zielgruppe gilt als ``standard``). Heizstrom-Vergleich sieht NUR die
    Heizstrom-Gruppe. So können WP-Tarife den Standardvergleich nie verfälschen.
    """
    zg = tarif_zielgruppe or "standard"
    if gesucht == "standard":
        return zg == "standard"
    return zg in ("waermepumpe", "elektroheizung", "unterbrechbar")


def _aktueller_tarif(
    lieferant: str,
    energiepreis_brutto: float,
    grundgebuehr_brutto: float,
    verbrauch: float,
    plz: str,
    nb_key: str | None,
    *,
    mit_gebrauchsabgabe: bool = True,
) -> Tariff:
    """Aktueller Tarif aus den Brutto-Rechnungswerten — gleiche Kosten-Engine wie
    die Alternativen (netto eingespeist; Gebrauchsabgabe als eigener Block)."""
    res = gesamtkosten_szenario(
        plz=plz,
        verbrauch_kwh=verbrauch,
        netto_ep_ct=energiepreis_brutto / _UST,
        netto_gg_eur_monat=grundgebuehr_brutto / _UST,
        nb_key=nb_key,
        quelle="rechnung",
    )
    # Gas hat keine Strom-Gebrauchsabgabe: wie in ``_tariff_from_row`` müssen die
    # GA-Felder AUCH im Rechenweg genullt werden — sonst widerspricht der
    # auditierbare Rechenweg dem (korrekt genullten) ``gebrauchsabgabe_eur``-Feld
    # (No-LLM-Math: kein erfundener GA-Posten, Fund gridbert-Gegenlese).
    rechenweg = res["rechenweg"]
    if not mit_gebrauchsabgabe:
        rechenweg = rechenweg.model_copy(
            update={"gebrauchsabgabe_eur": 0.0, "gebrauchsabgabe_rate": 0.0},
        )
    return Tariff(
        lieferant=lieferant,
        tarif_name="Aktueller Tarif",
        energiepreis_ct_kwh=energiepreis_brutto,
        grundgebuehr_eur_monat=grundgebuehr_brutto,
        jahreskosten_eur=res["jahreskosten_energie_brutto_eur"],
        gebrauchsabgabe_eur=res["gebrauchsabgabe_eur"] if mit_gebrauchsabgabe else 0.0,
        rechenweg=rechenweg,
        quelle="rechnung",
    )


def _lade_spot_preise(spot_source: SpotPriceSource | None) -> list[dict]:
    """Lädt verfügbare EPEX-Stundenpreise (für Spot/Floater-Effektivpreis).

    Fail-open: keine Quelle / keine Daten / Fehler → leere Liste, Spot-Tarife
    entfallen dann aus dem Vergleich (werden nie mit 0 fehlbepreist).
    """
    if spot_source is None:
        return []
    try:
        years = spot_source.available_years()
        if not years:
            return []
        start = datetime(min(years), 1, 1)
        end = datetime(max(years) + 1, 1, 1)
        return spot_source.get_prices(start, end)
    except Exception as exc:  # EPEX optional — Spot-Tarife entfallen dann
        log.warning("EPEX-Preise nicht ladbar, Spot/Floater entfallen: %s", exc)
        return []


def _kategorie(tariff: Tariff) -> str:
    """Kategorie aus dem Tariftyp ableiten (fix | floater)."""
    typ = tariff.tariftyp.lower()
    if "float" in typ or "monat" in typ or "spot" in typ or "stunden" in typ:
        return "floater"
    return "fix"


def _abdeckungs_block(plz: str, rows: list[dict]) -> VersorgerAbdeckungBlock:
    """Abdeckungs-Output-Block (B.2) für die Vergleichs-PLZ.

    ``im_katalog_fehlend`` = an der PLZ verfügbare Lieferanten, die im
    verglichenen Katalog (den übergebenen Zeilen) KEINEN Tarif haben.
    """
    katalog_lieferanten = sorted(
        {str(r.get("lieferant") or "") for r in rows if r.get("lieferant")},
    )
    a = versorger_abdeckung(plz, katalog_lieferanten=katalog_lieferanten)
    im_katalog = set(a.im_katalog)
    return VersorgerAbdeckungBlock(
        verfuegbar=[v.brand for v in a.verfuegbar],
        nicht_verfuegbar=[
            RegionalAusgeschlossen(brand=v.brand, region=list(v.region))
            for v in a.nicht_verfuegbar
        ],
        im_katalog_fehlend=sorted(
            {v.brand for v in a.verfuegbar if v.brand not in im_katalog},
        ),
    )


def _enrich(comparison: TariffComparison) -> TariffComparison:
    """Ersparnis, Gesamtkosten, Kategorien und Bestenlisten berechnen (immutabel).

    ``gesamtkosten = Energie (jahreskosten) + Netzkosten + Gebrauchsabgabe`` —
    die GAB ist per-Tarif, aber NICHT in ``jahreskosten_eur`` (reine Energie).
    ``ersparnis`` bleibt auf Energiebasis (Netz+GAB ändern sich beim Wechsel
    praktisch nicht). Gibt eine NEUE Instanz zurück.
    """
    aktuell_kosten = comparison.aktueller_tarif.jahreskosten_eur
    netz = comparison.netzkosten_eur_jahr

    enriched: list[Tariff] = []
    for t in comparison.alternativen:
        enriched.append(Tariff(
            **{
                **t.model_dump(),
                "ersparnis_eur": round(aktuell_kosten - t.jahreskosten_eur, 2),
                "gesamtkosten_eur": round(
                    t.jahreskosten_eur + netz + t.gebrauchsabgabe_eur, 2,
                ),
                "kategorie": _kategorie(t),
            },
        ))

    fix_tarife = sorted(
        [t for t in enriched if t.kategorie == "fix"], key=lambda t: t.jahreskosten_eur,
    )
    floater_tarife = sorted(
        [t for t in enriched if t.kategorie == "floater"], key=lambda t: t.jahreskosten_eur,
    )
    # "Gruen" energieartübergreifend: Ökostrom (POWER) ODER Biogas (GAS).
    gruen_tarife = sorted(
        [t for t in enriched if t.ist_oekostrom or t.ist_biogas],
        key=lambda t: t.jahreskosten_eur,
    )
    bester = min(enriched, key=lambda t: t.jahreskosten_eur) if enriched else None

    aktuell_enriched = Tariff(
        **{
            **comparison.aktueller_tarif.model_dump(),
            "gesamtkosten_eur": round(
                aktuell_kosten + netz + comparison.aktueller_tarif.gebrauchsabgabe_eur, 2,
            ),
            "kategorie": "aktuell",
        },
    )

    return TariffComparison(
        aktueller_tarif=aktuell_enriched,
        alternativen=enriched,
        plz=comparison.plz,
        jahresverbrauch_kwh=comparison.jahresverbrauch_kwh,
        netzkosten_eur_jahr=netz,
        netzbetreiber=comparison.netzbetreiber,
        gebrauchsabgabe_rate=comparison.gebrauchsabgabe_rate,
        versorger_abdeckung=comparison.versorger_abdeckung,
        beste_fix=fix_tarife,
        beste_floater=floater_tarife,
        beste_gruen=gruen_tarife,
        bester_gesamt=bester,
        max_ersparnis_eur=round(aktuell_kosten - bester.jahreskosten_eur, 2) if bester else 0.0,
    )


def vergleiche_tarife(
    *,
    plz: str,
    jahresverbrauch_kwh: float,
    aktueller_lieferant: str,
    aktueller_energiepreis_brutto_ct_kwh: float,
    aktuelle_grundgebuehr_brutto_eur_monat: float,
    tariff_source: TariffSource,
    spot_source: SpotPriceSource | None = None,
    nb_key: str | None = None,
    energy_type: str = "POWER",
    zielgruppe: str = "standard",
    top_n: int = 100,
    quelle: str = "extern",
    mit_abdeckung: bool = True,
) -> TariffComparison:
    """Vergleicht den aktuellen Tarif gegen alle aktiven Tarife der Quelle.

    Alle ausgewiesenen Preise BRUTTO (inkl. 20 % USt); Netzkosten und
    Gebrauchsabgabe als eigene Blöcke. ``energy_type`` wählt die Energieart
    (POWER=Strom Default, GAS — Gas hat keine Strom-Gebrauchsabgabe).

    ``nb_key``: vom Konsumenten VORGELÖSTER Netzbetreiber-Schlüssel (z.B.
    VKZ-deterministisch aus dem Zählpunkt). ``None`` → PLZ-Auflösung in der
    Kosten-Engine. Die ``service_area``-Vorfilterung der Zeilen ist
    Konsumenten-Sache (Schnitt B.1).

    Leerer Vergleich (0 Alternativen) ist ein gültiges Ergebnis, kein Fehler.
    """
    rows = tariff_source.get_latest(status="active", energy_type=energy_type)
    spot_prices = _lade_spot_preise(spot_source)

    # Gas hat keine Strom-Gebrauchsabgabe → kein VNB durchreichen (wie im Produkt).
    mit_ga = energy_type == "POWER"
    nb_key = nb_key if mit_ga else None

    alternativen: list[Tariff] = []
    for row in rows:
        t = _tariff_from_row(
            row, jahresverbrauch_kwh, spot_prices, plz, nb_key,
            mit_gebrauchsabgabe=mit_ga, quelle=quelle,
        )
        if t and t.jahreskosten_eur > 0:
            alternativen.append(t)

    # Zielgruppen-Trennung (fail-closed) + Lieferanten-Regionalprüfung: ein
    # Landesversorger eines ANDEREN Bundeslandes wird ausgeschlossen — sonst
    # rankt er fälschlich als Bestpreis, obwohl dort nicht abschließbar.
    alternativen = [t for t in alternativen if _passt_zielgruppe(t.zielgruppe, zielgruppe)]
    alternativen = [t for t in alternativen if ist_lieferant_verfuegbar(t.lieferant, plz)]

    alternativen.sort(key=lambda t: t.jahreskosten_eur)
    alternativen = alternativen[:top_n]

    if not alternativen:
        log.warning("vergleiche_tarife: 0 aktive Tarife für PLZ=%s — leerer Vergleich", plz)

    # Netzkosten + GA-Anzeigesatz aus der Kosten-Engine (einmal, anbieterunabhängig).
    # Fail-open: nicht auflösbar → (0.0, "").
    ref = gesamtkosten_szenario(
        plz=plz, verbrauch_kwh=jahresverbrauch_kwh,
        netto_ep_ct=10.0, netto_gg_eur_monat=0.0, nb_key=nb_key,
    )
    netzkosten = ref["netzkosten_brutto_eur"] if mit_ga else 0.0
    netzbetreiber = (ref["netzbetreiber"] or "") if mit_ga else ""
    gab_rate = ref["gebrauchsabgabe_rate"] if mit_ga else 0.0

    # Abdeckungs-Block (B.2) — Abdeckungsdaten sind Strom-only.
    abdeckung = _abdeckungs_block(plz, rows) if (mit_abdeckung and mit_ga) else None

    comparison = TariffComparison(
        aktueller_tarif=_aktueller_tarif(
            aktueller_lieferant, aktueller_energiepreis_brutto_ct_kwh,
            aktuelle_grundgebuehr_brutto_eur_monat, jahresverbrauch_kwh, plz, nb_key,
            mit_gebrauchsabgabe=mit_ga,
        ),
        alternativen=alternativen,
        plz=plz,
        jahresverbrauch_kwh=jahresverbrauch_kwh,
        netzkosten_eur_jahr=round(netzkosten, 2),  # reguliert, anbieterunabhängig
        netzbetreiber=netzbetreiber,
        gebrauchsabgabe_rate=gab_rate,
        versorger_abdeckung=abdeckung,
    )
    return _enrich(comparison)
