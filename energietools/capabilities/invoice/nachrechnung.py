# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Centgenaue Nachrechnung einer Stromrechnung — Position für Position.

Bis hierher gab es nur eine **Plausibilitätsprüfung**: Summe der Netto-Blöcke
× 1,2 gegen den Rechnungsbetrag, Toleranz ±15 % (``facts._pruefe_cross_field``).
Damit rutscht ein Rechenfehler von 3 % unbemerkt durch — für die Aussage „hier
wurde falsch gerechnet" ist das unbrauchbar.

Dieses Modul rechnet stattdessen nach, und zwar in drei Härtegraden, die
bewusst auseinandergehalten werden:

1. **Summenprüfung — hart, centgenau.** Die angegebenen Blöcke werden addiert
   und gegen den Rechnungsbetrag gestellt. Das ist reine Arithmetik auf den
   Zahlen der Rechnung selbst; es braucht keine Referenzdaten und kennt keine
   legitime Abweichung. Toleranz: 5 Cent (kaufmännische Rundung je Block).
2. **Positionsprüfung — weich, mit begründeter Toleranz.** Arbeitspreis ×
   Menge + Grundgebühr × Monate gegen den Energieblock. Die Rechnung selbst
   ist exakt; unscharf ist nur die **Transkription** des Arbeitspreises (auf
   der Rechnung oft vier Nachkommastellen, im Fakten-Feld gerundet). Die
   Toleranz skaliert deshalb mit der Menge, nicht mit dem Betrag.
3. **Referenzprüfung — Vergleich gegen den regulierten Tarif.** Netzentgelte
   und Abgaben sind in Österreich reguliert und öffentlich; energietools kennt
   sie. Eine Abweichung ist hier aber **kein Fehlerbeweis**: Netzebene,
   Zählertyp und unterjährige Tarifwechsel erklären Unterschiede legitim.
   Deshalb weiche Toleranz und vorsichtige Sprache.

**Warum die Trennung wichtig ist:** Ein Fehlalarm „dein Lieferant hat falsch
gerechnet" ist teurer als ein ausbleibender Befund. Nur Härtegrad 1 rechtfertigt
den Satz „die Rechnung geht nicht auf"; die anderen beiden liefern Hinweise mit
Begründung.

Kein Wert wird geschätzt. Fehlt ein Feld, ist die Position ``nicht_pruefbar``
und sagt, welches Feld fehlt — eine halbe Prüfung, die sich als ganze ausgibt,
wäre schlimmer als keine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from energietools.capabilities.invoice.facts import Betrag, Grundgebuehr, InvoiceFacts, PreisCtKwh
from energietools.capabilities.netz.resolve import (
    gebrauchsabgabe_regel,
    load_abgaben,
    resolve_netzbetreiber,
    tarif_fuer,
)

UST_SATZ = 0.20
_UST = 1.0 + UST_SATZ

# Härtegrad 1: die Summenprüfung ist reine Arithmetik auf den Zahlen der
# Rechnung. Erlaubt ist nur kaufmännische Rundung je Block (drei Blöcke +
# Gesamtbetrag ⇒ 4 × 1 Cent, aufgerundet auf 5).
SUMMEN_TOLERANZ_EUR = 0.05

# Härtegrad 2: unscharf ist die TRANSKRIPTION des Arbeitspreises, nicht die
# Rechnung. 0,005 ct/kWh Unsicherheit entspricht der halben letzten Stelle
# eines vierstellig angegebenen Preises; die Toleranz skaliert deshalb mit der
# Menge. Der Sockel fängt Grundgebühr-Rundungen.
POSITION_SOCKEL_EUR = 0.10
POSITION_PREIS_UNSCHAERFE_CT_KWH = 0.005

# Härtegrad 3: Referenzvergleich gegen den regulierten Tarif. Netzebene,
# Zählertyp und unterjährige Tarifwechsel erklären Unterschiede legitim.
REFERENZ_TOLERANZ_ANTEIL = 0.03
REFERENZ_SOCKEL_EUR = 5.0

STIMMT = "stimmt"
ZU_HOCH = "zu_hoch"
GUENSTIGER = "guenstiger_als_erwartet"
NICHT_PRUEFBAR = "nicht_pruefbar"

BEFUND_STIMMIG = "stimmig"
BEFUND_ABWEICHUNG = "abweichung"
BEFUND_UNVOLLSTAENDIG = "unvollstaendig"


@dataclass(frozen=True)
class Positionspruefung:
    """Eine nachgerechnete Position mit ihrem Rechenweg."""

    block: str
    bezeichnung: str
    haertegrad: str  # "summe" | "position" | "referenz"
    status: str
    angegeben_eur: float | None = None
    erwartet_eur: float | None = None
    abweichung_eur: float | None = None
    toleranz_eur: float | None = None
    rechenweg: str = ""
    grund: str | None = None


@dataclass(frozen=True)
class Nachrechnung:
    """Gesamtergebnis der formalen Prüfung."""

    befund: str
    zusammenfassung: str
    positionen: tuple[Positionspruefung, ...] = field(default_factory=tuple)
    zu_viel_verrechnet_eur: float | None = None
    geprueft_gegen: str = ""


# --- Hilfen ----------------------------------------------------------------


def _tage(von: date, bis: date) -> int:
    """Abgerechnete Tage, Anfangs- und Endtag eingeschlossen."""
    return max(1, (bis - von).days + 1)


def _jahresanteil(von: date, bis: date) -> float:
    return _tage(von, bis) / 365.0


def _monatsanteil(von: date, bis: date) -> float:
    """Abgerechnete Monate, kalendergenau.

    **Nicht** Tage/30,44: Ein volles Kalenderjahr (365 Tage) ergäbe damit
    11,99 Monate und die erwartete Grundgebühr läge vier Cent zu niedrig — bei
    einer centgenauen Prüfung ist das der Unterschied zwischen „stimmt" und
    einem Fehlalarm. Gezählt werden ganze Monatsschritte plus der Tagesanteil
    des angebrochenen Monats: 01.01.–31.12. ⇒ 12,0; 01.01.–30.06. ⇒ 6,0;
    15.03.–14.03. ⇒ 12,0.
    """
    ganze = (bis.year - von.year) * 12 + (bis.month - von.month)
    tage_im_endmonat = _tage_im_monat(bis.year, bis.month)
    rest = (bis.day - von.day + 1) / tage_im_endmonat
    return max(0.0, ganze + rest)


def _tage_im_monat(jahr: int, monat: int) -> int:
    if monat == 12:
        return (date(jahr + 1, 1, 1) - date(jahr, 12, 1)).days
    return (date(jahr, monat + 1, 1) - date(jahr, monat, 1)).days


def _netto(betrag: Betrag | None) -> float | None:
    if betrag is None:
        return None
    return betrag.wert_eur if betrag.ist_netto else betrag.wert_eur / _UST


def _preis_netto_ct(preis: PreisCtKwh | None) -> float | None:
    if preis is None:
        return None
    return preis.wert_ct_kwh if preis.ist_netto else preis.wert_ct_kwh / _UST


def _grundgebuehr_netto_monat(gg: Grundgebuehr | None) -> float | None:
    if gg is None:
        return None
    wert = gg.wert_eur if gg.ist_netto else gg.wert_eur / _UST
    return wert / 12.0 if gg.zeitraum == "jahr" else wert


def _nicht_pruefbar(block: str, bezeichnung: str, haertegrad: str, grund: str) -> Positionspruefung:
    return Positionspruefung(
        block=block,
        bezeichnung=bezeichnung,
        haertegrad=haertegrad,
        status=NICHT_PRUEFBAR,
        grund=grund,
    )


def _bewerte(
    *,
    block: str,
    bezeichnung: str,
    haertegrad: str,
    angegeben: float,
    erwartet: float,
    toleranz: float,
    rechenweg: str,
) -> Positionspruefung:
    """Eine Position gegen ihre Erwartung stellen.

    ``guenstiger_als_erwartet`` ist bewusst KEIN Fehler: Rabatte, Gutschriften
    und Aktionspreise machen den Block kleiner als Preis × Menge. Nur ein
    Betrag ÜBER der Erwartung ist ein Befund zulasten des Kunden.
    """
    abweichung = round(angegeben - erwartet, 2)
    if abs(abweichung) <= toleranz:
        status = STIMMT
    elif abweichung > 0:
        status = ZU_HOCH
    else:
        status = GUENSTIGER
    return Positionspruefung(
        block=block,
        bezeichnung=bezeichnung,
        haertegrad=haertegrad,
        status=status,
        angegeben_eur=round(angegeben, 2),
        erwartet_eur=round(erwartet, 2),
        abweichung_eur=abweichung,
        toleranz_eur=round(toleranz, 2),
        rechenweg=rechenweg,
    )


# --- Die einzelnen Prüfungen ------------------------------------------------


def _pruefe_energie(f: InvoiceFacts) -> Positionspruefung:
    angegeben = _netto(f.summe_energieentgelte)
    if angegeben is None:
        return _nicht_pruefbar(
            "energie", "Energie (Arbeitspreis + Grundgebühr)", "position",
            "summe_energieentgelte fehlt — ohne Blocksumme gibt es nichts nachzurechnen.",
        )
    preis_ct = _preis_netto_ct(f.arbeitspreis)
    if preis_ct is None:
        return _nicht_pruefbar(
            "energie", "Energie (Arbeitspreis + Grundgebühr)", "position",
            "arbeitspreis fehlt — Preis × Menge ist ohne Preis nicht rechenbar.",
        )

    arbeit = preis_ct * f.verbrauch_kwh / 100.0
    monate = _monatsanteil(f.zeitraum_von, f.zeitraum_bis)
    gg_monat = _grundgebuehr_netto_monat(f.grundgebuehr)
    grund_summe = (gg_monat or 0.0) * monate
    erwartet = arbeit + grund_summe

    toleranz = POSITION_SOCKEL_EUR + (
        POSITION_PREIS_UNSCHAERFE_CT_KWH * f.verbrauch_kwh / 100.0
    )
    teile = [f"{f.verbrauch_kwh:g} kWh × {preis_ct:.4f} ct netto = {arbeit:.2f} €"]
    if gg_monat is not None:
        teile.append(f"+ {monate:.2f} Monate × {gg_monat:.2f} € Grundgebühr = {grund_summe:.2f} €")
    else:
        teile.append("(keine Grundgebühr angegeben)")
    teile.append(f"⇒ erwartet {erwartet:.2f} € netto, auf der Rechnung {angegeben:.2f} € netto")
    return _bewerte(
        block="energie",
        bezeichnung="Energie (Arbeitspreis + Grundgebühr)",
        haertegrad="position",
        angegeben=angegeben,
        erwartet=erwartet,
        toleranz=toleranz,
        rechenweg="; ".join(teile),
    )


def _netz_referenz(f: InvoiceFacts) -> tuple[float, float, str] | None:
    """(Netzentgelt netto, Abgaben netto, VNB-Name) aus dem regulierten Tarif.

    Getrennt nach den Blöcken, wie sie auf einer Rechnung stehen: Netznutzung
    und Netzverlust bilden das Netzentgelt, EAG-Beitrag, Elektrizitätsabgabe
    und Gebrauchsabgabe die Steuern und Abgaben.
    """
    nb = resolve_netzbetreiber(f.plz)
    tarif = tarif_fuer(nb) if nb is not None else None
    if nb is None or tarif is None:
        return None
    abgaben = load_abgaben()
    kwh = f.verbrauch_kwh
    anteil = _jahresanteil(f.zeitraum_von, f.zeitraum_bis)

    netz = (
        (tarif.netznutzung_arbeitspreis_ct_kwh + tarif.netzverlust_ct_kwh) * kwh / 100.0
        + tarif.netznutzung_pauschale_eur_jahr * anteil
    )
    abgaben_summe = (
        (
            abgaben.eag_foerderbeitrag_ap_ct_kwh
            + abgaben.eag_foerderbeitrag_verlust_ct_kwh
            + abgaben.elektrizitaetsabgabe_haushalt_ct_kwh
        )
        * kwh
        / 100.0
        + abgaben.eag_foerderpauschale_eur_jahr * anteil
    )
    regel = gebrauchsabgabe_regel(f.plz, nb.key)
    if regel is not None and getattr(regel, "satz", None):
        abgaben_summe += _gebrauchsabgabe(regel, netz_netto=netz, energie_netto=_energie_basis(f))
    return (netz, abgaben_summe, nb.name)


def _energie_basis(f: InvoiceFacts) -> float:
    energie = _netto(f.summe_energieentgelte)
    if energie is not None:
        return energie
    preis_ct = _preis_netto_ct(f.arbeitspreis)
    return (preis_ct * f.verbrauch_kwh / 100.0) if preis_ct else 0.0


def _gebrauchsabgabe(regel, *, netz_netto: float, energie_netto: float) -> float:
    """Gebrauchsabgabe auf ihrer jeweiligen Bemessungsgrundlage."""
    satz = float(getattr(regel, "satz", 0.0) or 0.0)
    basis_name = str(getattr(regel, "basis", "") or "")
    if basis_name == "netz":
        basis = netz_netto
    elif basis_name == "energie":
        basis = energie_netto
    else:
        basis = netz_netto + energie_netto
    return basis * satz


def _pruefe_referenzblock(
    f: InvoiceFacts,
    *,
    block: str,
    bezeichnung: str,
    angegeben: float | None,
    erwartet: float | None,
    vnb: str,
    zusatz: str,
) -> Positionspruefung:
    if angegeben is None:
        return _nicht_pruefbar(
            block, bezeichnung, "referenz",
            f"summe_{block} fehlt auf der eingereichten Rechnung.",
        )
    if erwartet is None:
        return _nicht_pruefbar(
            block, bezeichnung, "referenz",
            f"Für PLZ {f.plz} ist kein Netzbetreiber auflösbar — ohne regulierten "
            "Tarif gibt es keine Referenz.",
        )
    toleranz = max(REFERENZ_SOCKEL_EUR, erwartet * REFERENZ_TOLERANZ_ANTEIL)
    return _bewerte(
        block=block,
        bezeichnung=bezeichnung,
        haertegrad="referenz",
        angegeben=angegeben,
        erwartet=erwartet,
        toleranz=toleranz,
        rechenweg=(
            f"reguliert für {vnb}, {f.verbrauch_kwh:g} kWh über "
            f"{_tage(f.zeitraum_von, f.zeitraum_bis)} Tage: {erwartet:.2f} € netto{zusatz}; "
            f"auf der Rechnung {angegeben:.2f} € netto"
        ),
    )


def _pruefe_summe(f: InvoiceFacts) -> Positionspruefung:
    """Härtegrad 1 — die eine Prüfung, die einen Rechenfehler beweisen kann."""
    if f.rechnungsbetrag_brutto_eur is None:
        return _nicht_pruefbar(
            "gesamtsumme", "Summe aller Blöcke gegen den Rechnungsbetrag", "summe",
            "rechnungsbetrag_brutto_eur fehlt — ohne Gesamtbetrag gibt es nichts zu prüfen.",
        )
    bloecke = {
        "Energie": f.summe_energieentgelte,
        "Netz": f.summe_netzentgelte,
        "Steuern und Abgaben": f.summe_steuern_abgaben,
    }
    fehlend = [name for name, b in bloecke.items() if b is None]
    if fehlend:
        return _nicht_pruefbar(
            "gesamtsumme", "Summe aller Blöcke gegen den Rechnungsbetrag", "summe",
            "Nicht alle Blöcke eingereicht — es fehlen: " + ", ".join(fehlend)
            + ". Eine Summenprüfung über unvollständige Blöcke wäre ein Fehlalarm.",
        )

    netto_summe = sum(_netto(b) or 0.0 for b in bloecke.values())
    erwartet_brutto = netto_summe * _UST
    teile = [f"{name} {(_netto(b) or 0.0):.2f} €" for name, b in bloecke.items()]
    return _bewerte(
        block="gesamtsumme",
        bezeichnung="Summe aller Blöcke gegen den Rechnungsbetrag",
        haertegrad="summe",
        angegeben=f.rechnungsbetrag_brutto_eur,
        erwartet=erwartet_brutto,
        toleranz=SUMMEN_TOLERANZ_EUR,
        rechenweg=(
            " + ".join(teile)
            + f" = {netto_summe:.2f} € netto; + {UST_SATZ:.0%} USt = "
            f"{erwartet_brutto:.2f} € brutto; "
            f"Rechnungsbetrag {f.rechnungsbetrag_brutto_eur:.2f} €"
        ),
    )


# --- Öffentliche Schnittstelle ----------------------------------------------


def rechne_nach(f: InvoiceFacts) -> Nachrechnung:
    """Rechnet eine eingereichte Rechnung Position für Position nach."""
    referenz = _netz_referenz(f)
    netz_erwartet, abgaben_erwartet, vnb = referenz if referenz else (None, None, "")

    positionen = [
        _pruefe_summe(f),
        _pruefe_energie(f),
        _pruefe_referenzblock(
            f,
            block="netzentgelte",
            bezeichnung="Netzentgelt (Netznutzung + Netzverlust)",
            angegeben=_netto(f.summe_netzentgelte),
            erwartet=netz_erwartet,
            vnb=vnb,
            zusatz=" inkl. Grundpauschale anteilig",
        ),
        _pruefe_referenzblock(
            f,
            block="steuern_abgaben",
            bezeichnung="Steuern und Abgaben",
            angegeben=_netto(f.summe_steuern_abgaben),
            erwartet=abgaben_erwartet,
            vnb=vnb,
            zusatz=" (EAG-Beitrag, Elektrizitätsabgabe, ggf. Gebrauchsabgabe)",
        ),
    ]
    return Nachrechnung(
        befund=_befund(positionen),
        zusammenfassung=_zusammenfassung(positionen),
        positionen=tuple(positionen),
        zu_viel_verrechnet_eur=_zu_viel(positionen),
        geprueft_gegen=(
            f"regulierter Netztarif {vnb} + Bundesabgaben" if vnb else "nur die Zahlen der Rechnung"
        ),
    )


def _befund(positionen: list[Positionspruefung]) -> str:
    summe = next(p for p in positionen if p.block == "gesamtsumme")
    if summe.status == ZU_HOCH or any(
        p.status == ZU_HOCH and p.haertegrad in {"summe", "position"} for p in positionen
    ):
        return BEFUND_ABWEICHUNG
    if summe.status == NICHT_PRUEFBAR:
        return BEFUND_UNVOLLSTAENDIG
    return BEFUND_STIMMIG


def _zu_viel(positionen: list[Positionspruefung]) -> float | None:
    """Der Betrag, um den die Rechnung über der Nachrechnung liegt.

    Nur aus den harten Prüfungen (Summe, Position) — der Referenzvergleich
    gegen den regulierten Tarif taugt nicht als Forderungsbetrag.
    """
    betraege = [
        p.abweichung_eur
        for p in positionen
        if p.status == ZU_HOCH and p.haertegrad in {"summe", "position"} and p.abweichung_eur
    ]
    return round(max(betraege), 2) if betraege else None


def _zusammenfassung(positionen: list[Positionspruefung]) -> str:
    summe = next(p for p in positionen if p.block == "gesamtsumme")
    if summe.status == ZU_HOCH:
        return (
            f"Die Rechnung geht nicht auf: Die angegebenen Blöcke ergeben "
            f"{summe.erwartet_eur:.2f} €, verrechnet wurden {summe.angegeben_eur:.2f} € — "
            f"{summe.abweichung_eur:.2f} € zu viel."
        )
    if summe.status == GUENSTIGER:
        return (
            f"Der Rechnungsbetrag liegt {abs(summe.abweichung_eur):.2f} € UNTER der Summe der "
            "Blöcke — typischerweise eine Gutschrift oder ein Rabatt, der nicht in den "
            "Blöcken steht."
        )
    if summe.status == STIMMT:
        auffaellig = [p for p in positionen if p.status == ZU_HOCH]
        if auffaellig:
            return (
                "Die Gesamtsumme geht centgenau auf. Auffällig ist aber: "
                + "; ".join(
                    f"{p.bezeichnung} liegt {p.abweichung_eur:.2f} € über der Erwartung"
                    for p in auffaellig
                )
                + "."
            )
        return "Die Rechnung geht centgenau auf — Summe und geprüfte Positionen stimmen."
    return f"Die Rechnung konnte nicht vollständig nachgerechnet werden: {summe.grund}"
