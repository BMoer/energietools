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
        description="Quelle des Preisblatts (URL des Netzbetreiber-Preisblatts bzw. BGBl. II Nr. 305/2025)",
    )


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
