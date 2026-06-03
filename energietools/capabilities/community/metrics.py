# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Energiegemeinschafts-Kennzahlen (EEG/BEG) — deterministisch und auditierbar.

Standardmetriken einer Energiegemeinschaft, berechnet pro Zeitschlitz (z.B.
15-min) aus aggregierter Erzeugung und Verbrauch:

    intern_t    = min(gen_t, cons_t)         # gemeinschaftsintern gedeckt
    reststrom_t = max(0, cons_t - gen_t)     # Zukauf aus dem Netz
    ueberschuss = max(0, gen_t - cons_t)     # Einspeisung ins Netz

    SSR (Self-Sufficiency Rate) = Σ intern / Σ cons   (Autarkiegrad)
    SCR (Self-Consumption Rate) = Σ intern / Σ gen    (Eigenverbrauchsquote)

Reine Python-Berechnung (keine numpy/pandas-Abhängigkeit), damit jede Zahl von
Hand nachgerechnet werden kann.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from energietools.capabilities.base import CapabilityError


class CommunityMetrics(BaseModel):
    """Auditierbare Kennzahlen einer Energiegemeinschaft (Energie in kWh)."""

    slots: int = Field(description="Anzahl ausgewerteter Zeitschlitze")
    verbrauch_kwh: float = Field(description="Σ Verbrauch")
    erzeugung_kwh: float = Field(description="Σ Erzeugung")
    intern_gedeckt_kwh: float = Field(description="Σ min(gen, cons) — gemeinschaftsintern gedeckt")
    reststrom_kwh: float = Field(description="Σ max(0, cons − gen) — Netzbezug")
    ueberschuss_kwh: float = Field(description="Σ max(0, gen − cons) — Einspeisung")
    ssr_pct: float = Field(description="Self-Sufficiency Rate (Autarkiegrad) in %")
    scr_pct: float = Field(description="Self-Consumption Rate (Eigenverbrauchsquote) in %")


def community_metrics(
    erzeugung_kwh: list[float],
    verbrauch_kwh: list[float],
) -> CommunityMetrics:
    """Berechnet die EEG-Kennzahlen aus gleich langen Erzeugungs-/Verbrauchsreihen.

    Args:
        erzeugung_kwh: aggregierte Erzeugung pro Zeitschlitz (kWh).
        verbrauch_kwh: aggregierter Verbrauch pro Zeitschlitz (kWh).

    Raises:
        CapabilityError: bei ungleicher Länge, leerer Eingabe oder negativen Werten.
    """
    # Defensiv kopieren (akzeptiert auch Tupel/Generatoren, schützt vor Mutation).
    erzeugung_kwh = list(erzeugung_kwh)
    verbrauch_kwh = list(verbrauch_kwh)
    if not erzeugung_kwh or not verbrauch_kwh:
        raise CapabilityError("Erzeugungs- und Verbrauchsreihe dürfen nicht leer sein")
    if len(erzeugung_kwh) != len(verbrauch_kwh):
        raise CapabilityError(
            f"Reihen ungleich lang: {len(erzeugung_kwh)} (Erzeugung) "
            f"≠ {len(verbrauch_kwh)} (Verbrauch)",
        )
    if any(g < 0 for g in erzeugung_kwh) or any(c < 0 for c in verbrauch_kwh):
        raise CapabilityError("Negative Energiewerte sind nicht zulässig")

    total_gen = sum(erzeugung_kwh)
    total_cons = sum(verbrauch_kwh)
    intern = sum(min(g, c) for g, c in zip(erzeugung_kwh, verbrauch_kwh))
    reststrom = sum(max(0.0, c - g) for g, c in zip(erzeugung_kwh, verbrauch_kwh))
    ueberschuss = sum(max(0.0, g - c) for g, c in zip(erzeugung_kwh, verbrauch_kwh))

    ssr = (intern / total_cons * 100.0) if total_cons > 0 else 0.0
    scr = (intern / total_gen * 100.0) if total_gen > 0 else 0.0

    return CommunityMetrics(
        slots=len(verbrauch_kwh),
        verbrauch_kwh=round(total_cons, 3),
        erzeugung_kwh=round(total_gen, 3),
        intern_gedeckt_kwh=round(intern, 3),
        reststrom_kwh=round(reststrom, 3),
        ueberschuss_kwh=round(ueberschuss, 3),
        ssr_pct=round(ssr, 2),
        scr_pct=round(scr, 2),
    )
