# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Datenmodelle für die publizierten Netz-Daten (offline, auditierbar).

Alle Modelle sind ``frozen`` (immutable): ein geladener Snapshot wird nie
in-place mutiert — eine neue Preisperiode ist ein neues Objekt. Die Modelle
spiegeln 1:1 die Form der JSON-Dateien in ``data/netz/`` (Netzkosten je
Netzbereich, PLZ-Index, föderale Abgaben + Gebrauchsabgabe-Regeln, Manifest).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class NetzkostenEntry(BaseModel):
    """Regulierte Netzkosten eines Netzbereichs (NE7-Haushalt, Niederspannung).

    **VNB-spezifisch** sind nur Netznutzungs-Arbeitspreis, Netznutzungs-Pauschale
    und Netzverlust. EAG-Förderbeitrag und Elektrizitätsabgabe sind bundesweit
    uniform und kommen als föderale Konstanten aus ``abgaben.json`` (siehe
    :class:`Abgaben`) in die Jahreskosten-Formel.

    Zwei Gebiets-Modelle:
    - **Landes-VNB** (``gemeinden`` leer): versorgt sein Bundesland per Exklusion —
      alles außer ``enclaves`` (eigene Stadtwerke).
    - **Stadt-/Enklaven-VNB** (``gemeinden`` gesetzt): versorgt per Inklusion genau
      die gelisteten Gemeinden (Linz/Graz/Innsbruck/Klagenfurt/Kleinwalsertal).

    **Attributions-VNB** tragen zusätzlich ``tarif_referenz`` (key des Netzbereich-
    VNB, dessen Tarif gilt) und haben dann AP/Pauschale/Verlust = 0 (Tarif via
    Referenz, kein Wert-Duplikat).
    """

    model_config = ConfigDict(frozen=True)

    key: str = Field(description="Eindeutiger Schlüssel (z.B. 'wiener_netze')")
    name: str = Field(description="Anzeigename des VNB")
    bundesland: str = Field(description="Bundesland des Versorgungsgebiets")
    enclaves: tuple[str, ...] = Field(
        default=(),
        description="Landes-VNB: Gemeinden, die dieser VNB NICHT versorgt (eigene Stadtwerke)",
    )
    gemeinden: tuple[str, ...] = Field(
        default=(),
        description="Stadt-/Enklaven-VNB: per Inklusion versorgte Gemeinden (leer = Landes-VNB)",
    )
    netznutzung_arbeitspreis_ct_kwh: float = Field(
        default=0.0, description="Netznutzung Arbeitspreis ct/kWh (0 bei Attributions-VNB)"
    )
    netznutzung_pauschale_eur_jahr: float = Field(
        default=0.0, description="Netznutzung Pauschale EUR/Jahr (Grundpreis + Messentgelt)"
    )
    netzverlust_ct_kwh: float = Field(default=0.0, description="Netzverlust-Entgelt ct/kWh")
    tarif_referenz: str = Field(
        default="",
        description="Attributions-VNB: key des Netzbereich-VNB, dessen Tarif gilt",
    )
    gueltig_ab: str = Field(default="", description="Gültig ab (ISO-Datum, z.B. '2026-01-01')")
    quelle: str = Field(
        default="",
        description=(
            "Quelle des Preisblatts (URL des Netzbetreiber-Preisblatts bzw. BGBl. II Nr. 305/2025)"
        ),
    )

    def netznutzung_netto_ohne_abgaben_eur(self, jahresverbrauch_kwh: float) -> float:
        """Reines Netznutzungs-/Netzverlustentgelt netto, OHNE föderale Abgaben.

        Bemessungsgrundlage für die Gebrauchsabgabe-Basis "Netz (ohne Abgaben)":
        nur VNB-Netznutzungs-Arbeitspreis + Netzverlust (ct/kWh) + Netznutzungs-
        Pauschale (EUR/Jahr) — OHNE EAG-Förderbeitrag/-pauschale und OHNE
        Elektrizitätsabgabe (die sind selbst Abgaben, nicht Teil der GA-Basis).
        Spiegelt ``gridbert.netz.models.Netzkosten.netznutzung_netto_ohne_abgaben_eur``.
        """
        ct_pro_kwh = self.netznutzung_arbeitspreis_ct_kwh + self.netzverlust_ct_kwh
        return ct_pro_kwh * jahresverbrauch_kwh / 100.0 + self.netznutzung_pauschale_eur_jahr


class PlzInfo(BaseModel):
    """Ein PLZ-Eintrag aus dem PLZ→Netzbereich-Index."""

    model_config = ConfigDict(frozen=True)

    plz: str = Field(description="Postleitzahl")
    gemeinde: str = Field(description="Gemeinde-/Ortsname")
    bundesland: str = Field(description="Bundesland")


class GebrauchsabgabeRegel(BaseModel):
    """Eine Gebrauchsabgabe-Regel (Match-Kriterien → Satz)."""

    model_config = ConfigDict(frozen=True)

    match: dict[str, object] = Field(
        default_factory=dict,
        description="Match-Kriterien (z.B. {'gemeinde': 'Wien'} oder {'bundesland': [...]})",
    )
    rate: float = Field(description="Gebrauchsabgabe-Satz (Anteil, z.B. 0.07 = 7 %)")
    quelle: str = Field(default="", description="Rechtsgrundlage / Quelle")


class GebrauchsabgabeRegelDetail(BaseModel):
    """Basisgenaue Gebrauchsabgabe-Regel (immutable) — typ/satz/basis.

    ``typ``:  "prozent" (Anteil auf eine Basis) oder "ct_kwh" (Fixbetrag je kWh).
    ``satz``: bei "prozent" der Anteil (0.07 = 7 %); bei "ct_kwh" der ct/kWh-Betrag.
    ``basis``: bei "prozent" "energie" | "netz" | "energie_und_netz" (welcher
              Netto-Block die Bemessungsgrundlage ist); bei "ct_kwh" "verbrauch".

    Spiegelt 1:1 ``gridbert.netz.abgaben.GebrauchsabgabeRegel`` (Referenz der
    basisgenauen GA-Berechnung). Quelle: E-Control-Gebrauchsabgabe-Liste Strom,
    Stand 01.03.2026, fundiert auf den Landes-Gebrauchsabgabegesetzen.
    """

    model_config = ConfigDict(frozen=True)

    typ: str = Field(description="'prozent' (Anteil auf Basis) oder 'ct_kwh' (Fixbetrag je kWh)")
    satz: float = Field(description="Anteil (0.07 = 7 %) bzw. ct/kWh-Betrag")
    basis: str = Field(description="'energie' | 'netz' | 'energie_und_netz' | 'verbrauch'")
    gemeinde: str = Field(default="", description="Gemeinde-/Gebietsbezeichnung")
    quelle: str = Field(default="", description="Rechtsgrundlage / Quelle")
    gueltig_ab: str = Field(default="2026-03-01", description="Gültig ab (ISO-Datum)")

    def betrag_netto_eur(
        self, energie_netto_eur: float, netz_netto_eur: float, verbrauch_kwh: float
    ) -> float:
        """Netto-Gebrauchsabgabe in EUR/Jahr für diese Regel.

        ``energie_netto_eur`` = Energie-Arbeitspreis-Netto (Verbrauch × ct/kWh).
        ``netz_netto_eur``    = reines Netznutzungs-/Netzverlustentgelt netto
                                (OHNE föderale Abgaben — "Netz ohne Abgaben").
        """
        if self.typ == "ct_kwh":
            return self.satz * verbrauch_kwh / 100.0
        if self.basis == "energie":
            basis_eur = energie_netto_eur
        elif self.basis == "netz":
            basis_eur = netz_netto_eur
        else:  # "energie_und_netz"
            basis_eur = energie_netto_eur + netz_netto_eur
        return self.satz * basis_eur


class Abgaben(BaseModel):
    """Föderale Abgaben (bundesweit uniform) + Gebrauchsabgabe-Regeln.

    ``federal`` trägt die bundesweit uniformen Arbeitspreis-/Pauschal-Anteile
    (EAG-Förderbeitrag, EAG-Förderpauschale, Elektrizitätsabgabe Haushalt).
    ``gebrauchsabgabe_regeln`` sind länder-/gemeindespezifisch; greift keine
    Regel, gilt ``gebrauchsabgabe_default``.
    """

    model_config = ConfigDict(frozen=True)

    gueltig_ab: str = Field(default="", description="Gültig ab (z.B. '2026')")
    federal: dict[str, object] = Field(
        default_factory=dict,
        description="Bundesweit uniforme Abgaben (ct/kWh bzw. EUR/Jahr) + Quelle",
    )
    gebrauchsabgabe_basis: str = Field(
        default="energie_netto",
        description="Bemessungsbasis der Gebrauchsabgabe (Konvention)",
    )
    gebrauchsabgabe_regeln: tuple[GebrauchsabgabeRegel, ...] = Field(
        default=(), description="Länder-/gemeindespezifische Gebrauchsabgabe-Regeln"
    )
    gebrauchsabgabe_default: float = Field(
        default=0.0, description="Satz, wenn keine Regel greift (ehrlich 0, nicht erfunden)"
    )
    gebrauchsabgabe_je_vnb: dict[str, GebrauchsabgabeRegelDetail] = Field(
        default_factory=dict,
        description="Basisgenaue GA-Regel je aufgelöstem VNB-Key (typ/satz/basis)",
    )
    gebrauchsabgabe_longtail_plz: dict[str, GebrauchsabgabeRegelDetail] = Field(
        default_factory=dict,
        description="Basisgenaue GA-Regel je exakter Long-Tail-PLZ (Single-Gemeinde)",
    )

    def _federal_float(self, schluessel: str) -> float:
        """Föderale Konstante als float (0.0, wenn fehlend/nicht numerisch)."""
        wert = self.federal.get(schluessel)
        if isinstance(wert, (int, float)):
            return float(wert)
        return 0.0

    @property
    def eag_foerderbeitrag_ap_ct_kwh(self) -> float:
        return self._federal_float("eag_foerderbeitrag_ap_ct_kwh")

    @property
    def eag_foerderbeitrag_verlust_ct_kwh(self) -> float:
        return self._federal_float("eag_foerderbeitrag_verlust_ct_kwh")

    @property
    def eag_foerderpauschale_eur_jahr(self) -> float:
        return self._federal_float("eag_foerderpauschale_eur_jahr")

    @property
    def elektrizitaetsabgabe_haushalt_ct_kwh(self) -> float:
        return self._federal_float("elektrizitaetsabgabe_haushalt_ct_kwh")


class NetzManifest(BaseModel):
    """Metadaten des Netz-Daten-Snapshots (Provenance, Coverage, Lizenz)."""

    model_config = ConfigDict(frozen=True)

    data_version: str = Field(default="", description="Daten-Version")
    generated_at: str = Field(default="", description="Erzeugt am (ISO)")
    market: str = Field(default="AT")
    energy_type: str = Field(default="POWER")
    profil: str = Field(default="", description="Tarif-/Lastprofil (z.B. NE7 Haushalt)")
    netzbereich_coverage: dict[str, object] = Field(default_factory=dict)
    plz_count: int = Field(default=0)
    provenance: str = Field(default="")
    methodik: str = Field(default="", description="Verweis auf den Provenance-Doc (wie erhoben)")
    knowledge: str = Field(default="", description="Verweis auf die Wissens-Referenz (Bedeutung)")
    license: str = Field(default="")
    disclaimer: str = Field(default="")
