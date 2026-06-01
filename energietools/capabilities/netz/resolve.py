# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Auflösung von PLZ → VNB, Netzkosten und regionaler Verfügbarkeit (offline).

Spiegelt die Resolve-Logik aus dem gridbert-Netz-Subsystem, aber gegen die
publizierten JSON-Daten (``data/netz/``) statt ein gridbert-Registry — **ohne
Netzwerk, ohne externe Tarif-API**.

**FAIL-OPEN überall:** Wo Daten fehlen oder mehrdeutig sind, wird nie hart
ausgeschlossen — der Vergleich zeigt lieber einen Tarif (mit Netzkosten 0) als
ihn fälschlich zu unterdrücken.

Netzkosten-Formel (NE7-Haushalt, brutto = netto × 1,20):
    netto = (vnb_arbeitspreis + vnb_verlust
             + eag_fb_ap + eag_fb_verlust + elektrizitaetsabgabe_haushalt)
            × kwh / 100
            + vnb_pauschale + eag_foerderpauschale
Nur die drei VNB-Felder variieren je Netzbereich; die übrigen Anteile sind
bundesweite föderale Konstanten aus ``abgaben.json``.
"""

from __future__ import annotations

from energietools.capabilities.netz.data import (
    load_abgaben,
    load_netzkosten,
    load_plz_index,
)
from energietools.capabilities.netz.models import NetzkostenEntry, PlzInfo

_UST = 1.20


def plz_info(plz: str) -> PlzInfo | None:
    """PLZ-Info (Gemeinde + Bundesland) für eine PLZ — oder ``None``."""
    return load_plz_index().get(str(plz).strip())


def resolve_netzbetreiber(plz: str) -> NetzkostenEntry | None:
    """Findet den eindeutigen VNB für eine PLZ — oder ``None``.

    Logik: PLZ → Bundesland/Gemeinde. Aus den Netzkosten-Daten werden alle VNB
    im selben Bundesland gesucht, deren ``enclaves`` die Gemeinde NICHT enthalten.
    Genau ein Treffer → dieser VNB. Kein oder mehrere Treffer (mehrdeutig)
    → ``None``. Fail-open: unbekannte PLZ → ``None``.
    """
    info = plz_info(plz)
    if info is None:
        return None

    kandidaten = [
        nb
        for nb in load_netzkosten()
        if nb.bundesland == info.bundesland and info.gemeinde not in nb.enclaves
    ]
    if len(kandidaten) == 1:
        return kandidaten[0]
    return None  # keiner oder mehrdeutig → fail-open


def gebrauchsabgabe_rate(plz: str) -> float:
    """Gebrauchsabgabe-Satz für eine PLZ (Anteil, z.B. 0.07 = 7 %).

    Wertet die Regeln aus ``abgaben.json`` aus (Match auf Gemeinde und/oder
    Bundesland, erste greifende Regel gewinnt); greift keine Regel, gilt der
    Default. Fail-open: unbekannte/fehlende PLZ → 0.0 (nie hart ausschließen).
    """
    info = plz_info(plz)
    if info is None:
        return 0.0

    abgaben = load_abgaben()
    for regel in abgaben.gebrauchsabgabe_regeln:
        if _regel_trifft(regel.match, info):
            return regel.rate
    return abgaben.gebrauchsabgabe_default


def _regel_trifft(match: dict[str, object], info: PlzInfo) -> bool:
    """Prüft, ob eine Gebrauchsabgabe-Regel auf die PLZ-Info passt.

    Ein Match-Kriterium kann ein einzelner String oder eine Liste sein; alle
    angegebenen Kriterien müssen zutreffen (UND-Verknüpfung).
    """
    felder = {"gemeinde": info.gemeinde, "bundesland": info.bundesland}
    for feld, erwartet in match.items():
        ist = felder.get(feld)
        erlaubte = {erwartet} if isinstance(erwartet, str) else set(erwartet)  # type: ignore[arg-type]
        if ist not in erlaubte:
            return False
    return True


def netzkosten_brutto_eur(plz: str, kwh: float) -> tuple[float, str]:
    """Brutto-Netzkosten pro Jahr + VNB-Name für eine PLZ.

    Returns:
        ``(kosten_eur, netzbetreiber_name)``. Fail-open: kein VNB auflösbar
        → ``(0.0, "")`` (keine Regression im Vergleich).
    """
    nb = resolve_netzbetreiber(plz)
    if nb is None:
        return (0.0, "")

    abgaben = load_abgaben()
    arbeitspreis_ct = (
        nb.netznutzung_arbeitspreis_ct_kwh
        + nb.netzverlust_ct_kwh
        + abgaben.eag_foerderbeitrag_ap_ct_kwh
        + abgaben.eag_foerderbeitrag_verlust_ct_kwh
        + abgaben.elektrizitaetsabgabe_haushalt_ct_kwh
    )
    pauschale_eur = nb.netznutzung_pauschale_eur_jahr + abgaben.eag_foerderpauschale_eur_jahr
    netto = arbeitspreis_ct * kwh / 100.0 + pauschale_eur
    brutto = netto * _UST
    return (round(brutto, 2), nb.name)


def ist_verfuegbar(service_area: str | list[str], plz: str) -> bool:
    """Prüft, ob ein Tarif mit ``service_area`` an dieser PLZ verfügbar ist.

    - ``"AT"`` → bundesweit, immer ``True``.
    - sonst (Bundesland-String oder Liste): verfügbar, wenn das Bundesland der
      PLZ enthalten ist.

    Fail-open: unbekannte PLZ → ``True`` (lieber anzeigen als ausschließen).
    """
    if service_area == "AT":
        return True

    info = plz_info(plz)
    if info is None:
        return True  # fail-open: unbekannte PLZ nicht ausschließen

    erlaubte = {service_area} if isinstance(service_area, str) else set(service_area)
    return info.bundesland in erlaubte
