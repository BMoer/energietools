# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pydantic import BaseModel, Field


class Rechenweg(BaseModel):
    """Transparenter Berechnungsweg für einen Tarif — ermöglicht Nachvollziehbarkeit."""

    energiepreis_netto_ct_kwh: float = Field(description="Netto-Energiepreis ct/kWh (ohne USt)")
    grundgebuehr_netto_eur_monat: float = Field(description="Netto-Grundgebühr EUR/Monat")
    netto_energie_eur: float = Field(description="Verbrauch × Netto-Energiepreis")
    netto_grund_eur: float = Field(description="Netto-Grundgebühr × 12 Monate")
    netto_gesamt_eur: float = Field(description="Netto-Energie + Netto-Grund")
    gebrauchsabgabe_rate: float = Field(description="Gebrauchsabgabe-Satz (z.B. 0.07 für Wien)")
    gebrauchsabgabe_eur: float = Field(description="Gebrauchsabgabe in EUR")
    netto_inkl_gab_eur: float = Field(description="Netto inkl. Gebrauchsabgabe")
    ust_eur: float = Field(description="Umsatzsteuer 20%")
    brutto_jahreskosten_eur: float = Field(description="Endwert: Brutto-Jahreskosten Energie")
    quelle: str = Field(default="berechnet", description="'e-control-api' oder 'berechnet'")
    hinweis: str = Field(
        default="",
        description="Zusätzliche Info (z.B. 'Gebrauchsabgabe nicht verfügbar')",
    )


class Tariff(BaseModel):
    """Ein Stromtarif aus dem E-Control Vergleich."""

    lieferant: str
    tarif_name: str
    energiepreis_ct_kwh: float
    grundgebuehr_eur_monat: float
    jahreskosten_eur: float = Field(description="Energiekosten €/Jahr (Energie + Grundgebühr, ohne Netz)")
    gesamtkosten_eur: float = Field(default=0.0, description="Gesamtkosten €/Jahr inkl. Netzkosten")
    ersparnis_eur: float = Field(default=0.0, description="Ersparnis vs. aktueller Tarif in €/Jahr")
    ist_oekostrom: bool = False
    tariftyp: str = Field(default="Fixpreis", description="Fixpreis, Monatsfloater oder Stundenfloater")
    kategorie: str = Field(default="fix", description="Kategorie: fix, floater, gruen")
    quelle: str = Field(default="e-control", description="Datenquelle")
    rechenweg: Rechenweg | None = Field(default=None, description="Transparenter Berechnungsweg")


def _categorize(tariff: Tariff) -> str:
    """Determine category from tariftyp."""
    typ = tariff.tariftyp.lower()
    if "float" in typ or "monat" in typ or "spot" in typ or "stunden" in typ:
        return "floater"
    return "fix"


class TariffComparison(BaseModel):
    """Ergebnis des Tarifvergleichs — vollständig deterministisch sortiert."""

    aktueller_tarif: Tariff
    alternativen: list[Tariff] = Field(default_factory=list)
    plz: str = ""
    jahresverbrauch_kwh: float = 0.0
    netzkosten_eur_jahr: float = Field(default=0.0, description="Behördlich festgelegte Netzkosten €/Jahr brutto")
    netzbetreiber: str = Field(default="", description="Name des Netzbetreibers")
    gebrauchsabgabe_rate: float = Field(
        default=0.0,
        description="Gebrauchsabgabe-Satz für diese PLZ (z.B. 0.07 für Wien)",
    )

    # Pre-sorted category lists (computed by enrich())
    beste_fix: list[Tariff] = Field(default_factory=list)
    beste_floater: list[Tariff] = Field(default_factory=list)
    beste_gruen: list[Tariff] = Field(default_factory=list)
    bester_gesamt: Tariff | None = None
    max_ersparnis_eur: float = 0.0

    @property
    def bester_tarif(self) -> Tariff | None:
        """Backward-compat: cheapest alternative overall."""
        return self.bester_gesamt

    def enrich(self) -> TariffComparison:
        """Compute savings, categories, and sorted lists. Returns new instance."""
        aktuell_kosten = self.aktueller_tarif.jahreskosten_eur
        netz = self.netzkosten_eur_jahr

        # Enrich each tariff with savings, gesamtkosten, kategorie
        enriched: list[Tariff] = []
        for t in self.alternativen:
            cat = _categorize(t)
            enriched.append(Tariff(
                **{
                    **t.model_dump(),
                    "ersparnis_eur": round(aktuell_kosten - t.jahreskosten_eur, 2),
                    "gesamtkosten_eur": round(t.jahreskosten_eur + netz, 2),
                    "kategorie": cat,
                }
            ))

        # Sort each category by jahreskosten_eur (cheapest first)
        fix_tarife = sorted(
            [t for t in enriched if t.kategorie == "fix"],
            key=lambda t: t.jahreskosten_eur,
        )
        floater_tarife = sorted(
            [t for t in enriched if t.kategorie == "floater"],
            key=lambda t: t.jahreskosten_eur,
        )
        gruen_tarife = sorted(
            [t for t in enriched if t.ist_oekostrom],
            key=lambda t: t.jahreskosten_eur,
        )

        bester = min(enriched, key=lambda t: t.jahreskosten_eur) if enriched else None

        # Enrich aktueller_tarif too
        aktuell_enriched = Tariff(
            **{
                **self.aktueller_tarif.model_dump(),
                "gesamtkosten_eur": round(aktuell_kosten + netz, 2),
                "kategorie": "aktuell",
            }
        )

        return TariffComparison(
            aktueller_tarif=aktuell_enriched,
            alternativen=enriched,
            plz=self.plz,
            jahresverbrauch_kwh=self.jahresverbrauch_kwh,
            netzkosten_eur_jahr=netz,
            netzbetreiber=self.netzbetreiber,
            gebrauchsabgabe_rate=self.gebrauchsabgabe_rate,
            beste_fix=fix_tarife,
            beste_floater=floater_tarife,
            beste_gruen=gruen_tarife,
            bester_gesamt=bester,
            max_ersparnis_eur=round(aktuell_kosten - bester.jahreskosten_eur, 2) if bester else 0.0,
        )
