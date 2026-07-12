# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Ergebnismodell der Trend-Attribution (L.3) — immutable, auditierbar.

Alle Modelle sind ``frozen``: ein berechnetes Result wird nie in-place mutiert.
Jede Anteils-Kennzahl (``delta_pct``) trägt ihre Nenner-Definition im
Result-``nenner`` (L.6), jedes Result Rechenweg + Caveats (L.6/Zielbild-3).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AttributionFenster(BaseModel):
    """Deckungsgleiches Vergleichsfenster beider Jahre (wie ``load_trend``)."""

    model_config = ConfigDict(frozen=True)

    von_jahr: int = Field(description="Basisjahr (jahr_a)")
    bis_jahr: int = Field(description="Vergleichsjahr (jahr_b)")
    gemeinsame_slots: int = Field(
        description="Anzahl (Monat,Tag,Std,Min)-Slots, die in BEIDEN Jahren existieren"
    )
    gemeinsame_tage: float = Field(description="gemeinsame_slots ÷ 96 (Slots/Tag)")


class ZerlegungsZelle(BaseModel):
    """Eine (Leistungsband × Tageszeit × Werktag/Wochenende)-Zelle der YoY-Zerlegung."""

    model_config = ConfigDict(frozen=True)

    band_kw: str = Field(description="Leistungsband, z.B. '1–4 kW'")
    tageszeit: str = Field(description="nacht | vormittag | tag | abend")
    werktag: bool = Field(description="True = Mo–Fr, False = Sa/So")
    kwh_a: float = Field(description="kWh-Summe der Zelle im Basisjahr (deckungsgleiches Fenster)")
    kwh_b: float = Field(description="kWh-Summe der Zelle im Vergleichsjahr")
    delta_kwh: float = Field(description="kwh_b − kwh_a (Beitrag der Zelle zum YoY-Delta)")
    delta_pct: float | None = Field(
        default=None, description="100·(kwh_b/kwh_a − 1); None, wenn kwh_a = 0"
    )


class Treiber(BaseModel):
    """Eine belegte Treiber-Zelle mit Geräte-KLASSE als Hypothese (nie Gerätename)."""

    model_config = ConfigDict(frozen=True)

    geraete_klasse: str = Field(
        description="Geräte-KLASSE (Hypothese), z.B. 'Kochen/Küche (sustained)'"
    )
    band_kw: str = Field(description="Leistungsband der Zelle")
    tageszeit: str = Field(description="Tageszeit-Fenster der Zelle")
    werktag: bool = Field(description="Werktag (True) oder Wochenende (False)")
    delta_kwh: float = Field(description="kWh-Zuwachs dieser Zelle (jahr_a→jahr_b)")
    delta_pct: float | None = Field(default=None, description="Relativer Zuwachs; Nenner = kwh_a")
    konfidenz: str = Field(description="hoch | mittel | niedrig")
    beleg: str = Field(description="Belegende Zahlen (Δ kWh, Band, Fenster, kwh_a→kwh_b)")


class TrendAttributionResult(BaseModel):
    """Vollständiges Attribution-Result (Rechenweg + Caveats + Nenner IM Result)."""

    model_config = ConfigDict(frozen=True)

    fenster: AttributionFenster
    zerlegung: list[ZerlegungsZelle] = Field(
        description="Alle attribuierten Zellen, nach delta_kwh absteigend"
    )
    treiber: list[Treiber] = Field(
        description="Top-Zellen (größtes delta_kwh) mit Geräte-KLASSE-Hypothese"
    )
    # Bequem-Skalare für result_field_paths / Caveat-Trigger (L.6, Prozess-Linter).
    anzahl_zellen: int = Field(description="Anzahl attribuierter Zellen in zerlegung")
    anzahl_treiber: int = Field(description="Anzahl identifizierter Treiber")
    top_treiber_klasse: str | None = Field(
        default=None, description="Geräte-KLASSE des stärksten Treibers"
    )
    top_treiber_delta_kwh: float | None = Field(
        default=None, description="delta_kwh des stärksten Treibers"
    )
    rechenweg: dict[str, Any] = Field(description="Bänder, Tageszeit-Fenster, Methode, Konversion")
    caveats: list[str] = Field(description="F21 15-min-Grenze IMMER; 'Klasse ja, Name nein'")
    nenner: dict[str, str] = Field(description="Kennzahl-Name → Nenner-Definition (L.6)")
    grenzen: dict[str, Any] = Field(
        description="Auflösungsgrenzen: aufloesung_min=15, klasse_nicht_name=True"
    )
