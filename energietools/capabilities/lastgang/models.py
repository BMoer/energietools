# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Pydantic-Result-Modelle der Lastgang-Capabilities (L.1.7, L.2.4, L.4.4).

Typsicher + selbstdokumentierend (Schema-Doku über die Feldbeschreibungen).
``_run`` gibt jeweils ``…Result.model_dump(mode="json")`` zurück — siehe
Spec §0.2 (native ``Capability._run``-Rückgaben werden NICHT automatisch
normalisiert).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RueckfrageModel(BaseModel):
    """Eine signal-motivierte Rückfrage an den Haushalt (L.1.6)."""

    feld: str = Field(description="Datenmodell-Feld, das die Antwort befüllt")
    frage: str = Field(description="Die an den Haushalt gestellte Frage")
    motiviert_durch: str = Field(description="Welches Signal/Werte die Frage auslösen")


class LastgangSignalsResult(BaseModel):
    """Ergebnis von ``lastgang_signals`` (L.1) — Signale + Guards + Rückfragen.

    Jede Zahl trägt ihr Fenster/ihre Einheit als Begleitfeld (F7); jede
    Anteils-/Verhältnis-Kennzahl ihre Nenner-Definition in ``nenner`` (L.6).
    """

    # Signale (dreiwertig, str-Enum-Werte "likely"|"unlikely"|"unknown")
    electric_heating: str = Field(
        description="Elektrische Heizung wahrscheinlich? Bei PV-Guard ggf. auf "
        "'unknown' herabgestuft — siehe electric_heating_guarded/roh_ws_ratio."
    )
    pv_self_consumption: str = Field(description="PV-Eigenverbrauch wahrscheinlich?")
    high_continuous_load: str = Field(
        description="Dauerläufer (hohe Nacht-Grundlast) wahrscheinlich?"
    )

    # Rohkennzahlen MIT Fenster/Einheit (F7)
    winter_summer_ratio: float | None = Field(
        default=None, description="Ø Wintertag-kWh / Ø Sommertag-kWh"
    )
    night_base_w: int = Field(description="Median Nacht-Grundlast in Watt (Fenster: night_fenster)")
    night_fenster: str = Field(
        default="00:00–04:59", description="Fenster von night_base_w (F9-Entscheidung, L.1.5)"
    )
    midday_dip_ratio: float | None = Field(
        default=None,
        description="Median Mittag / Median Nacht (Fenster: midday_fenster im Rechenweg)",
    )
    evening_peak_hour: int = Field(description="Stunde (0-23) mit dem höchsten Ø-Bezug")
    weekday_weekend_ratio: float | None = Field(
        default=None, description="Ø Werktag-kWh / Ø Wochenendtag-kWh"
    )
    pv_feedin_kwh: float | None = Field(default=None, description="Eingespeiste Überschuss-Energie")

    # Guards (L.1.4)
    is_pv: bool = Field(description="PV-Flag der Eingabe (ggf. aus pv_feedin_kwh abgeleitet)")
    basis_label: str = Field(description="'Netzbezug' (is_pv=True) oder 'Verbrauch' (is_pv=False)")
    electric_heating_guarded: bool = Field(
        description="True, wenn ein LIKELY-Heizungssignal wegen PV auf 'unknown' herabgestuft wurde"
    )
    roh_ws_ratio: float | None = Field(
        default=None, description="Ungeguardetes winter_summer_ratio — nur gesetzt, wenn geguardet"
    )
    grundlast_p15_pv_artefakt: bool = Field(
        description="True, wenn eine übergebene grundlast_kw bei PV als Artefakt markiert wurde"
    )
    pv_flag_widerspruch: bool = Field(
        description="Warnfeld: Mittag > Nacht ist untypisch für PV-Bezug — kein Hard-Fail"
    )

    # Rückfragen (L.1.6)
    rueckfragen: list[RueckfrageModel] = Field(default_factory=list)

    # Rechenweg + Caveats (Zielbild-Prinzip 3)
    rechenweg: dict = Field(default_factory=dict, description="Schwellen, Fenster, Formeln")
    caveats: list[str] = Field(default_factory=list)
    nenner: dict[str, str] = Field(
        default_factory=dict, description="L.6: Nenner-Definition je Anteils-/Verhältnis-Kennzahl"
    )


class PerYearModel(BaseModel):
    """Kennzahlen EINES Kalenderjahres (L.2.3 — ``_per_year``-Port)."""

    jahr: int = Field(description="Kalenderjahr")
    kwh: float = Field(description="kWh-Summe des Jahres")
    slots: int = Field(description="Anzahl Messwerte (Slots) in diesem Jahr")
    days: int = Field(description="Anzahl verschiedener Kalendertage (nicht Slots, F11)")
    full_year: bool = Field(
        description=(
            "True, wenn days >= FULL_YEAR_DAY_THRESHOLD abgedeckte Tage "
            "(Coverage-Guard, Wert siehe rechenweg.full_year_threshold_tage)"
        )
    )
    von: str = Field(description="Erster abgedeckter Kalendertag (ISO-Datum)")
    bis: str = Field(description="Letzter abgedeckter Kalendertag (ISO-Datum)")


class CalendarYoYModel(BaseModel):
    """Echter Kalenderjahres-Vergleich — nur zwischen zwei VOLLEN Jahren (L.2.3)."""

    von_jahr: int
    bis_jahr: int
    kwh_a: float = Field(description="kWh-Summe des Basisjahres (von_jahr)")
    kwh_b: float = Field(description="kWh-Summe des Vergleichsjahres (bis_jahr)")
    delta_pct: float = Field(description="100 * (kwh_b/kwh_a - 1)")


class WindowYoYModel(BaseModel):
    """Fenster-YoY über deckungsgleiche (Monat,Tag,Std,Min)-Slots (L.2.3)."""

    von_jahr: int
    bis_jahr: int
    gemeinsame_slots: int = Field(description="Anzahl Slots, die in BEIDEN Jahren existieren")
    gemeinsame_tage: float = Field(
        description="gemeinsame_slots/96 (Q15-Annahme) — Diagnosezahl, kein Nenner"
    )
    kwh_a: float = Field(description="kWh-Summe des Basisjahres, NUR über die gemeinsamen Slots")
    kwh_b: float = Field(
        description="kWh-Summe des Vergleichsjahres, NUR über die gemeinsamen Slots"
    )
    delta_pct: float | None = Field(description="100 * (kwh_b/kwh_a - 1); None wenn kwh_a == 0")


class LoadTrendResult(BaseModel):
    """Ergebnis von ``load_trend`` (L.2) — Mehrjahres-Trend mit Coverage-Guard.

    Kalender-YoY NUR bei >=2 vollen Kalenderjahren (Coverage-Guard, DoD-
    Kriterium 5); sonst Fenster-YoY über deckungsgleiche (Monat,Tag,Std,Min)-
    Slots. ``trend_aussage``/``trend_pct_pro_jahr`` sind eine deterministische
    Ableitung (Median der Delta-Werte, F12) — kein LLM.
    """

    per_year: list[PerYearModel] = Field(default_factory=list)
    calendar_yoy: CalendarYoYModel | None = Field(
        default=None, description="Nur gesetzt bei >=2 vollen Kalenderjahren"
    )
    calendar_yoy_verweigert_grund: str | None = Field(
        default=None, description="DoD-5: Begründung, wenn calendar_yoy None ist"
    )
    window_yoy: list[WindowYoYModel] = Field(default_factory=list)
    trend_aussage: str | None = Field(
        default=None,
        description="F12: deterministische Formulierung, z.B. 'Verbrauch steigt ~10 %/Jahr.'",
    )
    trend_pct_pro_jahr: float | None = Field(
        default=None, description="Median der delta_pct-Werte (window_yoy, Fallback calendar_yoy)"
    )
    rechenweg: dict = Field(default_factory=dict, description="Schwellen, Fenster-Methode, Formeln")
    caveats: list[str] = Field(default_factory=list)
    nenner: dict[str, str] = Field(
        default_factory=dict, description="L.6: Nenner-Definition je Anteils-/Verhältnis-Kennzahl"
    )


class SpotBacktestBlock(BaseModel):
    """Profilgewichteter Spot-Backtest vs. aktueller Fixpreis (L.4.3).

    ``verfuegbar=False`` (statt einer stillen 0) mit ``grund``, wenn
    ``spot_prices``/``consumption``/``energiepreis_brutto_ct_kwh`` fehlen oder
    sich Verbrauch und Preise zeitlich nicht überlappen.
    """

    verfuegbar: bool = Field(description="False = nicht berechenbar — Begründung in 'grund', NIE 0")
    grund: str | None = Field(default=None, description="Begründung, wenn verfuegbar=False")
    spot_netto_eur: float | None = Field(
        default=None, description="Spot-Jahreskosten Energie, netto € (profilgewichtet)"
    )
    fix_netto_eur: float | None = Field(
        default=None, description="Fixpreis-Jahreskosten Energie, netto €"
    )
    differenz_eur: float | None = Field(
        default=None, description="fix_netto_eur - spot_netto_eur; positiv = Spot günstiger"
    )
    effektiver_spot_ct: float | None = Field(
        default=None,
        description=(
            "Volumengewichteter Spot-Mittelwert (eigener Profil-Shape) + "
            "aufschlag_ct, netto ct/kWh"
        ),
    )
    profilkostenfaktor_pct: float | None = Field(
        default=None,
        description=(
            "100 * (volumengewichteter Spot / zeitgewichteter Spot - 1) — wie teuer "
            "das EIGENE Verbrauchsprofil ggü. einem flachen (zeitgewichteten) Bezug ist"
        ),
    )
    aufschlag_ct: float = Field(
        description=(
            "Angenommener Lieferanten-Aufschlag auf den EPEX-Spotpreis (Annahme, "
            "keine Garantie)"
        )
    )
    basis: str | None = Field(
        default=None, description="'eigene Verbrauchsdaten' oder 'H0-Standardlastprofil'"
    )
    hinweis: str | None = Field(default=None, description="Backtest-Hinweis (keine Preisgarantie)")
    vergleichs_kwh: float | None = Field(
        default=None,
        description=(
            "kWh im Vergleichsfenster — BEIDE Seiten (fix/spot) rechnen über exakt "
            "die EPEX-gedeckten Verbrauchs-Slots (Volumen-Parität)"
        ),
    )
    vergleich_von: str | None = Field(
        default=None, description="Beginn des EPEX-gedeckten Vergleichsfensters (ISO)"
    )
    vergleich_bis: str | None = Field(
        default=None, description="Ende des EPEX-gedeckten Vergleichsfensters (ISO)"
    )


class TarifErsparnisBlock(BaseModel):
    """Tarifwechsel-Ersparnis — dünne Sicht auf ``tariff_compare`` (L.4.3).

    ``verfuegbar=False`` mit ``grund``, wenn Pflicht-Eingaben fehlen, der
    Tarifvergleich ablehnt, oder keine Alternative im Katalog existiert.
    """

    verfuegbar: bool = Field(description="False = nicht berechenbar — Begründung in 'grund', NIE 0")
    grund: str | None = Field(default=None, description="Begründung, wenn verfuegbar=False")
    ist_eur: float | None = Field(
        default=None, description="Aktueller Tarif, Energie-Jahreskosten brutto €"
    )
    best_eur: float | None = Field(
        default=None, description="Günstigste Markt-Alternative, Energie-Jahreskosten brutto €"
    )
    ersparnis_eur: float | None = Field(
        default=None, description="ist_eur - best_eur (= tariff_compare.max_ersparnis_eur)"
    )
    lieferant_ist: str | None = Field(default=None, description="Aktueller Lieferant (Eingabe)")
    lieferant_best: str | None = Field(
        default=None, description="Lieferant der günstigsten Alternative"
    )
    tarif_best: str | None = Field(
        default=None, description="Tarifname der günstigsten Alternative"
    )
    netzkosten_vollstaendig: bool | None = Field(
        default=None,
        description=(
            "False: ist_eur/best_eur enthalten NUR den Energiepreis-Anteil (kein "
            "hinterlegter Netzbetreiber in tariff_compare) — s. tariff_compare.ergebnis_typ"
        ),
    )
    basis: str | None = Field(default=None, description="Einordnung der €-Basis")


class SpotBacktestResult(BaseModel):
    """Ergebnis von ``spot_backtest`` (L.4) — Spot-Backtest + Tarif-Ersparnis.

    Zwei unabhängig optionale Blöcke (jeder für sich ``verfuegbar``/``grund``,
    NIE eine stille 0, F8/L.6.2). ``rechenweg``/``caveats``/``nenner`` auf
    Top-Level (Zielbild-Prinzip 3 + L.6.1).
    """

    spot_backtest: SpotBacktestBlock
    tarif_ersparnis: TarifErsparnisBlock
    rechenweg: dict = Field(default_factory=dict, description="Formeln je Block")
    caveats: list[str] = Field(default_factory=list)
    nenner: dict[str, str] = Field(
        default_factory=dict, description="L.6: Nenner-Definition je Anteils-/Verhältnis-Kennzahl"
    )
