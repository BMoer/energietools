# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""PVGIS-Stundenprofile holen (EU JRC, frei, ohne API-Key).

Die einzige Stelle im PV-Pfad, die ins Netz geht. Der Rechenkern
(``capabilities/pv``) sieht davon nichts — er bekommt ein fertiges
:class:`~energietools.capabilities.pv.profil.PVStundenprofil` injiziert.

Warum ``seriescalc`` und nicht ``PVcalc``: ``PVcalc`` liefert nur Monats-/
Jahressummen. Für die Deckung zwischen Erzeugung und Verbrauch braucht es den
**Tagesverlauf** — 8.760 Stundenwerte. Genau daran scheiterte die alte
Faustformel-Schätzung in ``tools/pv_sim.py``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from energietools.capabilities.pv.profil import PVStundenprofil, profil_aus_pvgis_hourly

log = logging.getLogger(__name__)

_BASIS_URL = "https://re.jrc.ec.europa.eu/api/v5_3/seriescalc"

#: Referenzjahr des Strahlungsdatensatzes. Fest verdrahtet, damit dieselbe
#: Anfrage morgen dasselbe Profil liefert — ein wanderndes „letztes Jahr" würde
#: Kundenzahlen still verschieben.
_REFERENZJAHR = 2020

#: Systemverluste in % (PVGIS-Default für Aufdach; Verkabelung, Wechselrichter,
#: Verschmutzung). Explizit, nicht versteckt.
STANDARD_SYSTEMVERLUSTE_PCT = 14.0


class PVGISFehler(RuntimeError):
    """PVGIS war nicht erreichbar oder hat keine brauchbaren Daten geliefert."""


@dataclass(frozen=True)
class PVGISQuelle:
    """:class:`~energietools.capabilities.pv.profil.PVProfileSource` gegen PVGIS.

    Bewusst ohne eigenen Cache: das Caching gehört zum Konsumenten (der weiß, wo
    er persistieren darf). Ein Aufruf dauert ~2-5 s und liefert ~800 KB.
    """

    timeout_s: float = 60.0
    systemverluste_pct: float = STANDARD_SYSTEMVERLUSTE_PCT
    referenzjahr: int = _REFERENZJAHR

    def hole(
        self, *, lat: float, lon: float, neigung_grad: int, azimut_grad: int
    ) -> PVStundenprofil:
        """Stundenprofil je kWp für den Standort (1 kWp angefragt, linear skalierbar)."""
        params = {
            "lat": lat,
            "lon": lon,
            "startyear": self.referenzjahr,
            "endyear": self.referenzjahr,
            "pvcalculation": 1,
            "peakpower": 1,
            "loss": self.systemverluste_pct,
            "angle": neigung_grad,
            "aspect": azimut_grad,
            "outputformat": "json",
            "browser": 0,
        }
        try:
            resp = httpx.get(_BASIS_URL, params=params, timeout=self.timeout_s)
            resp.raise_for_status()
            daten = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise PVGISFehler(f"PVGIS nicht erreichbar oder unlesbar: {exc}") from exc

        hourly = daten.get("outputs", {}).get("hourly")
        if not hourly:
            raise PVGISFehler("PVGIS-Antwort enthält keine Stundenwerte")

        meteo = daten.get("inputs", {}).get("meteo_data", {})
        datensatz = (
            f"{meteo.get('radiation_db', 'PVGIS')}/{meteo.get('meteo_db', '?')}"
            f" {self.referenzjahr}, Verluste {self.systemverluste_pct:.0f} %"
        )
        profil = profil_aus_pvgis_hourly(
            hourly,
            lat=lat,
            lon=lon,
            neigung_grad=neigung_grad,
            azimut_grad=azimut_grad,
            datensatz=datensatz,
        )
        log.info(
            "PVGIS-Profil geholt: %.4f/%.4f, %d Grad/%d Grad, %.0f kWh je kWp",
            lat, lon, neigung_grad, azimut_grad, profil.jahresertrag_kwh_pro_kwp,
        )
        return profil


def profil_als_stundenliste(profil: PVStundenprofil) -> list[dict[str, float]]:
    """Profil → die Transportform der Capability (``pv_profil``-Eingabe)."""
    return [
        {"monat": m, "tag": t, "stunde": h, "kwh_pro_kwp": round(v, 6)}
        for (m, t, h), v in sorted(profil.werte.items())
    ]


__all__ = ["PVGISFehler", "PVGISQuelle", "STANDARD_SYSTEMVERLUSTE_PCT", "profil_als_stundenliste"]
