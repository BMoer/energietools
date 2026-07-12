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

from datetime import datetime
from importlib import metadata
from typing import Any

from energietools.capabilities.base import Capability, CapabilityError
from energietools.capabilities.lastgang.guards import apply_pv_guards, guard_rueckfragen
from energietools.capabilities.lastgang.models import (
    CalendarYoYModel,
    LastgangSignalsResult,
    LoadTrendResult,
    PerYearModel,
    RueckfrageModel,
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
from energietools.capabilities.lastgang.trend import FULL_YEAR_DAY_THRESHOLD, compute_load_trend

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
        "Median der delta_pct-Werte aus window_yoy (Fallback: calendar_yoy, falls "
        "window_yoy leer)"
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
            "trend_aussage_methode": (
                "Median der window_yoy delta_pct-Werte (Fallback: calendar_yoy, "
                "falls window_yoy leer); kein LLM"
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
