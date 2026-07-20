# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Capability-Hülle der Lastgang-Analysen (L.1 + L.2, WP2-L Durchstich 2).

Übersetzt die Rechen-Kerne (``signals.py``, ``trend.py``) + die PV-Guards
(``guards.py``) in die einheitliche ``Capability``-Oberfläche: JSON-Schema-
Eingabe, ok/error-Envelope, ``result_field_paths``/``_meta`` für den
Prozess-Linter (Spec §0.1). Alle vier Lastgang-Capabilities (L.1–L.4) leben
laut Spec §0.4 in dieser einen Datei — hier bislang L.1/L.2.

Rein stdlib — kein pandas/numpy nötig (anders als ``load_profile``), daher
kein Lazy-Import-Zwang für die Rechen-Kerne selbst.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from importlib import metadata
from typing import Any

from energietools.capabilities.base import Capability, CapabilityError
from energietools.capabilities.lastgang.granularitaet import ist_grobe_serie
from energietools.capabilities.lastgang.guards import apply_pv_guards, guard_rueckfragen
from energietools.capabilities.lastgang.models import (
    CalendarYoYModel,
    LastgangSignalsResult,
    LoadTrendResult,
    PerYearModel,
    RueckfrageModel,
    SpotBacktestBlock,
    SpotBacktestResult,
    TarifErsparnisBlock,
    WindowYoYModel,
)
from energietools.capabilities.lastgang.signals import (
    ELECTRIC_HEAT_RATIO,
    HIGH_BASE_W,
    MIDDAY_FENSTER_LABEL,
    NIGHT_FENSTER_LABEL,
    PV_DIP_RATIO,
    compute_signals,
    select_rueckfragen,
)
from energietools.capabilities.lastgang.spot import (
    DEFAULT_SPOT_AUFSCHLAG_CT,
    TarifErsparnisCore,
    compute_spot_backtest,
    extract_tarif_ersparnis,
)
from energietools.capabilities.lastgang.trend import (
    FULL_YEAR_DAY_THRESHOLD,
    MIN_TREND_FENSTER_TAGE,
    compute_load_trend,
)
from energietools.capabilities.tariff_compare.capability import TariffCompareCapability

_CONSUMPTION_SERIES = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "ts": {"type": "string", "description": "ISO-Zeitstempel des Slots"},
            "kwh": {"type": "number", "description": "Netzbezug/Verbrauch im Slot (kWh)"},
        },
        "required": ["ts", "kwh"],
    },
    "description": "15-min-Netzbezug/-Verbrauch: [{ts, kwh}, …]",
}

_SPOT_PRICE_SERIES = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "timestamp": {"type": "string", "description": "ISO-Zeitstempel der EPEX-Stunde"},
            "price_ct": {"type": "number", "description": "EPEX-Preis netto ct/kWh"},
        },
        "required": ["timestamp", "price_ct"],
    },
    "description": (
        "EPEX-Stundenreihe (netto ct/kWh), als Parameter hereingereicht — "
        "L.4.2, kein DB-/Netzzugriff im Rechen-Kern: [{timestamp, price_ct}, …]"
    ),
}

_NENNER = {
    "winter_summer_ratio": "Ø Sommertag-kWh (Juni–August)",
    "midday_dip_ratio": f"Median Nacht-Slot ({NIGHT_FENSTER_LABEL}, kWh/Slot)",
    "weekday_weekend_ratio": "Ø Wochenendtag-kWh (Sa/So)",
}

_CAVEAT_15MIN = (
    "Signale sind Hypothesen aus dem Q15-Muster (Heuristik, keine Beweise) — "
    "die Rückfragen lösen die Mehrdeutigkeit auf, nicht die Zahl allein."
)

# --- L.2 load_trend -----------------------------------------------------

_LEERER_LASTGANG_TREND_FEHLER = "Leerer Lastgang — kein Mehrjahres-Trend berechenbar."

_CAVEAT_TEILJAHR = (
    "Teiljahr-kWh nicht als Jahreswert hochrechnen — ein Teiljahr (z.B. 6 Monate) ist "
    "ohne Saisonalitäts-Korrektur kein halbes Jahresverbrauchs-Äquivalent."
)
_CAVEAT_FENSTER_YOY = (
    "Fenster-YoY (deckungsgleiche Monat/Tag/Std/Min-Slots) ist bei Teiljahren der "
    "einzige saubere Mehrjahresvergleich — ein reiner Kalenderjahr-Vergleich würde "
    "sonst ein Teiljahr gegen ein Volljahr stellen."
)

_TREND_NENNER = {
    "window_yoy.delta_pct": (
        "kWh_a der deckungsgleichen (Monat,Tag,Std,Min)-Slots (Fenster-Basisjahr)"
    ),
    "calendar_yoy.delta_pct": "kWh_a des vollen Kalender-Basisjahres",
    "trend_pct_pro_jahr": (
        "Median der delta_pct-Werte aus window_yoy MIT in_trend=true (Fallback: "
        "calendar_yoy, falls kein Fenster mit in_trend=true übrig)"
    ),
}


def _paket_version() -> str:
    try:
        return metadata.version("energietools")
    except metadata.PackageNotFoundError:
        return "dev"


def _zeitraum_aus_consumption(consumption: Any) -> str | None:
    """Bestes-Aufwand Datenstand aus der rohen Eingabe — nur stdlib (``_meta``
    darf keine schwereren Abhängigkeiten voraussetzen als ``_run``)."""
    if not isinstance(consumption, list) or not consumption:
        return None
    zeitstempel: list[datetime] = []
    for eintrag in consumption:
        roh = eintrag.get("ts") if isinstance(eintrag, dict) else None
        if not roh:
            continue
        try:
            zeitstempel.append(datetime.fromisoformat(str(roh)))
        except ValueError:
            continue  # ein einzelner kaputter Zeitstempel darf _meta nie kippen
    if not zeitstempel:
        return None
    return f"{min(zeitstempel).isoformat()}…{max(zeitstempel).isoformat()}"


def _zeitraum_aus_spot_prices(raw: Any) -> str | None:
    """Datenstand der ÜBERGEBENEN EPEX-Reihe (Muster ``SnapshotSpotPriceSource
    .meta``, WP2-S-Fund): ein Spot-Backtest ist nur so aktuell wie die
    hereingereichte ``spot_prices``-Serie — das Envelope-Meta macht diesen
    Datenstand sichtbar (min…max Zeitstempel), unabhängig vom Verbrauchsfenster."""
    if not isinstance(raw, list) or not raw:
        return None
    zeitstempel: list[datetime] = []
    for eintrag in raw:
        roh = eintrag.get("timestamp") if isinstance(eintrag, dict) else None
        if not roh:
            continue
        try:
            zeitstempel.append(datetime.fromisoformat(str(roh)))
        except ValueError:
            continue  # ein einzelner kaputter Zeitstempel darf _meta nie kippen
    if not zeitstempel:
        return None
    return f"{min(zeitstempel).isoformat()}…{max(zeitstempel).isoformat()}"


def _parse_consumption(raw: Any) -> list[tuple[datetime, float]]:
    """Validiert + parst die Pflicht-Eingabe ``consumption`` (Input-Validation
    an der Systemgrenze — nie auf ein rohes ``dict`` vertrauen)."""
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise CapabilityError("consumption muss eine Liste von {ts, kwh}-Objekten sein.")
    parsed: list[tuple[datetime, float]] = []
    for i, eintrag in enumerate(raw):
        if not isinstance(eintrag, dict) or "ts" not in eintrag or "kwh" not in eintrag:
            raise CapabilityError(f"consumption[{i}]: erwartet {{ts, kwh}}, erhalten {eintrag!r}.")
        try:
            ts = datetime.fromisoformat(str(eintrag["ts"]))
            kwh = float(eintrag["kwh"])
        except (TypeError, ValueError) as exc:
            raise CapabilityError(f"consumption[{i}]: ungültiger ts/kwh-Wert ({exc}).") from exc
        parsed.append((ts, kwh))
    return parsed


def _consumption_zu_timestamp_records(parsed: list[tuple[datetime, float]]) -> list[dict]:
    """Übersetzt die geparste ``(ts, kwh)``-Form ins Primitiv-Format, das
    ``compute_spot_effective``/``compute_annual_cost`` erwarten (``timestamp``-
    Schlüssel statt ``ts`` — L.4.2, ``spot_pricing.py:91-100``)."""
    return [{"timestamp": ts.isoformat(), "kwh": kwh} for ts, kwh in parsed]


def _parse_spot_prices(raw: Any) -> list[dict]:
    """Validiert + parst die Eingabe ``spot_prices`` (Input-Validation an der
    Systemgrenze — nie auf ein rohes ``dict`` vertrauen)."""
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise CapabilityError(
            "spot_prices muss eine Liste von {timestamp, price_ct}-Objekten sein."
        )
    parsed: list[dict] = []
    for i, eintrag in enumerate(raw):
        if not isinstance(eintrag, dict) or "timestamp" not in eintrag or "price_ct" not in eintrag:
            raise CapabilityError(
                f"spot_prices[{i}]: erwartet {{timestamp, price_ct}}, erhalten {eintrag!r}."
            )
        try:
            ts = datetime.fromisoformat(str(eintrag["timestamp"]))
            price_ct = float(eintrag["price_ct"])
        except (TypeError, ValueError) as exc:
            raise CapabilityError(
                f"spot_prices[{i}]: ungültiger timestamp/price_ct-Wert ({exc})."
            ) from exc
        parsed.append({"timestamp": ts.isoformat(), "price_ct": price_ct})
    return parsed


def _ist_pv(kwargs: dict[str, Any]) -> bool:
    """Konstruktions-Regel für ``is_pv`` (L.1.2): explizites Flag ODER eine
    positive Einspeise-Summe gilt als PV-Hinweis — die Capability vertraut dem
    Gateway-Flag nicht blind (s. Plausibilitäts-Check ``pv_flag_widerspruch``)."""
    feedin = kwargs.get("pv_feedin_kwh")
    return bool(kwargs.get("is_pv", False)) or (feedin is not None and float(feedin) > 0)


class LastgangSignalsCapability(Capability):
    """Ursachen-Hypothesen (Signale) + Rückfragen aus einem Verbrauchs-Lastgang.

    PV-bedingte Guards (L.1.4) entschärfen die False-Positives, die der
    Netzbezug bei Prosumern erzeugt (Ledger-F3/F14/F24) — nur bei ``is_pv``.
    """

    name = "lastgang_signals"
    summary = (
        "Leitet aus einem 15-min-Lastgang Ursachen-Hypothesen ab (elektrische "
        "Heizung, PV-Eigenverbrauch, Dauerläufer) und wählt die dazu passenden "
        "Rückfragen. Bei PV (is_pv=true) greifen Netzbezug-Guards (F24-"
        "False-Positive-Schutz)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "consumption": _CONSUMPTION_SERIES,
            "interval_minutes": {
                "type": "integer",
                "default": 15,
                "description": "Mess-Intervall in Minuten (Q15 = 15; >= 60 wird abgelehnt)",
            },
            "pv_feedin_kwh": {
                "type": "number",
                "description": "Einspeise-Summe (kWh), falls ein Einspeise-Zählpunkt vorhanden ist",
            },
            "is_pv": {
                "type": "boolean",
                "default": False,
                "description": (
                    "PV-Flag (aus Einspeise-Consent/ZP-Suffix …9901). Wird zusätzlich "
                    "gegen die Mittag/Nacht-Signatur geprüft (pv_flag_widerspruch)."
                ),
            },
            "grundlast_kw": {
                "type": "number",
                "description": (
                    "Optionale Grundlast(P15) aus load_profile — nur für den "
                    "PV-Artefakt-Hinweis (L.1.4c), fließt nicht in die Signale ein."
                ),
            },
        },
        "required": ["consumption"],
    }

    def result_field_paths(self) -> dict[str, str]:
        return {
            "electric_heating": "str",
            "pv_self_consumption": "str",
            "high_continuous_load": "str",
            "winter_summer_ratio": "number",
            "night_base_w": "number",
            "night_fenster": "str",
            "midday_dip_ratio": "number",
            "evening_peak_hour": "number",
            "weekday_weekend_ratio": "number",
            "pv_feedin_kwh": "number",
            "is_pv": "bool",
            "basis_label": "str",
            "electric_heating_guarded": "bool",
            "roh_ws_ratio": "number",
            "grundlast_p15_pv_artefakt": "bool",
            "pv_flag_widerspruch": "bool",
        }

    def _meta(self, **kwargs: Any) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "quelle": "Nutzer-Lastgang (consumption) — kein externer Datensatz",
            "snapshot_version": _paket_version(),
        }
        zeitraum = _zeitraum_aus_consumption(kwargs.get("consumption"))
        if zeitraum:
            meta["stand"] = zeitraum
        return meta

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        consumption = _parse_consumption(kwargs.get("consumption"))
        interval_minutes = int(kwargs.get("interval_minutes", 15) or 15)
        pv_feedin_kwh = kwargs.get("pv_feedin_kwh")
        grundlast_kw = kwargs.get("grundlast_kw")
        is_pv = _ist_pv(kwargs)

        signals = compute_signals(
            consumption, interval_minutes=interval_minutes, pv_feedin_kwh=pv_feedin_kwh
        )
        rueckfragen = select_rueckfragen(signals)
        guard = apply_pv_guards(signals, is_pv=is_pv, grundlast_kw=grundlast_kw)
        rueckfragen = guard_rueckfragen(rueckfragen, guard=guard)

        rechenweg = {
            "schwellen": {
                "electric_heat_winter_summer_ratio": ELECTRIC_HEAT_RATIO,
                "pv_dip_ratio": PV_DIP_RATIO,
                "high_base_w": HIGH_BASE_W,
            },
            "fenster": {
                "night": NIGHT_FENSTER_LABEL,
                "midday": MIDDAY_FENSTER_LABEL,
                "winter_monate": [12, 1, 2],
                "sommer_monate": [6, 7, 8],
            },
            "formeln": {
                "night_base_w": (
                    "round(median(night_kwh_slots) * (60/interval_minutes) * 1000)  [W]"
                ),
                "midday_dip_ratio": "median(midday_kwh_slots) / median(night_kwh_slots)",
                "winter_summer_ratio": "Ø Wintertag-kWh / Ø Sommertag-kWh",
                "weekday_weekend_ratio": "Ø Werktag-kWh / Ø Wochenendtag-kWh",
            },
            "interval_minutes": interval_minutes,
            "guards_aktiv": is_pv,
        }

        caveats = [_CAVEAT_15MIN, *guard.caveats]

        result = LastgangSignalsResult(
            electric_heating=guard.electric_heating.value,
            pv_self_consumption=signals.pv_self_consumption.value,
            high_continuous_load=signals.high_continuous_load.value,
            winter_summer_ratio=signals.winter_summer_ratio,
            night_base_w=signals.night_base_w,
            night_fenster=NIGHT_FENSTER_LABEL,
            midday_dip_ratio=signals.midday_dip_ratio,
            evening_peak_hour=signals.evening_peak_hour,
            weekday_weekend_ratio=signals.weekday_weekend_ratio,
            pv_feedin_kwh=signals.pv_feedin_kwh,
            is_pv=is_pv,
            basis_label=guard.basis_label,
            electric_heating_guarded=guard.electric_heating_guarded,
            roh_ws_ratio=guard.roh_ws_ratio,
            grundlast_p15_pv_artefakt=guard.grundlast_p15_pv_artefakt,
            pv_flag_widerspruch=guard.pv_flag_widerspruch,
            rueckfragen=[
                RueckfrageModel(feld=f.feld, frage=f.frage, motiviert_durch=f.motiviert_durch)
                for f in rueckfragen
            ],
            rechenweg=rechenweg,
            caveats=caveats,
            nenner=dict(_NENNER),
        )
        return result.model_dump(mode="json")


class LoadTrendCapability(Capability):
    """Mehrjahres-Trend (YoY) eines Verbrauchs-Lastgangs mit Coverage-Guard (L.2).

    Ein echter Kalenderjahres-Vergleich braucht zwei VOLLE Jahre (>=360
    abgedeckte Tage) — sonst wäre er ein Teiljahr-gegen-Volljahr-Vergleich.
    Ohne diese Coverage weicht die Capability auf eine Fenster-YoY aus:
    deckungsgleiche (Monat,Tag,Std,Min)-Slots, die in beiden Jahren
    existieren. Aus den Delta-Werten leitet sie eine deterministische
    Trend-Aussage ab (F12, kein LLM).
    """

    name = "load_trend"
    summary = (
        "Mehrjahres-Trend (YoY) aus einem Verbrauchs-Lastgang. Kalender-YoY nur "
        "bei >=2 vollen Kalenderjahren (Coverage-Guard); sonst Fenster-YoY über "
        "deckungsgleiche (Monat,Tag,Std,Min)-Slots. Liefert eine deterministische "
        "Trend-Aussage ('Verbrauch steigt ~X %/Jahr')."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "consumption": _CONSUMPTION_SERIES,
        },
        "required": ["consumption"],
    }

    def result_field_paths(self) -> dict[str, str]:
        return {
            "trend_aussage": "str",
            "trend_pct_pro_jahr": "number",
            "calendar_yoy_verweigert_grund": "str",
            "calendar_yoy.von_jahr": "number",
            "calendar_yoy.bis_jahr": "number",
            "calendar_yoy.delta_pct": "number",
        }

    def _meta(self, **kwargs: Any) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "quelle": "Nutzer-Lastgang (consumption) — kein externer Datensatz",
            "snapshot_version": _paket_version(),
        }
        zeitraum = _zeitraum_aus_consumption(kwargs.get("consumption"))
        if zeitraum:
            meta["stand"] = zeitraum
        return meta

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        consumption = _parse_consumption(kwargs.get("consumption"))
        if not consumption:
            raise CapabilityError(_LEERER_LASTGANG_TREND_FEHLER)

        trend = compute_load_trend(consumption)

        rechenweg = {
            "full_year_threshold_tage": FULL_YEAR_DAY_THRESHOLD,
            "abgedeckte_tage_definition": (
                "len(set(dt.date())) je Kalenderjahr — Slot-Anzahl zählt NICHT als "
                "Tage (F11: ein unterjähriges Q15-Opt-in hat viele Slots, aber wenige Tage)"
            ),
            "kalender_yoy_regel": (
                "NUR wenn >=2 volle Kalenderjahre vorliegen; nimmt die letzten "
                "zwei vollen Jahre (delta_pct = 100*(kwh_b/kwh_a - 1))"
            ),
            "fenster_methode": (
                "deckungsgleiche (Monat,Tag,Std,Min)-Slots, die in beiden Jahren "
                "vorkommen, je benachbartem Jahrespaar (_aligned_window_yoy)"
            ),
            "min_fenster_tage": MIN_TREND_FENSTER_TAGE,
            "min_fenster_tage_regel": (
                "Fenster mit gemeinsame_tage < min_fenster_tage bekommen "
                "in_trend=false (+ grund) und fließen NICHT in den Median — "
                "Korrektheits-Fix: ein Fenster mit nur 1-2 gemeinsamen Slots "
                "(z.B. Jahreswechsel-Grenzslot) lieferte sonst eine beliebige "
                "delta_pct-Zahl, die den Median verzerrt"
            ),
            "trend_aussage_methode": (
                "Median der delta_pct-Werte aus window_yoy MIT in_trend=true "
                "(Fallback: calendar_yoy, falls kein Fenster übrig); kein LLM. "
                "Bleibt kein Fenster + keine calendar_yoy übrig: ehrliche "
                "'zu wenig Deckung'-Aussage statt Wert"
            ),
        }

        caveats = [_CAVEAT_TEILJAHR, _CAVEAT_FENSTER_YOY]

        result = LoadTrendResult(
            per_year=[
                PerYearModel(
                    jahr=j.jahr,
                    kwh=j.kwh,
                    slots=j.slots,
                    days=j.days,
                    full_year=j.full_year,
                    von=j.von,
                    bis=j.bis,
                )
                for j in trend.per_year
            ],
            calendar_yoy=(
                CalendarYoYModel(
                    von_jahr=trend.calendar_yoy.von_jahr,
                    bis_jahr=trend.calendar_yoy.bis_jahr,
                    kwh_a=trend.calendar_yoy.kwh_a,
                    kwh_b=trend.calendar_yoy.kwh_b,
                    delta_pct=trend.calendar_yoy.delta_pct,
                )
                if trend.calendar_yoy is not None
                else None
            ),
            calendar_yoy_verweigert_grund=trend.calendar_yoy_verweigert_grund,
            window_yoy=[
                WindowYoYModel(
                    von_jahr=w.von_jahr,
                    bis_jahr=w.bis_jahr,
                    gemeinsame_slots=w.gemeinsame_slots,
                    gemeinsame_tage=w.gemeinsame_tage,
                    kwh_a=w.kwh_a,
                    kwh_b=w.kwh_b,
                    delta_pct=w.delta_pct,
                    in_trend=w.in_trend,
                    grund=w.grund,
                )
                for w in trend.window_yoy
            ],
            trend_aussage=trend.trend_aussage,
            trend_pct_pro_jahr=trend.trend_pct_pro_jahr,
            rechenweg=rechenweg,
            caveats=caveats,
            nenner=dict(_TREND_NENNER),
        )
        return result.model_dump(mode="json")


# --- L.4 spot_backtest / tarif_ersparnis ---------------------------------

_CAVEAT_BACKTEST = (
    "spot_backtest ist ein Backtest auf historischen EPEX-Preisen — keine "
    "Prognose oder Preisgarantie für künftige Kosten."
)
_CAVEAT_AUFSCHLAG_ANNAHME = (
    f"aufschlag_ct ist eine Annahme (Default {DEFAULT_SPOT_AUFSCHLAG_CT:g} ct/kWh, "
    "keine Preisgarantie), sofern kein realer Lieferanten-Aufschlag übergeben wird."
)
_CAVEAT_TARIF_ERSPARNIS_ENERGIEBASIS = (
    "tarif_ersparnis.ist_eur/best_eur sind der Energiepreis-Anteil brutto/Jahr "
    "(Netzkosten/Gebrauchsabgabe eigene Blöcke in tariff_compare) — bei "
    "tarif_ersparnis.netzkosten_vollstaendig=false fehlt zusätzlich ein "
    "hinterlegter Netzbetreiber für diese PLZ."
)

# Granularitäts-Guard (F29 (a), Plan DURCHSTICH-2-PLAN.md §4 F29 + §2 WP2-P
# Punkt 5) — derselbe Laufzeit-Guard wie lastgang_signals (interval_minutes
# >=60 -> Ablehnung), hier aus den Timestamps der consumption-Serie
# abgeleitet (kein interval_minutes-Inputfeld auf spot_backtest). Blockiert
# die GESAMTE Capability (beide Blöcke, spot_backtest UND tarif_ersparnis) —
# anders als die block-lokalen "verfuegbar=False"-Gründe (fehlende optionale
# Felder), ist eine zu grobe Serie ein Datenqualitäts-Hard-Stop (Wortlaut-
# Anlehnung an signals._GRANULARITAET_FEHLER und
# prozesse/lastganganalyse.yaml:datenqualitaet_abbruch).
_GRANULARITAET_FEHLER_SPOT = (
    "spot_backtest braucht 15-min-Auflösung: der profilgewichtete Spot-Vergleich "
    "bepreist den ECHTEN Verbrauchs-Shape gegen die EPEX-Stundenpreise — bei "
    "Tageswerten verliert das jede Aussagekraft. Abgeleiteter Slot-Abstand "
    "≈{abstand:g} min (Tageswerte/grobe Serie) ist zu grob. Aktiviere den "
    "Viertelstundenwerte-Opt-in im Netzbetreiber-Portal (f_q15_optin) — erst mit "
    "Q15-Auflösung ist der profilgewichtete Spot-Vergleich möglich."
)

_SPOT_NENNER = {
    "spot_backtest.profilkostenfaktor_pct": (
        "zeitgewichteter Durchschnittspreis (ungewichtetes Stundenmittel der "
        "EPEX-Preise im überlappenden Zeitraum, OHNE Aufschlag)"
    ),
}

_TARIF_ERSPARNIS_PFLICHTFELDER = (
    "plz",
    "jahresverbrauch_kwh",
    "aktueller_lieferant",
    "energiepreis_brutto_ct_kwh",
    "aktuelle_grundgebuehr_brutto_eur_monat",
)


class SpotBacktestCapability(Capability):
    """Profilgewichteter Spot-Backtest + Tarifwechsel-Ersparnis aus dem Lastgang (L.4).

    Zwei Blöcke, JEDER für sich unabhängig optional (``verfuegbar=False`` +
    ``grund`` statt einer stillen 0, F8/L.6.2 — "NIE 0 zeigen"):

    - ``spot_backtest``: bepreist den ECHTEN Verbrauchs-Shape gegen
      historische EPEX-Stundenpreise (Backtest, keine Prognose) und stellt
      ihn dem aktuellen Fixpreis gegenüber. ``spot_prices``/``consumption``
      sind Parameter (L.4.2) — KEINE DB-/Netz-Abhängigkeit, dadurch offline
      testbar mit einer synthetischen EPEX-Reihe.
    - ``tarif_ersparnis``: eine dünne Sicht auf ``tariff_compare`` (offline
      über dessen ``TariffSource``-Protocol-Injection, Default
      ``CatalogTariffSource``) — die DB-gebundene gridbert-Quelle
      (``compare_from_db``) wird NICHT portiert (L.4.3).
    """

    name = "spot_backtest"
    summary = (
        "Profilgewichteter Spot-Backtest (echter Verbrauchs-Shape × EPEX-"
        "Stundenpreise) vs. aktueller Fixpreis, plus Tarifwechsel-Ersparnis "
        "aus dem Lastgang (dünne Sicht auf tariff_compare). Beide Blöcke "
        "unabhängig optional — 'verfuegbar=false' + 'grund' statt einer "
        "stillen 0, wenn die Datenlage fehlt."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "consumption": _CONSUMPTION_SERIES,
            "spot_prices": _SPOT_PRICE_SERIES,
            "energiepreis_brutto_ct_kwh": {
                "type": "number",
                "description": (
                    "Aktueller Arbeitspreis (Fixpreis), brutto ct/kWh — Vergleichs-"
                    "basis für spot_backtest UND aktueller Tarif für tarif_ersparnis."
                ),
            },
            "aufschlag_ct": {
                "type": "number",
                "default": DEFAULT_SPOT_AUFSCHLAG_CT,
                "description": (
                    "Angenommener Lieferanten-Aufschlag auf den EPEX-Spotpreis "
                    "(netto ct/kWh) — Annahme, keine Preisgarantie."
                ),
            },
            "plz": {
                "type": "string", "description": "Postleitzahl (4-stellig) — für tarif_ersparnis",
            },
            "jahresverbrauch_kwh": {
                "type": "number", "description": "Jahresverbrauch in kWh — für tarif_ersparnis",
            },
            "aktueller_lieferant": {
                "type": "string",
                "description": "Name des aktuellen Lieferanten — für tarif_ersparnis",
            },
            "aktuelle_grundgebuehr_brutto_eur_monat": {
                "type": "number",
                "description": "Aktuelle Grundgebühr brutto €/Monat — für tarif_ersparnis",
            },
        },
        "required": [],
    }

    def __init__(self, tariff_compare: TariffCompareCapability | None = None) -> None:
        # Konsumenten injizieren eine eigene TariffCompareCapability (z.B. mit
        # produktseitiger TariffSource); Standalone rechnet auf deren Default
        # (CatalogTariffSource, offline, gebündelter Open-Data-Snapshot).
        self._tariff_compare = tariff_compare or TariffCompareCapability()

    def result_field_paths(self) -> dict[str, str]:
        return {
            "spot_backtest.verfuegbar": "bool",
            "spot_backtest.grund": "str",
            "spot_backtest.differenz_eur": "number",
            "spot_backtest.effektiver_spot_ct": "number",
            "spot_backtest.profilkostenfaktor_pct": "number",
            "spot_backtest.aufschlag_ct": "number",
            "tarif_ersparnis.verfuegbar": "bool",
            "tarif_ersparnis.grund": "str",
            "tarif_ersparnis.ersparnis_eur": "number",
            "tarif_ersparnis.netzkosten_vollstaendig": "bool",
        }

    def _meta(self, **kwargs: Any) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "quelle": (
                "Nutzer-Lastgang + injizierte EPEX-Reihe (Parameter, L.4.2) — "
                "kein DB-/Netzzugriff im Rechen-Kern"
            ),
            "snapshot_version": _paket_version(),
        }
        # Datenstand der ÜBERGEBENEN Spot-Reihe (Muster SnapshotSpotPriceSource
        # .meta) — der Backtest ist nur so aktuell wie die hereingereichte EPEX-
        # Serie, unabhängig vom (ggf. längeren) Verbrauchsfenster.
        stand = _zeitraum_aus_spot_prices(kwargs.get("spot_prices"))
        if stand:
            meta["stand"] = stand
        return meta

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        consumption_roh = _parse_consumption(kwargs.get("consumption"))
        grob, abstand = ist_grobe_serie(ts for ts, _ in consumption_roh)
        if grob:
            raise CapabilityError(_GRANULARITAET_FEHLER_SPOT.format(abstand=abstand))
        consumption = _consumption_zu_timestamp_records(consumption_roh)
        spot_prices = _parse_spot_prices(kwargs.get("spot_prices"))
        aufschlag_roh = kwargs.get("aufschlag_ct")
        # `or` würde ein explizites 0.0 verschlucken — nur None fällt auf den Default.
        aufschlag_ct = (
            DEFAULT_SPOT_AUFSCHLAG_CT if aufschlag_roh is None else float(aufschlag_roh)
        )
        energiepreis_roh = kwargs.get("energiepreis_brutto_ct_kwh")
        energiepreis = float(energiepreis_roh) if energiepreis_roh is not None else None

        spot_core = compute_spot_backtest(
            consumption, spot_prices, energiepreis, aufschlag_ct=aufschlag_ct,
        )
        tarif_core = self._tarif_ersparnis_block(kwargs)

        rechenweg = {
            "spot_backtest": {
                "formel_effektiver_spot_ct": (
                    "volumengewichtetes EPEX-Stundenmittel (gewichtet mit dem "
                    "eigenen Verbrauchs-Shape) + aufschlag_ct"
                ),
                "formel_profilkostenfaktor_pct": (
                    "100 * (volumengewichteter_spot / zeitgewichteter_spot - 1)"
                ),
                "formel_fix_vergleich": (
                    "energiepreis_brutto_ct_kwh / 1.20 (USt) als konstanter "
                    "Arbeitspreis, über dieselbe Cost Engine UND dasselbe "
                    "EPEX-gedeckte Volumen wie Spot gerechnet (vergleichs_kwh, "
                    "vergleich_von/bis)"
                ),
                "aufschlag_ct_default": DEFAULT_SPOT_AUFSCHLAG_CT,
            },
            "tarif_ersparnis": {
                "methode": (
                    "dünne Sicht auf tariff_compare (top_n=1): ist_eur = "
                    "aktueller Tarif, best_eur = günstigste Alternative "
                    "(alternativen[0], nach jahreskosten_eur sortiert), "
                    "ersparnis_eur = tariff_compare.max_ersparnis_eur"
                ),
                "pflichtfelder": list(_TARIF_ERSPARNIS_PFLICHTFELDER),
            },
        }

        caveats = [
            _CAVEAT_BACKTEST,
            _CAVEAT_AUFSCHLAG_ANNAHME,
            _CAVEAT_TARIF_ERSPARNIS_ENERGIEBASIS,
        ]

        result = SpotBacktestResult(
            spot_backtest=SpotBacktestBlock(**dataclasses.asdict(spot_core)),
            tarif_ersparnis=TarifErsparnisBlock(**dataclasses.asdict(tarif_core)),
            rechenweg=rechenweg,
            caveats=caveats,
            nenner=dict(_SPOT_NENNER),
        )
        return result.model_dump(mode="json")

    def _tarif_ersparnis_block(self, kwargs: dict[str, Any]) -> TarifErsparnisCore:
        """Ruft ``tariff_compare`` auf (falls alle Pflichtfelder vorhanden) und
        extrahiert das ``tarif_ersparnis``-Ergebnis (L.4.3, dünne Sicht)."""
        werte = {
            "plz": kwargs.get("plz"),
            "jahresverbrauch_kwh": kwargs.get("jahresverbrauch_kwh"),
            "aktueller_lieferant": kwargs.get("aktueller_lieferant"),
            "energiepreis_brutto_ct_kwh": kwargs.get("energiepreis_brutto_ct_kwh"),
            "aktuelle_grundgebuehr_brutto_eur_monat": kwargs.get(
                "aktuelle_grundgebuehr_brutto_eur_monat"
            ),
        }
        fehlend = [feld for feld in _TARIF_ERSPARNIS_PFLICHTFELDER if werte[feld] in (None, "")]
        if fehlend:
            return TarifErsparnisCore(
                verfuegbar=False,
                grund=f"Fehlende Eingaben für tarif_ersparnis: {', '.join(fehlend)}.",
            )

        lieferant = str(werte["aktueller_lieferant"])
        vergleich = self._tariff_compare.run(
            plz=str(werte["plz"]),
            jahresverbrauch_kwh=werte["jahresverbrauch_kwh"],
            aktueller_lieferant=lieferant,
            aktueller_energiepreis_brutto_ct_kwh=werte["energiepreis_brutto_ct_kwh"],
            aktuelle_grundgebuehr_brutto_eur_monat=werte["aktuelle_grundgebuehr_brutto_eur_monat"],
            top_n=1,
        )
        return extract_tarif_ersparnis(
            ok=vergleich.ok, error=vergleich.error, data=vergleich.data,
            aktueller_lieferant=lieferant,
        )
