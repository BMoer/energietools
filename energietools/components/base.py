# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Gemeinsame Schnittstelle der Simulationsbausteine (Schicht „Rechnen“).

Ein Energiesystem ist ein Baukasten aus *Komponenten* (PV, Batterie, E-Auto,
Wärmepumpe, Gaskessel). Jede Komponente ist ein Objekt mit beschriebenem
Verhalten und definierten Schnittstellen: **Energie rein/raus** an einem Bus und
ein **Zustand** (z.B. Ladezustand). Über diese Schnittstelle werden Komponenten
zu einem System verschaltet und der Energiefluss bilanziert (siehe ``system/``).

## Auflösung: diskret jetzt, Zeitreihe als Superset

v1 rechnet **diskret** — ein Aufruf von :meth:`Component.step` ist *ein* Intervall,
wie eine klassische Ingenieursrechnung. Entscheidend fürs Interface: **ein Skalar
ist ein Ein-Punkt-Profil.** Eine spätere Zeitreihen-Variante ist schlicht das
N-fache Durchlaufen von :meth:`step`, wobei der zurückgegebene (immutable) Zustand
weitergereicht wird — kein Rewrite, nur mehr Punkte. ``dt_hours`` im
:class:`StepContext` trägt die Intervalllänge (für einen Skalar: die Dauer der
betrachteten Periode).

## Vorzeichen-Konvention am elektrischen Bus

Pro Intervall meldet eine Komponente, wie viel Energie sie mit dem Bus austauscht:

- ``produced_kwh`` — Energie, die die Komponente **in den Bus speist**
  (PV-Ertrag, Batterie-Entladung).
- ``consumed_kwh`` — Energie, die die Komponente **aus dem Bus bezieht**
  (Last, Batterie-Ladung, E-Auto-Ladung).

Das System reicht den laufenden Überschuss (``surplus`` = bisher eingespeist −
bisher bezogen) durch die Komponenten in Prioritätsreihenfolge; was am Ende übrig
bleibt, ist Netzbezug (Überschuss < 0) bzw. Netzeinspeisung (Überschuss > 0).

## Immutabilität

Komponenten sind ``frozen`` Dataclasses. :meth:`step` **mutiert nichts**, sondern
gibt den Energieaustausch **und eine neue Komponenten-Instanz** mit fortge-
schriebenem Zustand zurück. So bleibt jeder Simulationsschritt nachvollziehbar.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

#: Komponenten-Arten. Bestimmen die Reihenfolge der Bilanzierung im System
#: (Quellen speisen ein, Lasten beziehen, Speicher reagieren auf den Rest).
KIND_SOURCE = "source"
KIND_LOAD = "load"
KIND_STORAGE = "storage"
KIND_CONVERTER = "converter"


@dataclass(frozen=True)
class StepContext:
    """Umgebung eines Simulationsschritts.

    ``dt_hours`` ist die Intervalllänge in Stunden (ein Skalar = ein Punkt über
    die betrachtete Periode). Weitere Umgebungssignale (Außentemperatur,
    Spotpreis …) werden hier ergänzt, wenn Komponenten sie brauchen — das Feld-Set
    ist bewusst erweiterbar, ohne die ``step``-Signatur zu ändern.
    """

    dt_hours: float = 1.0
    aussentemperatur_c: float | None = None
    spotpreis_ct_kwh: float | None = None


@dataclass(frozen=True)
class ComponentStep:
    """Energieaustausch einer Komponente mit dem elektrischen Bus in einem Intervall (kWh, ≥ 0).

    Siehe Vorzeichen-Konvention im Modul-Docstring. ``detail`` trägt optionale,
    auditierbare Zwischengrößen (z.B. SOC nach dem Schritt, COP), die das System
    in den Rechenweg übernehmen kann.
    """

    produced_kwh: float = 0.0
    consumed_kwh: float = 0.0
    detail: dict[str, float] | None = None

    @property
    def net_to_bus_kwh(self) -> float:
        """Netto in den Bus eingespeiste Energie (negativ = netto bezogen)."""
        return self.produced_kwh - self.consumed_kwh


class Component(ABC):
    """Basis eines verschaltbaren Energiebausteins (immutable).

    Subklassen setzen ``name`` und ``kind`` und implementieren :meth:`step`.
    ``step`` bekommt den **laufenden Bus-Überschuss** des Intervalls (kWh;
    > 0 = es steht Energie zur Verfügung, < 0 = es fehlt Energie) und den
    :class:`StepContext`, und liefert ``(ComponentStep, neue_komponente)``.

    Eine *Quelle* ignoriert den Überschuss und speist ihren Ertrag ein; eine
    *Last* bezieht ihren Bedarf; ein *Speicher* lädt aus positivem Überschuss
    bzw. entlädt in negativen Überschuss (Eigenverbrauchs-Logik).
    """

    name: str = ""
    kind: str = ""

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        # Abstrakte Zwischenklassen (step noch nicht implementiert) überspringen.
        if getattr(cls.step, "__isabstractmethod__", False):
            return
        if not cls.kind:
            raise TypeError(f"{cls.__name__}: Klassenattribut 'kind' fehlt")

    @abstractmethod
    def step(self, surplus_kwh: float, ctx: StepContext) -> tuple[ComponentStep, Component]:
        """Ein diskreter Schritt. Gibt Energieaustausch + fortgeschriebene Komponente zurück.

        Args:
            surplus_kwh: Laufender Überschuss am Bus vor dieser Komponente
                (> 0 = verfügbar, < 0 = fehlend).
            ctx: Schritt-Umgebung (Intervalllänge u.a.).
        """
