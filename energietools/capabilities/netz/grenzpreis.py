# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Grenzpreis je kWh — was eine zusätzliche Kilowattstunde wirklich kostet.

Der Energiepreis des Lieferanten ist nur ein Teil davon. Bei einem Wiener
Haushalt mit 12,95 ct/kWh netto Energiepreis kostet eine zusätzliche kWh rund
27 ct brutto — mehr als das Doppelte. Wer für eine Verbrauchs-Rückmeldung den
Lieferantenpreis einsetzt, halbiert die Zahl, die er dem Haushalt nennt.

Abgrenzung zu den Nachbarn im selben Paket:

* :mod:`…netz.per_kwh` liefert den **Netz-Anteil** je kWh (Netznutzung,
  Netzverlust, EAG, Elektrizitätsabgabe) — ohne Energiepreis und ohne die
  kommunale Gebrauchsabgabe, weil Dispatch und Spot-Analyse genau diesen
  Block getrennt führen.
* :func:`…netz.resolve.netzkosten_brutto_fuer` liefert die **Jahressumme**
  inklusive der verbrauchsunabhängigen Pauschalen.
* Dieses Modul liefert den **marginalen Gesamtpreis**: alles, was an einer
  zusätzlichen kWh hängt, und nichts, was auch ohne sie anfiele. Die
  Netznutzungs-Pauschale und die EAG-Förderpauschale sind deshalb bewusst
  NICHT enthalten — sie ändern sich nicht, wenn ein Gerät eine Nacht länger
  läuft.

**Die Gebrauchsabgabe ist der Grund, warum das nicht trivial ist.** Sie ist
kommunal, prozentual und hat je Gemeinde eine andere Bemessungsgrundlage
(nur Energie, nur Netz, oder beides — und in keinem Fall die Bundesabgaben).
Weil sie prozentual auf einen linearen Block wirkt, lässt sie sich exakt in
einen ct/kWh-Anteil umrechnen.

Aufgelöst wird sie über :func:`…netz.resolve.gebrauchsabgabe_regel` und damit
über **PLZ und Netzbetreiber**, nicht nur über den Netzbetreiber: die Tabelle
``gebrauchsabgabe_je_vnb`` deckt vier Netzbereiche ab, danach folgen 33
Long-Tail-Gemeinden per exakter PLZ und ein Wien-Fallback über das Bundesland.
Ohne die PLZ verliert ein Wiener Haushalt, dessen Netzbereich nicht in der
VNB-Tabelle steht, 2,05 ct/kWh brutto — rund 6 % des Grenzpreises, still.

**Die Zählpunkt-Kennung (``AT001000``) löst dieses Modul bewusst NICHT auf.**
Die VKZ-Tabelle lebt in gridbert (``gridbert/netz/resolve.py``), weil sie an
der Zählpunkt-Semantik hängt und nicht am Rechenweg; ``NetzkostenEntry`` trägt
gar kein VKZ-Feld. Der Aufrufer löst die Kennung dort auf und übergibt hier den
Netzbetreiber-Schlüssel.

**Fail-open, aber nie erfindend:** kein auflösbarer Netzbetreiber, ein
unsinniger Energiepreis → ``None``. Der Aufrufer schreibt dann keine €-Zahl,
statt eine geschätzte zu nennen.
"""

from __future__ import annotations

from dataclasses import dataclass

from energietools.capabilities.netz.data import load_abgaben
from energietools.capabilities.netz.resolve import (
    entry_fuer_key,
    gebrauchsabgabe_regel,
    tarif_fuer,
)

#: Umsatzsteuer auf Strom für Haushalte.
UST_SATZ = 1.20

#: Plausibilitätsgrenze für einen Energie-Arbeitspreis (netto, ct/kWh). Alles
#: darüber ist ein Eingabefehler — der höchste je in Österreich beworbene
#: Haushaltstarif lag während der Energiekrise unter 100 ct/kWh.
ENERGIEPREIS_MAX_CT_KWH = 100.0


@dataclass(frozen=True, slots=True)
class Grenzpreis:
    """Der Preis einer zusätzlichen kWh, aufgeschlüsselt nach Summanden.

    Jeder Summand steht einzeln, weil eine €-Zahl ohne Rechenweg in einer
    Kundenmail nichts verloren hat.
    """

    energie_ct_kwh: float
    netznutzung_ct_kwh: float
    netzverlust_ct_kwh: float
    eag_ct_kwh: float
    elektrizitaetsabgabe_ct_kwh: float
    gebrauchsabgabe_ct_kwh: float
    netto_ct_kwh: float
    brutto_ct_kwh: float
    netzbetreiber: str
    quelle: str
    gebrauchsabgabe_quelle: str = ""

    def rechenweg(self) -> str:
        """Der Rechenweg als Text, so wie er einem Haushalt gezeigt werden kann."""
        zeilen = [
            f"Energie (Lieferant): {_z(self.energie_ct_kwh)} ct/kWh netto",
            f"Netznutzung ({self.netzbetreiber}): {_z(self.netznutzung_ct_kwh)} ct/kWh",
            f"Netzverlust: {_z(self.netzverlust_ct_kwh)} ct/kWh",
            f"EAG-Förderbeitrag: {_z(self.eag_ct_kwh)} ct/kWh",
            f"Elektrizitätsabgabe: {_z(self.elektrizitaetsabgabe_ct_kwh)} ct/kWh",
        ]
        if self.gebrauchsabgabe_ct_kwh:
            zeilen.append(f"Gebrauchsabgabe: {_z(self.gebrauchsabgabe_ct_kwh)} ct/kWh")
        else:
            zeilen.append("Gebrauchsabgabe: keine in diesem Netzgebiet")
        zeilen.append(f"Summe netto: {_z(self.netto_ct_kwh)} ct/kWh")
        zeilen.append(
            f"Umsatzsteuer 20 %: {_z(self.netto_ct_kwh * (UST_SATZ - 1))} ct/kWh"
        )
        zeilen.append(f"Preis je zusätzlicher kWh: {_z(self.brutto_ct_kwh)} ct brutto")
        return "\n".join(zeilen)


def _z(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def grenzpreis_ct_kwh(
    *, energiepreis_netto_ct_kwh: float, vnb_key: str | None, plz: str = ""
) -> Grenzpreis | None:
    """Preis einer zusätzlichen kWh für einen Haushalt in diesem Netzgebiet.

    Args:
        energiepreis_netto_ct_kwh: Arbeitspreis des Lieferanten, NETTO. Aus
            einer Rechnung oder einem Vertrag, nie geschätzt.
        vnb_key: Schlüssel des Verteilernetzbetreibers (z.B. ``wiener_netze``).
            Ein synthetischer ``vkz:``-Schlüssel (bekannter Betreibername ohne
            hinterlegtes Preisblatt) löst hier bewusst zu ``None`` auf statt zu
            einem Preis ohne Netzanteil — der sähe plausibel aus und wäre um
            ein Drittel zu niedrig.
        plz: Postleitzahl des Zählpunkts. Nur für die Gebrauchsabgabe nötig,
            aber dort wichtig: ohne sie fehlt sie in jeder Gemeinde, die nicht
            über den Netzbetreiber abgedeckt ist.

    Returns:
        Aufgeschlüsselter :class:`Grenzpreis` oder ``None``, wenn der
        Netzbetreiber nicht auflösbar oder der Energiepreis unplausibel ist.
    """
    if not vnb_key:
        return None
    if not isinstance(energiepreis_netto_ct_kwh, (int, float)):
        return None
    if energiepreis_netto_ct_kwh < 0 or energiepreis_netto_ct_kwh > ENERGIEPREIS_MAX_CT_KWH:
        return None

    eintrag = entry_fuer_key(vnb_key)
    if eintrag is None:
        return None
    tarif = tarif_fuer(eintrag)
    if tarif is None:
        return None

    abgaben = load_abgaben()
    eag = (
        abgaben.eag_foerderbeitrag_ap_ct_kwh + abgaben.eag_foerderbeitrag_verlust_ct_kwh
    )
    netznutzung = tarif.netznutzung_arbeitspreis_ct_kwh
    netzverlust = tarif.netzverlust_ct_kwh
    e_abgabe = abgaben.elektrizitaetsabgabe_haushalt_ct_kwh

    ga_regel = gebrauchsabgabe_regel(plz or "", vnb_key)
    ga_ct, ga_quelle = _gebrauchsabgabe_ct_kwh(
        ga_regel,
        energie_ct=energiepreis_netto_ct_kwh,
        netz_ct=netznutzung + netzverlust,
    )

    netto = (
        energiepreis_netto_ct_kwh + netznutzung + netzverlust + eag + e_abgabe + ga_ct
    )
    return Grenzpreis(
        energie_ct_kwh=round(energiepreis_netto_ct_kwh, 4),
        netznutzung_ct_kwh=round(netznutzung, 4),
        netzverlust_ct_kwh=round(netzverlust, 4),
        eag_ct_kwh=round(eag, 4),
        elektrizitaetsabgabe_ct_kwh=round(e_abgabe, 4),
        gebrauchsabgabe_ct_kwh=round(ga_ct, 4),
        netto_ct_kwh=round(netto, 4),
        brutto_ct_kwh=round(netto * UST_SATZ, 4),
        netzbetreiber=eintrag.name,
        quelle=getattr(tarif, "quelle", "") or "",
        gebrauchsabgabe_quelle=ga_quelle,
    )


def _gebrauchsabgabe_ct_kwh(regel, *, energie_ct: float, netz_ct: float) -> tuple[float, str]:
    """Die kommunale Gebrauchsabgabe als ct/kWh-Anteil.

    Sie wirkt prozentual auf einen linearen Block (oder ist selbst ein
    ct/kWh-Betrag), lässt sich also exakt auf eine einzelne kWh herunterbrechen
    — anders als die Pauschalen, die gar nicht am Verbrauch hängen.

    Die Bemessungsgrundlage unterscheidet sich je Gemeinde und schließt die
    Bundesabgaben nie ein.
    """
    if regel is None:
        return 0.0, ""
    quelle = getattr(regel, "quelle", "") or ""
    if regel.typ == "ct_kwh":
        return float(regel.satz), quelle
    if regel.typ != "prozent":
        return 0.0, quelle
    basis = {
        "energie": energie_ct,
        "netz": netz_ct,
        "energie_und_netz": energie_ct + netz_ct,
    }.get(regel.basis)
    if basis is None:
        return 0.0, quelle
    return basis * float(regel.satz), quelle
