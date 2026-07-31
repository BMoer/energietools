# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""PV-Ertragsprofil — stündlicher Ertrag je kWp für einen Standort.

Das Profil ist die *einzige* Zutat, die die PV-Rechnung von außen braucht und
nicht aus den Messdaten des Haushalts kommt. Es ist bewusst als **Protocol**
modelliert (storage-blind, analog ``TariffSource``): energietools rechnet, der
Konsument (gridbert-Gateway) injiziert eine PVGIS-gestützte Implementierung mit
Cache. So bleibt der Rechenkern offline testbar und ohne Netzzugriff.

Konvention
----------
Ein Profilwert ist der **mittlere Ertrag einer vollen Stunde in kWh je kWp**
(= kW im Stundenmittel). Der Schlüssel ist ``(monat, tag, stunde)`` in **UTC** —
dieselbe Zeitbasis, in der die Messwerte gespeichert sind. Ein Jahr ist damit
kalenderlos: dasselbe Profil passt auf jedes Messjahr, ein Schaltjahr-29.02.
fällt auf den 28.02. zurück.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

_STUNDEN_PRO_JAHR = 8760

#: Ausrichtung → PVGIS-Azimut (0 = Süd, negativ = Ost, positiv = West).
AUSRICHTUNG_AZIMUT: dict[str, int] = {
    "sued": 0,
    "suedost": -45,
    "suedwest": 45,
    "ost": -90,
    "west": 90,
    "nord": 180,
}


def azimut_aus_ausrichtung(ausrichtung: str) -> int:
    """``"Südwest"`` → ``45``. Wirft bei unbekannter Ausrichtung (kein stiller Default)."""
    key = (
        ausrichtung.strip()
        .lower()
        .replace("ü", "ue")
        .replace("ö", "oe")
        .replace("ä", "ae")
        .replace("-", "")
        .replace(" ", "")
    )
    if key not in AUSRICHTUNG_AZIMUT:
        erlaubt = ", ".join(sorted(AUSRICHTUNG_AZIMUT))
        raise ValueError(f"Unbekannte Ausrichtung {ausrichtung!r}; erlaubt: {erlaubt}")
    return AUSRICHTUNG_AZIMUT[key]


@dataclass(frozen=True)
class PVStundenprofil:
    """Stündlicher Ertrag je kWp (kWh) für einen Standort und eine Modulgeometrie."""

    werte: Mapping[tuple[int, int, int], float]
    lat: float
    lon: float
    neigung_grad: int
    azimut_grad: int
    quelle: str
    #: Strahlungsdatensatz/Jahr der Quelle — gehört in jeden Rechenweg, weil die
    #: Version das Ergebnis messbar verschiebt (SARAH2 ≠ SARAH3).
    datensatz: str = ""

    def __post_init__(self) -> None:
        if not self.werte:
            raise ValueError("PV-Profil ist leer")
        if any(v < 0 for v in self.werte.values()):
            raise ValueError("PV-Profil enthält negative Erträge")
        if len(self.werte) < _STUNDEN_PRO_JAHR:
            raise ValueError(
                f"PV-Profil hat nur {len(self.werte)} Stunden, erwartet mindestens "
                f"{_STUNDEN_PRO_JAHR} (ein volles Jahr) — eine Teilreihe würde die "
                "Jahresrechnung still verfälschen"
            )

    @property
    def jahresertrag_kwh_pro_kwp(self) -> float:
        """Summe über das Profiljahr (29.02. zählt mit, falls vorhanden)."""
        return sum(self.werte.values())

    def ertrag(self, zeitpunkt: datetime, kwp: float, dt_hours: float) -> float:
        """Ertrag (kWh) eines Intervalls der Länge ``dt_hours`` ab ``zeitpunkt``.

        Der Stundenwert ist ein Mittelwert — ein 15-min-Slot bekommt ein Viertel
        davon. Das glättet die PV innerhalb der Stunde; die Last behält ihre volle
        Auflösung. Die Richtung dieses Effekts ist gemessen (siehe
        ``tests/test_pv_potenzial.py::test_stundenglaettung_ueberschaetzt_nicht``).
        """
        key = (zeitpunkt.month, zeitpunkt.day, zeitpunkt.hour)
        wert = self.werte.get(key)
        if wert is None and key[:2] == (2, 29):
            wert = self.werte.get((2, 28, zeitpunkt.hour))
        return (wert or 0.0) * kwp * dt_hours


@runtime_checkable
class PVProfileSource(Protocol):
    """Quelle für Stundenprofile — injiziert vom Konsumenten, nicht hier gebaut."""

    def hole(
        self, *, lat: float, lon: float, neigung_grad: int, azimut_grad: int
    ) -> PVStundenprofil: ...


def profil_aus_pvgis_hourly(
    hourly: Iterable[Mapping[str, Any]],
    *,
    lat: float,
    lon: float,
    neigung_grad: int,
    azimut_grad: int,
    datensatz: str = "",
) -> PVStundenprofil:
    """PVGIS-``outputs.hourly`` → :class:`PVStundenprofil`.

    PVGIS liefert ``P`` in **W** je Stunde für die angefragte ``peakpower``; der
    Aufrufer fragt mit 1 kWp an, sodass ``P/1000`` direkt kWh je kWp ist. Der
    Zeitstempel (``YYYYMMDD:HHMM``) ist UTC; die Minuten (:10 bei PVGIS) werden
    verworfen, der Wert gilt für die volle Stunde.
    """
    werte: dict[tuple[int, int, int], float] = {}
    for eintrag in hourly:
        ts = datetime.strptime(str(eintrag["time"]), "%Y%m%d:%H%M")
        werte[(ts.month, ts.day, ts.hour)] = float(eintrag["P"]) / 1000.0
    return PVStundenprofil(
        werte=werte,
        lat=lat,
        lon=lon,
        neigung_grad=neigung_grad,
        azimut_grad=azimut_grad,
        quelle="pvgis",
        datensatz=datensatz,
    )


def profil_aus_stundenliste(
    eintraege: Iterable[Mapping[str, Any]],
    *,
    lat: float = 0.0,
    lon: float = 0.0,
    neigung_grad: int = 35,
    azimut_grad: int = 0,
    quelle: str = "uebergeben",
    datensatz: str = "",
) -> PVStundenprofil:
    """``[{monat, tag, stunde, kwh_pro_kwp}, …]`` → :class:`PVStundenprofil`.

    Das ist die Form, in der ein Konsument ein bereits geholtes/gecachtes Profil
    in die Capability reicht — ohne dass energietools selbst ins Netz muss.
    """
    werte: dict[tuple[int, int, int], float] = {}
    for e in eintraege:
        schluessel = (int(e["monat"]), int(e["tag"]), int(e["stunde"]))
        werte[schluessel] = float(e["kwh_pro_kwp"])
    return PVStundenprofil(
        werte=werte,
        lat=lat,
        lon=lon,
        neigung_grad=neigung_grad,
        azimut_grad=azimut_grad,
        quelle=quelle,
        datensatz=datensatz,
    )


__all__ = [
    "AUSRICHTUNG_AZIMUT",
    "PVProfileSource",
    "PVStundenprofil",
    "azimut_aus_ausrichtung",
    "profil_aus_pvgis_hourly",
    "profil_aus_stundenliste",
]
