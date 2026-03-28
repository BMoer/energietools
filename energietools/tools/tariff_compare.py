# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tarifvergleich via E-Control Tarifkalkulator (neue Portlet-API 2025+)."""

from __future__ import annotations

import logging
import time

import httpx

from energietools.models import Rechenweg, Tariff, TariffComparison

log = logging.getLogger(__name__)

# E-Control neue API — Liferay-Portlet auf www.e-control.at
# Reverse-engineered aus /o/rc-public-portlet JS-Bundle
_BASE_URL = "https://www.e-control.at/o/rc-public-rest"
_PAGE_URL = "https://www.e-control.at/tarifkalkulator"

# Timeout & Retry
_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 2  # Sekunden: 2, 4, 8...


def _request_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    **kwargs: object,
) -> httpx.Response:
    """HTTP-Request mit Retry und exponentiellem Backoff bei transienten Fehlern."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = client.request(method, url, **kwargs)
            if response.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"Server error {response.status_code}",
                    request=response.request,
                    response=response,
                )
            response.raise_for_status()
            return response
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES - 1:
                wait = _RETRY_BACKOFF_BASE ** (attempt + 1)
                log.warning(
                    "E-Control Anfrage fehlgeschlagen (Versuch %d/%d): %s — warte %ds",
                    attempt + 1, _MAX_RETRIES, exc, wait,
                )
                time.sleep(wait)
            else:
                log.error(
                    "E-Control Anfrage endgültig fehlgeschlagen nach %d Versuchen: %s",
                    _MAX_RETRIES, exc,
                )
    raise last_exc  # type: ignore[misc]


class _EControlResult:
    """Ergebnis der E-Control Abfrage inkl. Metadaten."""

    __slots__ = (
        "tarife", "netzbetreiber", "netzkosten_eur_jahr",
        "gebrauchsabgabe_rate", "baseline_total_eur",
    )

    def __init__(
        self,
        tarife: list[dict],
        netzbetreiber: str,
        netzkosten_eur_jahr: float,
        gebrauchsabgabe_rate: float = 0.0,
        baseline_total_eur: float = 0.0,
    ) -> None:
        self.tarife = tarife
        self.netzbetreiber = netzbetreiber
        self.netzkosten_eur_jahr = netzkosten_eur_jahr
        self.gebrauchsabgabe_rate = gebrauchsabgabe_rate
        self.baseline_total_eur = baseline_total_eur


def _fetch_tariffs_econtrol(
    plz: str,
    jahresverbrauch_kwh: float,
    aktueller_energiepreis_netto_ct: float,
    aktuelle_grundgebuehr_netto_eur_monat: float,
) -> _EControlResult:
    """Tarife vom E-Control Tarifkalkulator holen (neue API).

    Alle Eingabewerte sind NETTO (ohne USt) — so wie E-Control sie erwartet.
    """
    with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
        # Session-Cookie holen (Liferay braucht das)
        client.get(_PAGE_URL)

        # Step 1: Netzbetreiber + gridAreaId für PLZ ermitteln
        log.info("Ermittle Netzbetreiber für PLZ %s", plz)
        grid_response = _request_with_retry(
            client, "GET",
            f"{_BASE_URL}/rate-calculator/grid-operators",
            params={"zipCode": plz, "energyType": "POWER"},
        )
        grid_data = grid_response.json()
        operators = grid_data.get("gridOperators", [])

        if not operators:
            raise ValueError(f"Kein Netzbetreiber für PLZ {plz} gefunden")

        operator = operators[0]
        grid_operator_id = operator["id"]
        grid_area_id = operator["gridAreaId"]
        netzbetreiber_name = operator.get("name", "Unbekannt")
        log.info(
            "Netzbetreiber: %s (ID=%s, GridArea=%s)",
            netzbetreiber_name, grid_operator_id, grid_area_id,
        )

        # Step 2: Tarife abfragen
        log.info(
            "Frage Tarife ab: PLZ=%s, Verbrauch=%d kWh",
            plz, jahresverbrauch_kwh,
        )
        payload = {
            "customerGroup": "HOME",
            "energyType": "POWER",
            "zipCode": plz,
            "gridOperatorId": grid_operator_id,
            "gridAreaId": grid_area_id,
            "moveHome": False,
            "includeSwitchingDiscounts": True,
            "firstMeterOptions": {
                "standardConsumption": int(jahresverbrauch_kwh),
                "smartMeterRequestOptions": {"smartMeterSearch": False},
            },
            "comparisonOptions": {
                "manualEntry": True,
                "mainBaseRate": aktuelle_grundgebuehr_netto_eur_monat,
                "mainEnergyRate": aktueller_energiepreis_netto_ct,
            },
            "priceView": "EUR_PER_YEAR",
            "referencePeriod": "ONE_YEAR",
            "searchPriceModel": "CLASSIC",
        }
        tarif_response = _request_with_retry(
            client, "POST",
            f"{_BASE_URL}/rate-calculator/energy-type/POWER/rate",
            json=payload,
            params={"isSmartMeter": False},
        )
        data = tarif_response.json()
        raw_tarife = data.get("ratedProducts", [])

        # Netzkosten aus erstem Tarif extrahieren (für alle Anbieter gleich)
        netzkosten = 0.0
        gebrauchsabgabe_rate = 0.0
        if raw_tarife:
            grid_costs = raw_tarife[0].get("calculatedGridCosts", {})
            netzkosten = grid_costs.get("totalGrossSum", 0.0) / 100.0

            # Gebrauchsabgabe-Satz aus den Gebühren extrahieren
            # (z.B. Wien: 7%, variiert je nach Gemeinde)
            energy_costs = raw_tarife[0].get("calculatedProductEnergyCosts", {})
            for fee in energy_costs.get("calculatedFees", []):
                if fee.get("appliedToEnergyRate"):
                    gebrauchsabgabe_rate = fee.get("proportionalRate", 0.0)
                    break

        # Baseline-Gesamtkosten von E-Control berechnen lassen
        # annualRateRange.to minus annualRateRange.from = Spread;
        # Ein Tarif mit annualSaving > 0 → Baseline = annualGrossRate + annualSaving
        baseline_total = 0.0
        for raw in raw_tarife:
            saving_cent = raw.get("annualSaving", 0.0)
            if saving_cent > 0:
                gross_cent = raw.get("annualGrossRate", 0.0)
                baseline_total = (gross_cent + saving_cent) / 100.0
                break

        return _EControlResult(
            tarife=raw_tarife,
            netzbetreiber=netzbetreiber_name,
            netzkosten_eur_jahr=round(netzkosten, 2),
            gebrauchsabgabe_rate=gebrauchsabgabe_rate,
            baseline_total_eur=round(baseline_total, 2),
        )


_FLOATER_KEYWORDS = {"floater", "flex", "float", "monatsfloater", "variable"}
_SPOT_KEYWORDS = {"spot", "stundenfloater", "hourly", "dynamic", "dynamisch"}


def _detect_tariftyp(tarif_name: str) -> str:
    """Detect tariff type from product name (API provides no structured field)."""
    name_lower = tarif_name.lower()
    if any(kw in name_lower for kw in _SPOT_KEYWORDS):
        return "Stundenfloater"
    if any(kw in name_lower for kw in _FLOATER_KEYWORDS):
        return "Monatsfloater"
    return "Fixpreis"


def _parse_tariff(
    raw: dict, jahresverbrauch_kwh: float, gebrauchsabgabe_rate: float = 0.0,
) -> Tariff | None:
    """Einen einzelnen Tarif aus der neuen E-Control API parsen.

    Die API liefert Netto-Cent-Werte. energietools arbeitet mit Brutto (inkl. 20% MwSt).
    Wir nutzen totalGrossSum (inkl. Abgaben + USt) als Jahreskosten, damit die
    Zahlen exakt mit dem E-Control Tarifkalkulator übereinstimmen.
    """
    try:
        # Spotmarkt-/Dynamik-Tarife haben keinen festen Energiepreis → überspringen
        if raw.get("rateZoningType") == "COMPLEX":
            return None

        lieferant = raw.get("brandName", raw.get("supplierName", "Unbekannt"))
        tarif_name = raw.get("productName", "")

        energy_costs = raw.get("calculatedProductEnergyCosts", {})

        # energyRateTotal = Netto-Energiekosten in Cent (Verbrauch × Netto-ct/kWh)
        energy_netto_cent = energy_costs.get("energyRateTotal", 0.0)
        # baseRate = Netto-Grundgebühr in Cent/Jahr
        base_netto_cent_year = energy_costs.get("baseRate", 0.0)

        # Netto-Werte für Rechenweg
        netto_ep_ct = energy_netto_cent / jahresverbrauch_kwh if jahresverbrauch_kwh > 0 else 0.0
        netto_gg_eur_monat = base_netto_cent_year / 100.0 / 12.0
        netto_energie_eur = energy_netto_cent / 100.0
        netto_grund_eur = base_netto_cent_year / 100.0
        netto_gesamt = netto_energie_eur + netto_grund_eur

        # → Brutto-Energiepreis ct/kWh (for display)
        energiepreis = netto_ep_ct * 1.2 if netto_ep_ct > 0 else 0.0

        # → Brutto-Grundgebühr EUR/Monat (for display)
        grundgebuehr_monat = netto_gg_eur_monat * 1.2

        # Jahreskosten: prefer totalGrossSum (includes Gebrauchsabgabe + USt)
        # to match E-Control's displayed numbers exactly.
        total_gross_cent = energy_costs.get("totalGrossSum", 0.0)
        hinweis = ""
        if total_gross_cent > 0:
            jahreskosten = total_gross_cent / 100.0
            rw_quelle = "e-control-api"
        else:
            # Fallback: Berechnung mit GAB (wenn bekannt)
            if gebrauchsabgabe_rate > 0:
                jahreskosten = netto_gesamt * (1.0 + gebrauchsabgabe_rate) * 1.2
                rw_quelle = "berechnet"
                hinweis = "totalGrossSum nicht verfügbar, mit GAB-Formel berechnet"
            else:
                # Letzter Fallback: ohne GAB
                jahreskosten = netto_gesamt * 1.2
                rw_quelle = "berechnet"
                hinweis = "totalGrossSum und Gebrauchsabgabe nicht verfügbar"

        # Gebrauchsabgabe aus Jahreskosten rückrechnen
        gab_eur = netto_gesamt * gebrauchsabgabe_rate
        netto_inkl_gab = netto_gesamt + gab_eur
        ust_eur = netto_inkl_gab * 0.2

        rechenweg = Rechenweg(
            energiepreis_netto_ct_kwh=round(netto_ep_ct, 4),
            grundgebuehr_netto_eur_monat=round(netto_gg_eur_monat, 2),
            netto_energie_eur=round(netto_energie_eur, 2),
            netto_grund_eur=round(netto_grund_eur, 2),
            netto_gesamt_eur=round(netto_gesamt, 2),
            gebrauchsabgabe_rate=gebrauchsabgabe_rate,
            gebrauchsabgabe_eur=round(gab_eur, 2),
            netto_inkl_gab_eur=round(netto_inkl_gab, 2),
            ust_eur=round(ust_eur, 2),
            brutto_jahreskosten_eur=round(jahreskosten, 2),
            quelle=rw_quelle,
            hinweis=hinweis,
        )

        # Ökostrom
        oekostrom = any(
            prop.get("propName") == "CERTIFIED_GREEN_POWER"
            for prop in raw.get("productProperties", [])
        )

        if jahreskosten <= 0:
            return None

        tariftyp = _detect_tariftyp(tarif_name)

        return Tariff(
            lieferant=lieferant,
            tarif_name=tarif_name,
            energiepreis_ct_kwh=round(energiepreis, 2),
            grundgebuehr_eur_monat=round(grundgebuehr_monat, 2),
            jahreskosten_eur=round(jahreskosten, 2),
            ist_oekostrom=oekostrom,
            tariftyp=tariftyp,
            quelle="e-control",
            rechenweg=rechenweg,
        )
    except (KeyError, TypeError, ZeroDivisionError) as e:
        log.warning("Tarif konnte nicht geparst werden: %s — %s", e, raw.get("productName", "?"))
        return None


def compare_tariffs(
    plz: str,
    jahresverbrauch_kwh: float,
    aktueller_lieferant: str,
    aktueller_energiepreis: float,
    aktuelle_grundgebuehr: float,
    top_n: int = 20,
) -> TariffComparison:
    """Vergleiche aktuellen Tarif gegen E-Control Alternativen.

    Alle Preise sind BRUTTO (inkl. 20% USt).
    - aktueller_energiepreis: Brutto ct/kWh
    - aktuelle_grundgebuehr: Brutto EUR/Monat
    """

    # Netto-Werte für E-Control API (erwartet netto)
    energiepreis_netto_ct = aktueller_energiepreis / 1.2
    grundgebuehr_netto_eur = aktuelle_grundgebuehr / 1.2

    try:
        result = _fetch_tariffs_econtrol(
            plz, jahresverbrauch_kwh,
            energiepreis_netto_ct, grundgebuehr_netto_eur,
        )
    except Exception as e:
        log.error("E-Control Abfrage fehlgeschlagen: %s", e)
        # Fallback: simple calculation without Gebrauchsabgabe (GAB unknown)
        netto_e = jahresverbrauch_kwh * energiepreis_netto_ct / 100.0
        netto_g = grundgebuehr_netto_eur * 12.0
        netto_ges = netto_e + netto_g
        aktuelle_jahreskosten = netto_ges * 1.2  # ohne GAB — kein API-Zugriff
        fallback_rw = Rechenweg(
            energiepreis_netto_ct_kwh=round(energiepreis_netto_ct, 4),
            grundgebuehr_netto_eur_monat=round(grundgebuehr_netto_eur, 2),
            netto_energie_eur=round(netto_e, 2),
            netto_grund_eur=round(netto_g, 2),
            netto_gesamt_eur=round(netto_ges, 2),
            gebrauchsabgabe_rate=0.0,
            gebrauchsabgabe_eur=0.0,
            netto_inkl_gab_eur=round(netto_ges, 2),
            ust_eur=round(netto_ges * 0.2, 2),
            brutto_jahreskosten_eur=round(aktuelle_jahreskosten, 2),
            quelle="berechnet",
            hinweis="E-Control nicht erreichbar — Gebrauchsabgabe unbekannt, nicht enthalten",
        )
        aktueller_tarif = Tariff(
            lieferant=aktueller_lieferant,
            tarif_name="Aktueller Tarif",
            energiepreis_ct_kwh=aktueller_energiepreis,
            grundgebuehr_eur_monat=aktuelle_grundgebuehr,
            jahreskosten_eur=round(aktuelle_jahreskosten, 2),
            quelle="rechnung",
            rechenweg=fallback_rw,
        )
        return TariffComparison(
            aktueller_tarif=aktueller_tarif,
            plz=plz,
            jahresverbrauch_kwh=jahresverbrauch_kwh,
        )

    # Aktuellen Tarif berechnen — inkl. Gebrauchsabgabe (wie E-Control)
    # Formel: (Netto-Energie + Netto-Grundgebühr) × (1 + Gebrauchsabgabe) × (1 + USt)
    gab = result.gebrauchsabgabe_rate  # z.B. 0.07 für Wien
    netto_energie = jahresverbrauch_kwh * energiepreis_netto_ct / 100.0
    netto_grund = grundgebuehr_netto_eur * 12.0
    netto_gesamt = netto_energie + netto_grund
    gab_eur = netto_gesamt * gab
    netto_inkl_gab = netto_gesamt + gab_eur
    ust_eur = netto_inkl_gab * 0.2
    aktuelle_jahreskosten = netto_inkl_gab * 1.2

    # Log baseline comparison for debugging (but NEVER override our calculation)
    if result.baseline_total_eur > 0:
        baseline_energy = result.baseline_total_eur - result.netzkosten_eur_jahr
        diff = abs(aktuelle_jahreskosten - baseline_energy)
        if diff > 5.0:
            log.warning(
                "Baseline-Abweichung: GAB-Formel=%.2f EUR, E-Control-Baseline=%.2f EUR "
                "(Diff=%.2f EUR). Verwende GAB-Formel (konsistent mit Alternativ-Tarifen).",
                aktuelle_jahreskosten, baseline_energy, diff,
            )
        else:
            log.info(
                "Baseline verifiziert: GAB-Formel=%.2f EUR ≈ E-Control=%.2f EUR (Diff=%.2f)",
                aktuelle_jahreskosten, baseline_energy, diff,
            )

    aktuell_rechenweg = Rechenweg(
        energiepreis_netto_ct_kwh=round(energiepreis_netto_ct, 4),
        grundgebuehr_netto_eur_monat=round(grundgebuehr_netto_eur, 2),
        netto_energie_eur=round(netto_energie, 2),
        netto_grund_eur=round(netto_grund, 2),
        netto_gesamt_eur=round(netto_gesamt, 2),
        gebrauchsabgabe_rate=gab,
        gebrauchsabgabe_eur=round(gab_eur, 2),
        netto_inkl_gab_eur=round(netto_inkl_gab, 2),
        ust_eur=round(ust_eur, 2),
        brutto_jahreskosten_eur=round(aktuelle_jahreskosten, 2),
        quelle="berechnet",
    )

    aktueller_tarif = Tariff(
        lieferant=aktueller_lieferant,
        tarif_name="Aktueller Tarif",
        energiepreis_ct_kwh=aktueller_energiepreis,
        grundgebuehr_eur_monat=aktuelle_grundgebuehr,
        jahreskosten_eur=round(aktuelle_jahreskosten, 2),
        quelle="rechnung",
        rechenweg=aktuell_rechenweg,
    )

    # Placeholder/test tariffs in E-Control database to filter out
    _BLOCKED_TARIF_NAMES = {"Ihr Produkt"}
    _BLOCKED_LIEFERANTEN = {"Ihre Marke"}

    alternativen: list[Tariff] = []
    for raw in result.tarife:
        tarif = _parse_tariff(raw, jahresverbrauch_kwh, gab)
        if tarif and tarif.jahreskosten_eur > 0:
            if tarif.tarif_name in _BLOCKED_TARIF_NAMES:
                log.info("Filtered test tariff: %s — %s", tarif.lieferant, tarif.tarif_name)
                continue
            if tarif.lieferant.strip() in _BLOCKED_LIEFERANTEN:
                log.info("Filtered test provider: %s — %s", tarif.lieferant, tarif.tarif_name)
                continue
            alternativen.append(tarif)

    # Sortiere nach Jahreskosten, Top N
    alternativen.sort(key=lambda t: t.jahreskosten_eur)
    alternativen = alternativen[:top_n]

    # Build comparison and enrich with savings, categories, sorted lists
    comparison = TariffComparison(
        aktueller_tarif=aktueller_tarif,
        alternativen=alternativen,
        plz=plz,
        jahresverbrauch_kwh=jahresverbrauch_kwh,
        netzkosten_eur_jahr=result.netzkosten_eur_jahr,
        netzbetreiber=result.netzbetreiber,
        gebrauchsabgabe_rate=gab,
    )
    return comparison.enrich()
