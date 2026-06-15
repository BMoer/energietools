"""
Austrian electricity grid fees (Netzentgelte) — Energienetze Steiermark.

Source
------
SNE-V 2018 Novelle 2025 (Systemnutzungsentgelte-Verordnung), valid from 01.01.2025.
All Netznutzungsentgelt and Netzdienstleistungsentgelt values are **ex VAT** as
published in the SNE-V. VAT (20%) is added by the utility on the invoice.
Elektrizitätsabgabe (1.50 ct/kWh) is fixed by law and carries no VAT.

Voltage levels (E-Control classification)
------------------------------------------
NE3  — Hochspannung <110 kV (high voltage)
NE4  — Umspannung HS/MS (HV/MV transformer)
NE5  — Mittelspannung <36 kV (medium voltage)
NE6  — Umspannung MS/NS (MV/LV transformer) — typical PV feed-in level
NE7  — Niederspannung <1 kV (low voltage, residential)

NE7 billing variants
---------------------
NE7 nicht gemessen (SLP)  — standard residential load profile (default)
  flat:        9.13 ct/kWh ex VAT (no HT/NT distinction)
  Doppeltarif: HT=9.25 / NT=6.85 ct/kWh ex VAT

NE7 gemessen (load-profile)  — for larger metered consumers (not residential)
  HT=6.98 / NT=6.29 ct/kWh ex VAT

Feed-in vs. consumption
-----------------------
PV systems inject at the MV/LV transformer (NE6), one level above NE7.
User's tariff: feed-in grid fee = 0 EUR/kWh (ne6_eur_kwh = 0.0).

Usage
-----
    fees = AustrianGridFees()          # Steiermark 2025 defaults
    fees.consumption_fee()             # NE7 flat, incl. all components + VAT
    fees.consumption_fee(tou=True)     # Doppeltarif HT, incl. all components + VAT
    fees.consumption_fee(tou=True, peak=False)  # Doppeltarif NT
    fees.feedin_fee()                  # 0.0 (zero per current tariff)
    fees.total_fee_breakdown()         # dict of all cost components
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AustrianGridFees:
    """
    Steiermark 2025 grid fees per voltage level, all ex VAT (SNE-V 2025).

    Call consumption_fee() / feedin_fee() for the fully loaded per-kWh cost
    (Netznutzung + Netzdienstleistung + taxes, incl. VAT).
    """

    # ------------------------------------------------------------------
    # Netznutzungsentgelt — Arbeitspreis per NE level (ct/kWh, ex VAT)
    # ------------------------------------------------------------------
    ne3_eur_kwh: float = 0.0066   # NE3 Steiermark 2025, flat
    ne4_eur_kwh: float = 0.0121   # NE4 Steiermark 2025, flat
    ne5_eur_kwh: float = 0.0192   # NE5 Steiermark 2025, flat
    ne6_eur_kwh: float = 0.0000   # NE6 feed-in: zero per user tariff
                                   # (actual SNE-V: HT=0.0295, NT=0.0230 ex VAT)
    ne7_eur_kwh: float = 0.0913   # NE7 nicht gemessen, flat (SLP), ex VAT
    ne7_ht_eur_kwh: float = 0.0925  # NE7 nicht gem. Doppeltarif HT, ex VAT
    ne7_nt_eur_kwh: float = 0.0685  # NE7 nicht gem. Doppeltarif NT, ex VAT

    # ------------------------------------------------------------------
    # Netzdienstleistungsentgelt per NE level (ct/kWh, ex VAT)
    # ------------------------------------------------------------------
    netzdienstleistung: dict = field(default_factory=lambda: {
        "NE3": 0.00128,
        "NE4": 0.00143,
        "NE5": 0.00151,
        "NE6": 0.00269,
        "NE7": 0.00444,
    })

    # ------------------------------------------------------------------
    # Federal taxes (ex VAT unless noted)
    # ------------------------------------------------------------------
    elektrizitaetsabgabe_eur_kwh: float = 0.0150  # fixed by law, NO VAT
    eap_eur_kwh: float = 0.0010                    # Erneuerbare-Ausbau-Pauschale, +VAT

    # VAT applied to Netznutzung, Netzdienstleistung, EAP
    vat_rate: float = 0.20

    # ------------------------------------------------------------------
    # Installation configuration
    # ------------------------------------------------------------------
    consumption_level: str = "NE7"   # household draws at NE7
    feedin_level: str = "NE6"        # PV injects at NE6

    # Direct override for feed-in grid fee (EUR/kWh, total incl. VAT).
    # Set to 0.0 if your tariff charges no grid fee on exported energy (default).
    # Set to None to compute from feedin_level like a consumption fee (Netznutzung
    # + Netzdienstleistung only — taxes like Elektrizitätsabgabe don't apply to feed-in).
    feedin_total_eur_kwh: float = 0.0

    # EU storage double-charging exemption (§ 17 ElWOG 2010)
    # Batteries > 200 kWh exempt from grid fees on charging energy.
    storage_exemption: bool = False

    # ------------------------------------------------------------------
    # Core: Netznutzungsentgelt lookup (ex VAT)
    # ------------------------------------------------------------------

    def _netznutzung_ex_vat(self, level: str, tou: bool = False, peak: bool = True) -> float:
        """Raw Netznutzungsentgelt in EUR/kWh, ex VAT."""
        level = level.upper()
        mapping = {
            "NE3": self.ne3_eur_kwh,
            "NE4": self.ne4_eur_kwh,
            "NE5": self.ne5_eur_kwh,
            "NE6": self.ne6_eur_kwh,
            "NE7": self.ne7_eur_kwh,
        }
        if level not in mapping:
            raise ValueError(f"Unknown voltage level {level!r}. Use NE3–NE7.")

        if tou and level == "NE7":
            return self.ne7_ht_eur_kwh if peak else self.ne7_nt_eur_kwh
        return mapping[level]

    # ------------------------------------------------------------------
    # Public: total per-kWh cost incl. all components and VAT
    # ------------------------------------------------------------------

    def for_level(self, level: str = "NE7", tou: bool = False, peak: bool = True) -> float:
        """
        Total grid fee in EUR/kWh (Netznutzung + Netzdienstleistung + taxes, incl. VAT).

        Parameters
        ----------
        level : str
            Voltage level: 'NE3', 'NE4', 'NE5', 'NE6', 'NE7'.
        tou : bool
            If True and level='NE7', use Doppeltarif HT or NT rate.
        peak : bool
            True → HT (peak), False → NT (off-peak). Only used when tou=True.
        """
        lv = level.upper()
        netznutzung = self._netznutzung_ex_vat(lv, tou=tou, peak=peak)
        netzdienstleistung = self.netzdienstleistung.get(lv, 0.0)
        # VAT applies to Netznutzung + Netzdienstleistung + EAP
        total = (
            (netznutzung + netzdienstleistung + self.eap_eur_kwh) * (1 + self.vat_rate)
            + self.elektrizitaetsabgabe_eur_kwh  # no VAT
        )
        return round(total, 6)

    def consumption_fee(self, tou: bool = False, peak: bool = True) -> float:
        """Total per-kWh fee for energy drawn from the grid (incl. VAT + taxes)."""
        return self.for_level(self.consumption_level, tou=tou, peak=peak)

    def feedin_fee(self) -> float:
        """
        Per-kWh fee for energy exported to the grid (incl. VAT where applicable).

        Returns feedin_total_eur_kwh directly (default 0.0).
        Note: Elektrizitätsabgabe and EAP are consumption-side taxes and do NOT
        apply to feed-in energy.
        """
        return self.feedin_total_eur_kwh

    def charging_fee(self, tou: bool = False, peak: bool = True) -> float:
        """Grid fee for battery charging energy (0 if storage exemption applies)."""
        if self.storage_exemption:
            return 0.0
        return self.consumption_fee(tou=tou, peak=peak)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def total_fee_breakdown(self, tou: bool = False, peak: bool = True) -> dict:
        """
        Return a dict of all cost components for consumption_level (EUR/kWh, incl. VAT).
        Useful for checking calculations or displaying on a dashboard.
        """
        lv = self.consumption_level.upper()
        netznutzung = self._netznutzung_ex_vat(lv, tou=tou, peak=peak)
        netzdienstleistung = self.netzdienstleistung.get(lv, 0.0)
        return {
            "netznutzung_incl_vat":          round(netznutzung * (1 + self.vat_rate), 6),
            "netzdienstleistung_incl_vat":   round(netzdienstleistung * (1 + self.vat_rate), 6),
            "elektrizitaetsabgabe":           self.elektrizitaetsabgabe_eur_kwh,
            "eap_incl_vat":                  round(self.eap_eur_kwh * (1 + self.vat_rate), 6),
            "total":                          self.consumption_fee(tou=tou, peak=peak),
        }

    def summary(self) -> str:
        """Human-readable summary of this installation's grid fee configuration."""
        b = self.total_fee_breakdown()
        b_ht = self.total_fee_breakdown(tou=True, peak=True)
        b_nt = self.total_fee_breakdown(tou=True, peak=False)
        lines = [
            "Grid fee configuration (Energienetze Steiermark, SNE-V 2025):",
            f"  Consumption : {self.consumption_level}  flat={self.consumption_fee()*100:.3f} ct/kWh  "
            f"HT={b_ht['total']*100:.3f}  NT={b_nt['total']*100:.3f} ct/kWh",
            f"  Feed-in     : {self.feedin_level}  {self.feedin_fee()*100:.3f} ct/kWh  (override)",
            f"  Storage exemption: {self.storage_exemption}",
            "  Breakdown (flat, incl. VAT):",
            f"    Netznutzung:        {b['netznutzung_incl_vat']*100:.3f} ct/kWh",
            f"    Netzdienstleistung: {b['netzdienstleistung_incl_vat']*100:.3f} ct/kWh",
            f"    Elektrizitaetsabg.: {b['elektrizitaetsabgabe']*100:.3f} ct/kWh  (no VAT)",
            f"    EAP:                {b['eap_incl_vat']*100:.3f} ct/kWh",
            f"    Total:              {b['total']*100:.3f} ct/kWh",
        ]
        return "\n".join(lines)
