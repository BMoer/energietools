# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Die zwei PV-Capabilities: ``pv_potenzial`` und ``speicher_dimensionierung``.

Beide rechnen auf dem ECHTEN Lastgang (Viertelstundenwerte) gegen ein
übergebenes Stundenprofil (PVGIS). Das Profil wird NICHT hier geholt — der
Konsument (Gateway) injiziert es, damit der Rechenkern ohne Netz auskommt und
offline testbar bleibt.

Keine erfundenen Annahmen: Preise, Investitionskosten, Nutzungsdauer und
Diskontrate sind Pflichteingaben (dieselbe Linie wie ``scenarios``). Was eine
Annahme ist (Einspeisevergütung), wird als Szenario-Band gerechnet und als
Annahme ausgewiesen — nicht als eine Zahl, die wie ein Messwert aussieht.
"""

from __future__ import annotations

from typing import Any

from energietools.capabilities.base import Capability, CapabilityError
from energietools.capabilities.finance.calculations import npv, simple_payback_years
from energietools.capabilities.pv.potenzial import (
    Bezugspreis,
    Lastreihe,
    PVBilanz,
    PVPotenzialFehler,
    bezugspreis,
    grenznutzen,
    jahresmodell,
    lastreihe_aus_messwerten,
    nutzen,
    pv_bilanz,
    tagessummen_aus_messwerten,
)
from energietools.capabilities.pv.profil import PVStundenprofil, profil_aus_stundenliste

_STUNDEN_PRO_JAHR = 8760.0

_PROFIL_SCHEMA = {
    "type": "array",
    "description": (
        "Stündliches PV-Ertragsprofil je kWp am Standort: "
        "[{monat, tag, stunde, kwh_pro_kwp}, …] (UTC, volles Jahr)"
    ),
    "items": {"type": "object"},
}
_MESSWERTE_SCHEMA = {
    "type": "array",
    "description": "Gemessener Verbrauch: [{timestamp, kwh, interval_minutes}, …]",
    "items": {"type": "object"},
}


def _zahl(kwargs: dict[str, Any], feld: str, *, positiv: bool = True) -> float:
    wert = kwargs.get(feld)
    if wert is None:
        raise CapabilityError(f"{feld} ist erforderlich (keine erfundenen Annahmen)")
    try:
        wert = float(wert)
    except (TypeError, ValueError) as exc:
        raise CapabilityError(f"{feld} muss eine Zahl sein") from exc
    if positiv and wert <= 0:
        raise CapabilityError(f"{feld} muss > 0 sein")
    return wert


def _liste(kwargs: dict[str, Any], feld: str) -> list[Any]:
    wert = kwargs.get(feld)
    if not isinstance(wert, list) or not wert:
        raise CapabilityError(f"{feld} muss eine nicht-leere Liste sein")
    return wert


def _profil(kwargs: dict[str, Any]) -> PVStundenprofil:
    try:
        return profil_aus_stundenliste(
            _liste(kwargs, "pv_profil"),
            lat=float(kwargs.get("lat") or 0.0),
            lon=float(kwargs.get("lon") or 0.0),
            neigung_grad=int(kwargs.get("neigung_grad") or 35),
            azimut_grad=int(kwargs.get("azimut_grad") or 0),
            quelle=str(kwargs.get("profil_quelle") or "uebergeben"),
            datensatz=str(kwargs.get("profil_datensatz") or ""),
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise CapabilityError(f"pv_profil unbrauchbar: {exc}") from exc


def _bilanz_dict(b: PVBilanz) -> dict[str, Any]:
    return {
        "kwp": b.kwp,
        "speicher_kwh": b.speicher_kwh,
        "verbrauch_kwh": b.verbrauch_kwh,
        "ertrag_kwh": b.ertrag_kwh,
        "eigenverbrauch_kwh": b.eigenverbrauch_kwh,
        "eigenverbrauch_direkt_kwh": b.eigenverbrauch_direkt_kwh,
        "eigenverbrauch_aus_speicher_kwh": b.eigenverbrauch_speicher_kwh,
        "einspeisung_kwh": b.einspeisung_kwh,
        "netzbezug_kwh": b.netzbezug_kwh,
        "eigenverbrauchsquote": b.eigenverbrauchsquote,
        "autarkiegrad": b.autarkiegrad,
        "speicher_vollzyklen": b.speicher_vollzyklen,
        "speicher_restfuellung_kwh": b.speicher_restfuellung_kwh,
        "speicher_verlust_kwh": b.speicher_verlust_kwh,
    }


def _reihen(kwargs: dict[str, Any]) -> tuple[Lastreihe, dict[str, Any]]:
    """Q15-Reihe + (falls Tagessummen reichen) das 365-Tage-Modell."""
    messwerte = _liste(kwargs, "consumption_data")
    q15 = [m for m in messwerte if int(m.get("interval_minutes") or 15) < 60]
    if not q15:
        raise CapabilityError(
            "Diese Serie enthält keine Viertelstundenwerte. Eine PV-Rechnung braucht "
            "den Tagesverlauf — aus Tagessummen ist nicht ablesbar, wie viel Strom "
            "gerade dann gebraucht wird, wenn die Sonne scheint."
        )
    try:
        reihe = lastreihe_aus_messwerten(q15)
    except PVPotenzialFehler as exc:
        raise CapabilityError(str(exc)) from exc

    modell_info: dict[str, Any] = {"verfuegbar": False}
    if kwargs.get("jahresmodell", True):
        try:
            tage = tagessummen_aus_messwerten(messwerte)
            jm = jahresmodell(reihe, tage)
        except PVPotenzialFehler as exc:
            modell_info = {"verfuegbar": False, "grund": str(exc)}
        else:
            modell_info = {
                "verfuegbar": True,
                "reihe": jm.reihe,
                "von": jm.von.isoformat(),
                "bis": jm.bis.isoformat(),
                "tage_mit_gemessener_tagessumme": jm.tage_mit_tagessumme,
                "muster_tage": jm.muster_tage,
                "muster_monate": list(jm.muster_monate),
                "deckt_sonnenhalbjahr": jm.deckt_sonnenhalbjahr,
            }
    return reihe, modell_info


def _modell_hinweis(info: dict[str, Any]) -> str:
    basis = (
        f"MODELL, keine Messung: {info['tage_mit_gemessener_tagessumme']} von 365 Tagen "
        f"({info['von']} bis {info['bis']}) haben eine echte Tagessumme; die Verteilung "
        f"über den Tag stammt vom jeweils ähnlichsten von {info['muster_tage']} "
        "gemessenen Viertelstunden-Tagen."
    )
    # Gemessen an einem echten Jahreslastgang (Wien, 2.030 kWh, 3-10 kWp): das
    # Modell traf den Eigenverbrauch auf 2-4 % genau, solange ein Mustertag aus
    # dem Sonnenhalbjahr dabei war — mit reinen Winter-Mustertagen lag es um bis
    # zu 15 % ZU HOCH. Mit Speicher blieb der Fehler in allen Fällen unter 1 %.
    if info.get("deckt_sonnenhalbjahr"):
        return (
            basis + " Die Mustertage decken auch das Sonnenhalbjahr ab; an einem echten "
            "Jahreslastgang lag der Modellfehler beim Eigenverbrauch in dieser "
            "Konstellation bei 2-4 %."
        )
    return (
        basis + " ACHTUNG: unter den Mustertagen ist KEIN Tag aus April bis September. "
        "An einem echten Jahreslastgang überschätzte das Modell den Eigenverbrauch "
        "dann um bis zu 15 % — die Anlage wird eher zu gut gerechnet. Für eine "
        "belastbare Zahl Viertelstundenwerte aus dem Sommerhalbjahr nachliefern."
    )


class PVPotenzialCapability(Capability):
    """Was eine PV-Anlage auf DIESEM Lastgang bringen würde."""

    name = "pv_potenzial"
    summary = (
        "PV-Potenzial auf dem echten Viertelstunden-Lastgang: Eigenverbrauchsquote, "
        "Autarkie, Einspeisung, vermiedene Netzkosten und Amortisation je Anlagengröße "
        "— gerechnet gegen das Sonnenertragsprofil des Standorts, nicht gegen ein "
        "Standardprofil."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "consumption_data": _MESSWERTE_SCHEMA,
            "pv_profil": _PROFIL_SCHEMA,
            "kwp_varianten": {
                "type": "array",
                "description": "Anlagengrößen in kWp, z.B. [5, 10, 15]",
                "items": {"type": "number"},
            },
            "speicher_kwh": {
                "type": "number",
                "description": "Speichergröße für die Zusatz-Variante (0 = ohne)",
            },
            "arbeitspreis_netto_ct_kwh": {
                "type": "number",
                "description": "Energie-Arbeitspreis des Kunden, netto ct/kWh",
            },
            "netz_arbeitsabhaengig_netto_ct_kwh": {
                "type": "number",
                "description": (
                    "Arbeitsabhängige Netz-/Abgabenbestandteile netto ct/kWh "
                    "(aus der netzkosten-Capability)"
                ),
            },
            "einspeise_szenarien_ct_kwh": {
                "type": "array",
                "description": "Annahme-Band für die Einspeisevergütung, netto ct/kWh",
                "items": {"type": "number"},
            },
            "investition_eur_pro_kwp": {
                "type": "object",
                "description": "Investition brutto EUR/kWp je Anlagengröße, z.B. {\"5\": 1650}",
            },
            "nutzungsdauer_jahre": {"type": "integer"},
            "diskontrate": {"type": "number", "description": "z.B. 0.04"},
            "jahresmodell": {
                "type": "boolean",
                "description": "Zusätzlich das 365-Tage-Modell rechnen (Default true)",
            },
        },
        "required": [
            "consumption_data",
            "pv_profil",
            "kwp_varianten",
            "arbeitspreis_netto_ct_kwh",
            "netz_arbeitsabhaengig_netto_ct_kwh",
            "einspeise_szenarien_ct_kwh",
        ],
    }

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        profil = _profil(kwargs)
        reihe, modell = _reihen(kwargs)
        kwps = [float(k) for k in _liste(kwargs, "kwp_varianten")]
        if any(k <= 0 for k in kwps):
            raise CapabilityError("kwp_varianten müssen > 0 sein")
        speicher = float(kwargs.get("speicher_kwh") or 0.0)
        szenarien = [float(s) for s in _liste(kwargs, "einspeise_szenarien_ct_kwh")]

        preis = bezugspreis(
            arbeitspreis_netto_ct_kwh=_zahl(kwargs, "arbeitspreis_netto_ct_kwh"),
            netz_arbeitsabhaengig_netto_ct_kwh=_zahl(
                kwargs, "netz_arbeitsabhaengig_netto_ct_kwh"
            ),
        )
        invest_je_kwp = kwargs.get("investition_eur_pro_kwp") or {}
        nutzungsdauer = int(kwargs.get("nutzungsdauer_jahre") or 0)
        diskontrate = kwargs.get("diskontrate")

        gemessen = self._varianten(
            reihe, profil, kwps, speicher, preis, szenarien,
            invest_je_kwp, nutzungsdauer, diskontrate,
        )
        ergebnis: dict[str, Any] = {
            "gemessen": {
                "von": reihe.zeitpunkte[0].isoformat(),
                "bis": reihe.zeitpunkte[-1].isoformat(),
                "stunden": round(reihe.stunden, 1),
                "tage": round(reihe.stunden / 24.0, 1),
                "slot_minuten": round(reihe.dt_hours * 60),
                "verbrauch_kwh": round(reihe.summe_kwh, 1),
                "varianten": gemessen,
                "hinweis": (
                    "Gemessener Zeitraum, nichts modelliert. Deckt weniger als ein "
                    "Jahr ab — NICHT hochgerechnet, weil ein Sommerfenster die "
                    "Jahresausbeute überschätzen und ein Winterfenster sie "
                    "unterschätzen würde."
                    if reihe.stunden < _STUNDEN_PRO_JAHR
                    else "Gemessener Zeitraum, nichts modelliert."
                ),
            },
            "bezugspreis": {
                "brutto_eur_kwh": preis.brutto_eur_kwh,
                "rechenweg": list(preis.rechenweg),
            },
            "annahmen": {
                "einspeise_szenarien_ct_kwh": szenarien,
                "einspeisung_ist_annahme": True,
                "pv_profil_quelle": profil.quelle,
                "pv_profil_datensatz": profil.datensatz,
                "pv_jahresertrag_kwh_pro_kwp": round(profil.jahresertrag_kwh_pro_kwp, 1),
                "neigung_grad": profil.neigung_grad,
                "azimut_grad": profil.azimut_grad,
                "speicher_kwh": speicher,
            },
        }

        if modell.get("verfuegbar"):
            jr: Lastreihe = modell["reihe"]
            ergebnis["jahr_modelliert"] = {
                "von": modell["von"],
                "bis": modell["bis"],
                "verbrauch_kwh": round(jr.summe_kwh, 1),
                "varianten": self._varianten(
                    jr, profil, kwps, speicher, preis, szenarien,
                    invest_je_kwp, nutzungsdauer, diskontrate,
                ),
                "ist_modell": True,
                "hinweis": _modell_hinweis(modell),
            }
        else:
            ergebnis["jahr_modelliert"] = {
                "verfuegbar": False,
                "grund": modell.get("grund", "nicht angefordert"),
            }
        return ergebnis

    def _varianten(
        self,
        reihe: Lastreihe,
        profil: PVStundenprofil,
        kwps: list[float],
        speicher: float,
        preis: Bezugspreis,
        szenarien: list[float],
        invest_je_kwp: dict[str, Any],
        nutzungsdauer: int,
        diskontrate: Any,
    ) -> list[dict[str, Any]]:
        jahresfaktor = _STUNDEN_PRO_JAHR / reihe.stunden if reihe.stunden > 0 else 1.0
        ist_jahr = abs(jahresfaktor - 1.0) < 0.05
        zeilen: list[dict[str, Any]] = []
        for kwp in kwps:
            for sp in dict.fromkeys([0.0, speicher] if speicher > 0 else [0.0]):
                bilanz = pv_bilanz(reihe, profil, kwp=kwp, speicher_kwh=sp)
                zeile = _bilanz_dict(bilanz)
                # Geld nur dort, wo der Zeitraum ein Jahr ist — sonst wäre die
                # Jahres-Hochrechnung eine saisonale Verzerrung mit Euro-Zeichen.
                if ist_jahr:
                    zeile["wirtschaftlichkeit"] = self._geld(
                        bilanz, preis, szenarien, kwp, invest_je_kwp,
                        nutzungsdauer, diskontrate,
                    )
                else:
                    zeile["wirtschaftlichkeit"] = {
                        "gerechnet": False,
                        "grund": (
                            f"Zeitraum deckt {reihe.stunden / 24:.0f} Tage ab, kein Jahr — "
                            "eine Hochrechnung auf 12 Monate wäre saisonal verzerrt."
                        ),
                    }
                zeilen.append(zeile)
        return zeilen

    def _geld(
        self,
        bilanz: PVBilanz,
        preis: Bezugspreis,
        szenarien: list[float],
        kwp: float,
        invest_je_kwp: dict[str, Any],
        nutzungsdauer: int,
        diskontrate: Any,
    ) -> dict[str, Any]:
        pro_kwp = invest_je_kwp.get(str(int(kwp))) or invest_je_kwp.get(str(kwp))
        invest = float(pro_kwp) * kwp if pro_kwp else None
        band: list[dict[str, Any]] = []
        for ct in szenarien:
            n = nutzen(bilanz, preis, einspeise_netto_ct_kwh=ct)
            eintrag: dict[str, Any] = {
                "einspeise_netto_ct_kwh": ct,
                "vermiedener_bezug_eur_jahr": n.vermiedener_bezug_eur,
                "einspeiseerloes_eur_jahr": n.einspeiseerloes_eur,
                "nutzen_eur_jahr": n.gesamt_eur,
                "rechenweg": list(n.rechenweg),
            }
            if invest and n.gesamt_eur > 0:
                jahre = simple_payback_years(invest, n.gesamt_eur)
                eintrag["amortisation_jahre"] = round(jahre, 1)
                if nutzungsdauer > 0 and diskontrate is not None:
                    eintrag["npv_eur"] = round(
                        npv(
                            total_investment_eur=invest,
                            annual_benefit_year1_eur=n.gesamt_eur,
                            lifetime_years=nutzungsdauer,
                            discount_rate=float(diskontrate),
                        ),
                        2,
                    )
            band.append(eintrag)
        return {
            "gerechnet": True,
            "investition_eur": round(invest, 2) if invest else None,
            "szenarien": band,
        }


class SpeicherDimensionierungCapability(Capability):
    """Wie groß der Speicher sein soll — und ab wann die nächste kWh nichts mehr bringt."""

    name = "speicher_dimensionierung"
    summary = (
        "Speicher-Größen-Sweep auf dem echten Lastgang mit PV: je Größe "
        "Eigenverbrauchsquote, Autarkie, Vollzyklen, Grenznutzen der nächsten kWh, "
        "Amortisation und Kapitalwert."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "consumption_data": _MESSWERTE_SCHEMA,
            "pv_profil": _PROFIL_SCHEMA,
            "kwp": {"type": "number", "description": "Anlagengröße in kWp"},
            "groessen_kwh": {
                "type": "array",
                "description": "Speichergrößen in kWh (0 wird immer mitgerechnet)",
                "items": {"type": "number"},
            },
            "arbeitspreis_netto_ct_kwh": {"type": "number"},
            "netz_arbeitsabhaengig_netto_ct_kwh": {"type": "number"},
            "einspeise_netto_ct_kwh": {
                "type": "number",
                "description": "Annahme Einspeisevergütung netto ct/kWh",
            },
            "speicher_kosten_eur_pro_kwh": {"type": "number"},
            "nutzungsdauer_jahre": {"type": "integer"},
            "diskontrate": {"type": "number"},
            "jahresmodell": {"type": "boolean"},
        },
        "required": [
            "consumption_data",
            "pv_profil",
            "kwp",
            "groessen_kwh",
            "arbeitspreis_netto_ct_kwh",
            "netz_arbeitsabhaengig_netto_ct_kwh",
            "einspeise_netto_ct_kwh",
            "speicher_kosten_eur_pro_kwh",
            "nutzungsdauer_jahre",
            "diskontrate",
        ],
    }

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        profil = _profil(kwargs)
        reihe, modell = _reihen(kwargs)
        kwp = _zahl(kwargs, "kwp")
        groessen = sorted({0.0, *(float(g) for g in _liste(kwargs, "groessen_kwh"))})
        if any(g < 0 for g in groessen):
            raise CapabilityError("groessen_kwh dürfen nicht negativ sein")

        preis = bezugspreis(
            arbeitspreis_netto_ct_kwh=_zahl(kwargs, "arbeitspreis_netto_ct_kwh"),
            netz_arbeitsabhaengig_netto_ct_kwh=_zahl(
                kwargs, "netz_arbeitsabhaengig_netto_ct_kwh"
            ),
        )
        einspeise = _zahl(kwargs, "einspeise_netto_ct_kwh", positiv=False)
        kosten_kwh = _zahl(kwargs, "speicher_kosten_eur_pro_kwh")
        nutzungsdauer = int(_zahl(kwargs, "nutzungsdauer_jahre"))
        diskontrate = _zahl(kwargs, "diskontrate", positiv=False)

        # Für die Wirtschaftlichkeit zählt ein volles Jahr. Liegt das Modell vor,
        # wird darauf gerechnet (und als Modell ausgewiesen); sonst nur physisch.
        rechenreihe = modell["reihe"] if modell.get("verfuegbar") else reihe
        auf_modell = bool(modell.get("verfuegbar"))

        zeilen: list[dict[str, Any]] = []
        nutzen_je_groesse: list[tuple[float, float]] = []
        basis_nutzen = None
        for g in groessen:
            bilanz = pv_bilanz(rechenreihe, profil, kwp=kwp, speicher_kwh=g)
            n = nutzen(bilanz, preis, einspeise_netto_ct_kwh=einspeise)
            if basis_nutzen is None:
                basis_nutzen = n.gesamt_eur
            invest = g * kosten_kwh
            mehrnutzen = n.gesamt_eur - basis_nutzen
            zeile = _bilanz_dict(bilanz)
            zeile.update(
                {
                    "nutzen_eur_jahr": n.gesamt_eur,
                    "mehrnutzen_gegenueber_ohne_speicher_eur_jahr": round(mehrnutzen, 2),
                    "investition_eur": round(invest, 2),
                    "rechenweg": list(n.rechenweg),
                }
            )
            if g > 0 and mehrnutzen > 0:
                zeile["amortisation_jahre"] = round(
                    simple_payback_years(invest, mehrnutzen), 1
                )
                zeile["npv_eur"] = round(
                    npv(
                        total_investment_eur=invest,
                        annual_benefit_year1_eur=mehrnutzen,
                        lifetime_years=nutzungsdauer,
                        discount_rate=diskontrate,
                    ),
                    2,
                )
            elif g > 0:
                zeile["amortisation_jahre"] = None
                zeile["npv_eur"] = round(-invest, 2)
            zeilen.append(zeile)
            nutzen_je_groesse.append((g, n.gesamt_eur))

        bewertbar = [z for z in zeilen if z["speicher_kwh"] > 0 and z.get("npv_eur") is not None]
        bestes = max(bewertbar, key=lambda z: z["npv_eur"]) if bewertbar else None
        lohnt_sich = bool(bestes and bestes["npv_eur"] > 0)

        return {
            "kwp": kwp,
            "groessen": zeilen,
            "grenznutzen": grenznutzen(nutzen_je_groesse),
            "bestes_szenario": bestes,
            "lohnt_sich": lohnt_sich,
            "befund": (
                f"Bester Kapitalwert bei {bestes['speicher_kwh']:g} kWh"
                f" ({bestes['npv_eur']:.0f} EUR über {nutzungsdauer} Jahre)."
                if lohnt_sich and bestes
                else (
                    "Keine der gerechneten Größen erreicht einen positiven Kapitalwert — "
                    "der Speicher verdient seine Anschaffung über die Nutzungsdauer nicht "
                    "zurück. Das ist ein Ergebnis, kein Fehler."
                )
            ),
            "basis": {
                "gerechnet_auf": "jahr_modelliert" if auf_modell else "gemessener_zeitraum",
                "ist_modell": auf_modell,
                "hinweis": (
                    _modell_hinweis(modell)
                    if auf_modell
                    else (
                        f"Gerechnet auf dem gemessenen Fenster ({reihe.stunden / 24:.0f} "
                        "Tage). Die Euro-Beträge gelten für diesen Zeitraum, nicht für ein Jahr."
                    )
                ),
                "verbrauch_kwh": round(rechenreihe.summe_kwh, 1),
            },
            "bezugspreis": {
                "brutto_eur_kwh": preis.brutto_eur_kwh,
                "rechenweg": list(preis.rechenweg),
            },
            "annahmen": {
                "einspeise_netto_ct_kwh": einspeise,
                "einspeisung_ist_annahme": True,
                "speicher_kosten_eur_pro_kwh": kosten_kwh,
                "nutzungsdauer_jahre": nutzungsdauer,
                "diskontrate": diskontrate,
                "pv_profil_quelle": profil.quelle,
                "pv_profil_datensatz": profil.datensatz,
                "alterung_beruecksichtigt": False,
            },
            "hinweis": (
                "Speicher-Alterung ist NICHT eingepreist. Bei hoher Zyklenzahl "
                "(Richtwert LFP ~6.000 Vollzyklen) verschiebt der Kapazitätsverlust die "
                "Amortisation nach hinten — die Vollzyklen je Größe stehen in der Tabelle."
            ),
        }


__all__ = ["PVPotenzialCapability", "SpeicherDimensionierungCapability"]
