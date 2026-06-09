# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Auflösung von PLZ → VNB, Netzkosten und regionaler Verfügbarkeit (offline).

Löst PLZ → Netzbereich/Netzkosten gegen die publizierten JSON-Daten
(``data/netz/``) auf — **ohne Netzwerk, ohne externe Tarif-API**.

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

import re

from energietools.capabilities.netz.data import (
    load_abgaben,
    load_alle_vnb,
    load_netzkosten,
    load_plz_index,
)
from energietools.capabilities.netz.models import (
    GebrauchsabgabeRegelDetail,
    NetzkostenEntry,
    PlzInfo,
)

_UST = 1.20

# Rechtsform-/Füllwörter, die beim Namensvergleich ignoriert werden, damit
# "Stadtwerke Kapfenberg" und "Stadtwerke Kapfenberg GmbH" als gleich gelten.
_RECHTSFORM_TOKENS = frozenset({"gmbh", "ag", "kg", "co", "ges", "mbh", "gesmbh"})


def plz_info(plz: str) -> PlzInfo | None:
    """PLZ-Info (Gemeinde + Bundesland) für eine PLZ — oder ``None``."""
    return load_plz_index().get(str(plz).strip())


def resolve_netzbetreiber(plz: str) -> NetzkostenEntry | None:
    """Findet den VNB für eine PLZ — den **realen** Betreiber — oder ``None``.

    Zweistufig (Stadt-/Attributions-VNB haben Vorrang):

    1. **Inklusion:** Versorgt ein VNB die Gemeinde explizit
       (``gemeinde ∈ gemeinden``)? Genau ein Treffer → dieser VNB. Damit lösen
       Stadt-Netzbereiche (Graz/Linz/…) und Attributions-VNB (Stadtwerke Kapfenberg)
       auf ihren realen Betreiber auf.
    2. **Exklusion:** Sonst der Landes-VNB (``gemeinden`` leer) im selben Bundesland,
       sofern die Gemeinde nicht in dessen ``enclaves`` steht.

    Der zurückgegebene Eintrag trägt den **realen Namen**; sein Tarif folgt ggf.
    ``tarif_referenz`` (siehe :func:`tarif_fuer`). Fail-open: unbekannte/mehrdeutige
    PLZ → ``None``.
    """
    info = plz_info(plz)
    if info is None:
        return None

    # Jede Gemeinde der PLZ einzeln (mit IHREM Bundesland) auflösen; nur wenn ALLE
    # auf denselben VNB zeigen, ist die PLZ eindeutig. Geteilte PLZ (mehrere VNB)
    # → fail-open None (lieber 0 Netzkosten als falscher VNB). 1:1 wie
    # gridbert.netz.resolve.resolve_netzbetreiber.
    alle = load_alle_vnb()
    treffer: dict[str, NetzkostenEntry] = {}
    for g in info.gemeinden:
        nb = _vnb_fuer_gemeinde(g.name, g.bundesland, alle)
        if nb is not None:
            treffer[nb.key] = nb
    if len(treffer) == 1:
        return next(iter(treffer.values()))
    return None  # keiner oder mehrdeutig (geteilte PLZ) → fail-open


def _vnb_fuer_gemeinde(
    gemeinde: str, bundesland: str, alle: tuple[NetzkostenEntry, ...]
) -> NetzkostenEntry | None:
    """Der eindeutige VNB für GENAU EINE Gemeinde — oder ``None``.

    (1) Inklusion: Stadt-/Enklaven-VNB, die die Gemeinde explizit führen (Vorrang);
    (2) Exklusion: Landes-VNB im Bundesland, deren ``enclaves`` die Gemeinde nicht
    enthalten. Kein/mehrdeutiger Treffer → ``None``.
    """
    stadt = [nb for nb in alle if gemeinde and gemeinde in nb.gemeinden]
    if len(stadt) == 1:
        return stadt[0]
    if len(stadt) > 1:
        return None
    kandidaten = [
        nb
        for nb in alle
        if not nb.gemeinden and nb.bundesland == bundesland and gemeinde not in nb.enclaves
    ]
    if len(kandidaten) == 1:
        return kandidaten[0]
    return None


def tarif_fuer(nb: NetzkostenEntry) -> NetzkostenEntry | None:
    """Der Eintrag, dessen Tarif (AP/Pauschale/Verlust) für ``nb`` gilt.

    - VNB mit eigenem Tarif → er selbst.
    - Attributions-VNB (``tarif_referenz`` gesetzt) → der referenzierte
      Netzbereich-VNB (Single Source of Truth). Fail-open: unbekannte Referenz → ``None``.
    """
    if not nb.tarif_referenz:
        return nb
    return next((t for t in load_netzkosten() if t.key == nb.tarif_referenz), None)


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
    felder = {
        "gemeinde": set(info.gemeinde_namen),
        "bundesland": set(info.bundeslaender),
    }
    for feld, erwartet in match.items():
        ist = felder.get(feld, set())
        erlaubte = {erwartet} if isinstance(erwartet, str) else set(erwartet)  # type: ignore[arg-type]
        if not (ist & erlaubte):
            return False
    return True


def gebrauchsabgabe_regel(
    plz: str, netzbetreiber_key: str | None = None
) -> GebrauchsabgabeRegelDetail | None:
    """Basisgenaue Gebrauchsabgabe-Regel für eine PLZ + (falls aufgelöst) den VNB.

    Reihenfolge (1:1 wie ``gridbert.netz.abgaben.gebrauchsabgabe_regel``):
    (1) Regel des aufgelösten Netzbetreibers (deterministisch, ``gebrauchsabgabe_je_vnb``);
    (2) Long-Tail-Gemeinde per EXAKTER PLZ (``gebrauchsabgabe_longtail_plz``);
    (3) Wien-Fallback über das eigene Bundesland.

    Single-Gemeinde-Guard: Long-Tail greift nur bei eindeutiger PLZ (genau eine
    Gemeinde) — kein Mis-Apply in geteilten PLZ. Fail-open: nichts greift /
    unbekannte PLZ → ``None``.
    """
    abgaben = load_abgaben()
    if netzbetreiber_key and netzbetreiber_key in abgaben.gebrauchsabgabe_je_vnb:
        return abgaben.gebrauchsabgabe_je_vnb[netzbetreiber_key]

    info = plz_info(plz)
    if info is None:
        return None

    # Long-Tail: nur bei eindeutiger PLZ (genau eine Gemeinde) — kein Mis-Apply in
    # geteilten PLZ (Single-Gemeinde-Guard, 1:1 wie gridbert).
    if plz in abgaben.gebrauchsabgabe_longtail_plz and len(info.gemeinden) == 1:
        return abgaben.gebrauchsabgabe_longtail_plz[plz]

    # Wien ist als eigenes Bundesland eindeutig (auch ohne aufgelösten VNB).
    if "Wien" in info.gemeinde_namen and list(info.bundeslaender) == ["Wien"]:
        return abgaben.gebrauchsabgabe_je_vnb.get("wiener_netze")
    return None


def netznutzung_netto_ohne_abgaben_fuer(
    nb: NetzkostenEntry | None, jahresverbrauch_kwh: float
) -> float:
    """Reines Netznutzungs-/Netzverlustentgelt netto (ohne Abgaben) für einen VNB.

    Bemessungsgrundlage der GA-Basis "netz"/"energie_und_netz". Folgt
    ``tarif_referenz`` (Attributions-VNB). Fail-open: kein VNB/Tarif → 0.0.
    """
    if nb is None:
        return 0.0
    tarif = tarif_fuer(nb)
    if tarif is None:
        return 0.0
    return tarif.netznutzung_netto_ohne_abgaben_eur(jahresverbrauch_kwh)


def netzkosten_brutto_fuer(nb: NetzkostenEntry | None, kwh: float) -> tuple[float, str]:
    """Brutto-Netzkosten pro Jahr + **realer** VNB-Name für einen bereits aufgelösten VNB.

    Wie :func:`netzkosten_brutto_eur`, aber für einen schon (ggf. VKZ-deterministisch
    vom Konsumenten) aufgelösten VNB statt aus der PLZ. Der Tarif folgt ggf.
    ``tarif_referenz`` (Attributions-VNB). Fail-open: kein VNB/Tarif → ``(0.0, "")``.
    """
    if nb is None:
        return (0.0, "")
    tarif = tarif_fuer(nb)
    if tarif is None:
        return (0.0, "")

    abgaben = load_abgaben()
    arbeitspreis_ct = (
        tarif.netznutzung_arbeitspreis_ct_kwh
        + tarif.netzverlust_ct_kwh
        + abgaben.eag_foerderbeitrag_ap_ct_kwh
        + abgaben.eag_foerderbeitrag_verlust_ct_kwh
        + abgaben.elektrizitaetsabgabe_haushalt_ct_kwh
    )
    pauschale_eur = tarif.netznutzung_pauschale_eur_jahr + abgaben.eag_foerderpauschale_eur_jahr
    netto = arbeitspreis_ct * kwh / 100.0 + pauschale_eur
    return (round(netto * _UST, 2), nb.name)


def netzkosten_brutto_eur(plz: str, kwh: float) -> tuple[float, str]:
    """Brutto-Netzkosten pro Jahr + **realer** VNB-Name für eine PLZ.

    Der Tarif folgt ggf. ``tarif_referenz`` (Attributions-VNB billt den Tarif
    seines Netzbereichs); der Name bleibt der des realen Betreibers.

    Returns:
        ``(kosten_eur, netzbetreiber_name)``. Fail-open: kein VNB/Tarif auflösbar
        → ``(0.0, "")`` (keine Regression im Vergleich).
    """
    return netzkosten_brutto_fuer(resolve_netzbetreiber(plz), kwh)


def entry_fuer_key(key: str | None) -> NetzkostenEntry | None:
    """Der VNB-Eintrag (realer Betreiber) mit diesem ``key`` — oder ``None``.

    Brücke für Konsumenten, die den VNB selbst (z.B. VKZ-deterministisch über den
    Zählpunkt) auflösen und von et nur die Kosten beziehen. ``None``/leer → ``None``.
    """
    if not key:
        return None
    return next((nb for nb in load_alle_vnb() if nb.key == key), None)


def _normalisiere_vnb_namen(name: str) -> str:
    """Normalisiert einen VNB-Namen für toleranten Vergleich.

    Casefold, Klammer-Zusätze (z.B. ``(EVK)``) und Satzzeichen raus, Rechtsform-/
    Füllwörter (GmbH/AG/KG/…) entfernen. Damit matcht ``Stadtwerke Kapfenberg``
    auf ``Stadtwerke Kapfenberg GmbH``.
    """
    s = re.sub(r"\(.*?\)", " ", name.casefold())
    s = re.sub(r"[^0-9a-zäöüß]+", " ", s)
    return " ".join(t for t in s.split() if t not in _RECHTSFORM_TOKENS)


def akzeptierte_vnb_namen(plz: str) -> set[str]:
    """Alle für diese PLZ **akzeptierten** (gleichwertigen) VNB-Namen.

    Der reale Betreiber plus — bei einem Attributions-VNB — der Netzbereich-VNB,
    dessen Tarif gilt (z.B. ``{"Stadtwerke Kapfenberg GmbH",
    "Energienetze Steiermark GmbH"}``). Fail-open: keine Auflösung → leere Menge.
    """
    nb = resolve_netzbetreiber(plz)
    if nb is None:
        return set()
    namen = {nb.name}
    if nb.tarif_referenz:
        ref = next((t for t in load_netzkosten() if t.key == nb.tarif_referenz), None)
        if ref is not None:
            namen.add(ref.name)
    return namen


def vnb_name_akzeptiert(plz: str, name: str) -> bool:
    """Ob ``name`` ein für diese PLZ gültiger VNB-Name ist (toleranter Vergleich).

    Akzeptiert sowohl den realen Betreiber als auch den gleichwertigen
    Netzbereich-VNB, unabhängig von Rechtsform-Suffix/Groß-Kleinschreibung.
    """
    if not name:
        return False
    ziel = _normalisiere_vnb_namen(name)
    return any(_normalisiere_vnb_namen(n) == ziel for n in akzeptierte_vnb_namen(plz))


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
    return bool(set(info.bundeslaender) & erlaubte)
