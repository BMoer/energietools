# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Gas Tariff Comparison — Gas-Tarifvergleich via E-Control rc-public-rest API.

Uses the same rc-public-rest API as tariff_compare.py,
with energyType=GAS and gasRequestOptions instead of firstMeterOptions.
"""

from __future__ import annotations

import logging
import time

import httpx

from energietools.models.gas import GasRechenweg, GasTariff, GasTariffComparison

log = logging.getLogger(__name__)

# Same API as electricity — reverse-engineered from /o/rc-public-portlet JS bundle
_BASE_URL = "https://www.e-control.at/o/rc-public-rest"
_PAGE_URL = "https://www.e-control.at/tarifkalkulator"

_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 2

# Placeholder/test tariffs to filter out
_BLOCKED_TARIF_NAMES = {"Ihr Produkt"}
_BLOCKED_LIEFERANTEN = {"Ihre Marke"}

_FLOATER_KEYWORDS = {"floater", "flex", "float", "monatsfloater", "variable"}


def _request_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    **kwargs: object,
) -> httpx.Response:
    """HTTP-Request mit Retry und exponentiellem Backoff."""
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
                    "E-Control Gas-Anfrage fehlgeschlagen (Versuch %d/%d): %s — warte %ds",
                    attempt + 1, _MAX_RETRIES, exc, wait,
                )
                time.sleep(wait)
            else:
                log.error(
                    "E-Control Gas-Anfrage endgültig fehlgeschlagen nach %d Versuchen: %s",
                    _MAX_RETRIES, exc,
                )
    raise last_exc  # type: ignore[misc]


def _detect_tariftyp(name: str) -> str:
    """Tariftyp aus dem Tarifnamen erkennen."""
    lower = name.lower()
    if any(kw in lower for kw in _FLOATER_KEYWORDS):
        return "Monatsfloater"
    return "Fixpreis"


def compare_gas_tariffs(
    plz: str,
    jahresverbrauch_kwh: float = 15000.0,
    aktueller_tarif: dict | None = None,
) -> GasTariffComparison:
    """Gas-Tarife für eine PLZ vergleichen via E-Control rc-public-rest API.

    Args:
        plz: Postleitzahl.
        jahresverbrauch_kwh: Jährlicher Gasverbrauch in kWh.
        aktueller_tarif: Optionaler aktueller Tarif
            {anbieter, tarif_name, gaspreis_ct_kwh, grundgebuehr_eur_monat}.

    Returns:
        GasTariffComparison mit Tarifliste, Netzkosten und Empfehlung.
    """
    # Build current tariff for comparison
    current = None
    current_gaspreis_netto = 0.0
    current_grundgebuehr_netto = 0.0

    if aktueller_tarif:
        gaspreis_brutto = aktueller_tarif.get("gaspreis_ct_kwh", 0)
        grund_brutto = aktueller_tarif.get("grundgebuehr_eur_monat", 0)
        current_gaspreis_netto = gaspreis_brutto / 1.2
        current_grundgebuehr_netto = grund_brutto / 1.2

    try:
        result = _fetch_gas_tariffs_econtrol(
            plz, jahresverbrauch_kwh,
            current_gaspreis_netto, current_grundgebuehr_netto,
        )
    except Exception as e:
        log.error("E-Control Gas-Abfrage fehlgeschlagen: %s", e)
        # Fallback: return empty comparison
        if aktueller_tarif:
            gaspreis = aktueller_tarif.get("gaspreis_ct_kwh", 0)
            grund = aktueller_tarif.get("grundgebuehr_eur_monat", 0)
            jk = (jahresverbrauch_kwh * gaspreis / 100) + (grund * 12)
            current = GasTariff(
                anbieter=aktueller_tarif.get("anbieter", ""),
                tarif_name=aktueller_tarif.get("tarif_name", "Aktueller Tarif"),
                gaspreis_ct_kwh=gaspreis,
                grundgebuehr_eur_monat=grund,
                jahreskosten_eur=round(jk, 2),
                quelle="rechnung",
            )
        return GasTariffComparison(
            plz=plz,
            jahresverbrauch_kwh=jahresverbrauch_kwh,
            aktueller_tarif=current,
        )

    # Calculate current tariff costs with Gebrauchsabgabe (like E-Control does)
    gab = result["gebrauchsabgabe_rate"]
    if aktueller_tarif:
        netto_e = jahresverbrauch_kwh * current_gaspreis_netto / 100.0
        netto_g = current_grundgebuehr_netto * 12.0
        netto_ges = netto_e + netto_g
        gab_eur = netto_ges * gab
        co2_eur = result.get("co2_rate", 0.0) * jahresverbrauch_kwh / 100.0
        netto_inkl = netto_ges + gab_eur + co2_eur
        ust = netto_inkl * 0.2
        jk = netto_inkl + ust

        current = GasTariff(
            anbieter=aktueller_tarif.get("anbieter", ""),
            tarif_name=aktueller_tarif.get("tarif_name", "Aktueller Tarif"),
            gaspreis_ct_kwh=aktueller_tarif.get("gaspreis_ct_kwh", 0),
            grundgebuehr_eur_monat=aktueller_tarif.get("grundgebuehr_eur_monat", 0),
            jahreskosten_eur=round(jk, 2),
            quelle="rechnung",
            rechenweg=GasRechenweg(
                gaspreis_netto_ct_kwh=round(current_gaspreis_netto, 4),
                grundgebuehr_netto_eur_monat=round(current_grundgebuehr_netto, 2),
                netto_energie_eur=round(netto_e, 2),
                netto_grund_eur=round(netto_g, 2),
                netto_gesamt_eur=round(netto_ges, 2),
                co2_bepreisung_eur=round(co2_eur, 2),
                gebrauchsabgabe_rate=gab,
                gebrauchsabgabe_eur=round(gab_eur, 2),
                netto_inkl_abgaben_eur=round(netto_inkl, 2),
                ust_eur=round(ust, 2),
                brutto_jahreskosten_eur=round(jk, 2),
                quelle="berechnet",
            ),
        )

    # Parse alternatives
    alternativen: list[GasTariff] = []
    for raw in result["tarife"]:
        tarif = _parse_gas_tariff(raw, jahresverbrauch_kwh, gab)
        if tarif and tarif.jahreskosten_eur > 0:
            if tarif.tarif_name in _BLOCKED_TARIF_NAMES:
                continue
            if tarif.anbieter.strip() in _BLOCKED_LIEFERANTEN:
                continue
            alternativen.append(tarif)

    alternativen.sort(key=lambda t: t.jahreskosten_eur)
    alternativen = alternativen[:20]

    # Calculate savings vs current
    if current:
        for t in alternativen:
            t.ersparnis_eur = round(current.jahreskosten_eur - t.jahreskosten_eur, 2)

    return GasTariffComparison(
        plz=plz,
        jahresverbrauch_kwh=jahresverbrauch_kwh,
        tarife=alternativen,
        aktueller_tarif=current,
        netzkosten_eur_jahr=result["netzkosten_eur_jahr"],
        netzbetreiber=result["netzbetreiber"],
        gebrauchsabgabe_rate=gab,
    )


def _fetch_gas_tariffs_econtrol(
    plz: str,
    jahresverbrauch_kwh: float,
    aktueller_gaspreis_netto_ct: float,
    aktuelle_grundgebuehr_netto_eur_monat: float,
) -> dict:
    """Gas-Tarife vom E-Control rc-public-rest API holen."""
    with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
        # Session-Cookie (Liferay)
        client.get(_PAGE_URL)

        # Step 1: Grid operator for GAS
        log.info("Ermittle Gas-Netzbetreiber für PLZ %s", plz)
        grid_response = _request_with_retry(
            client, "GET",
            f"{_BASE_URL}/rate-calculator/grid-operators",
            params={"zipCode": plz, "energyType": "GAS"},
        )
        grid_data = grid_response.json()
        operators = grid_data.get("gridOperators", [])

        if not operators:
            raise ValueError(f"Kein Gas-Netzbetreiber für PLZ {plz} gefunden")

        operator = operators[0]
        grid_operator_id = operator["id"]
        grid_area_id = operator["gridAreaId"]
        netzbetreiber = operator.get("name", "Unbekannt")
        log.info("Gas-Netzbetreiber: %s (ID=%s)", netzbetreiber, grid_operator_id)

        # Step 2: Gas tariffs — uses gasRequestOptions (not firstMeterOptions!)
        payload: dict = {
            "customerGroup": "HOME",
            "energyType": "GAS",
            "zipCode": plz,
            "gridOperatorId": grid_operator_id,
            "gridAreaId": grid_area_id,
            "moveHome": False,
            "includeSwitchingDiscounts": True,
            "gasRequestOptions": {
                "annualConsumption": int(jahresverbrauch_kwh),
            },
            "priceView": "EUR_PER_YEAR",
            "referencePeriod": "ONE_YEAR",
        }

        # comparisonOptions required by API — use current tariff or sensible defaults
        if aktueller_gaspreis_netto_ct > 0:
            payload["comparisonOptions"] = {
                "manualEntry": True,
                "mainBaseRate": aktuelle_grundgebuehr_netto_eur_monat,
                "mainEnergyRate": aktueller_gaspreis_netto_ct,
            }
        else:
            # Default: ~7 ct/kWh netto (~8.4 brutto), ~3 EUR/Mo netto
            payload["comparisonOptions"] = {
                "manualEntry": True,
                "mainBaseRate": 2.5,
                "mainEnergyRate": 7.0,
            }

        log.info("Frage Gas-Tarife ab: PLZ=%s, Verbrauch=%d kWh", plz, jahresverbrauch_kwh)
        tarif_response = _request_with_retry(
            client, "POST",
            f"{_BASE_URL}/rate-calculator/energy-type/GAS/rate",
            json=payload,
            params={"isSmartMeter": False},
        )
        data = tarif_response.json()
        raw_tarife = data.get("ratedProducts", [])
        log.info("Got %d gas tariffs from E-Control", len(raw_tarife))

        # Extract grid costs & fees from first product
        netzkosten = 0.0
        gebrauchsabgabe_rate = 0.0
        co2_rate = 0.0
        if raw_tarife:
            grid_costs = raw_tarife[0].get("calculatedGridCosts", {})
            netzkosten = grid_costs.get("totalGrossSum", 0.0) / 100.0

            energy_costs = raw_tarife[0].get("calculatedProductEnergyCosts", {})
            for fee in energy_costs.get("calculatedFees", []):
                if fee.get("appliedToEnergyRate"):
                    gebrauchsabgabe_rate = fee.get("proportionalRate", 0.0)
                elif "CO2" in fee.get("name", ""):
                    # CO2 pricing is a fixed fee, extract rate per kWh
                    co2_value = fee.get("value", 0.0) / 100.0  # cents to EUR
                    if jahresverbrauch_kwh > 0:
                        co2_rate = co2_value / jahresverbrauch_kwh * 100  # EUR to ct/kWh

        return {
            "tarife": raw_tarife,
            "netzbetreiber": netzbetreiber,
            "netzkosten_eur_jahr": round(netzkosten, 2),
            "gebrauchsabgabe_rate": gebrauchsabgabe_rate,
            "co2_rate": co2_rate,
        }


def _parse_gas_tariff(
    raw: dict,
    jahresverbrauch_kwh: float,
    gebrauchsabgabe_rate: float,
) -> GasTariff | None:
    """E-Control ratedProduct → GasTariff."""
    try:
        tarif_name = raw.get("productName", "")
        lieferant = raw.get("supplierName") or raw.get("brandName") or ""

        # E-Control annualGrossRate for GAS includes grid costs!
        # We need energy-only costs: (netto_energy + fees - discounts) * 1.2
        energy_costs = raw.get("calculatedProductEnergyCosts", {})
        energy_rate_total_cents = energy_costs.get("energyRateTotal", 0.0)
        base_rate_cents = energy_costs.get("baseRate", 0.0)
        fee_net_sum_cents = energy_costs.get("productFeeNetSum", 0.0)
        discount_net_sum_cents = energy_costs.get("discountNetSum", 0.0)

        # Netto values
        netto_energie = energy_rate_total_cents / 100.0
        netto_grund = base_rate_cents / 100.0
        netto_gesamt = netto_energie + netto_grund

        # Fees (CO2, Gebrauchsabgabe, etc.)
        co2_eur = 0.0
        gab_eur = 0.0
        for fee in energy_costs.get("calculatedFees", []):
            if fee.get("appliedToEnergyRate"):
                gab_eur = fee.get("value", 0.0) / 100.0
            elif "CO2" in fee.get("name", ""):
                co2_eur = fee.get("value", 0.0) / 100.0

        # Energy-only costs (excluding grid/Netzkosten)
        netto_inkl_fees = netto_gesamt + fee_net_sum_cents / 100.0 - discount_net_sum_cents / 100.0
        jahreskosten = netto_inkl_fees * 1.2  # brutto, energy only

        if jahreskosten <= 0:
            return None

        # Calculate brutto prices for display
        if jahresverbrauch_kwh > 0:
            gaspreis_netto = energy_rate_total_cents / jahresverbrauch_kwh  # ct/kWh netto
            gaspreis_brutto = gaspreis_netto * 1.2
        else:
            gaspreis_brutto = 0.0
            gaspreis_netto = 0.0

        grundgebuehr_netto_monat = netto_grund / 12.0
        grundgebuehr_brutto_monat = grundgebuehr_netto_monat * 1.2

        # Biogas detection
        ist_biogas = any(
            prop.get("propName") in ("CERTIFIED_GREEN_GAS", "BIO_GAS", "GREEN_GAS")
            for prop in raw.get("productProperties", [])
        )

        tariftyp = _detect_tariftyp(tarif_name)

        rechenweg = GasRechenweg(
            gaspreis_netto_ct_kwh=round(gaspreis_netto, 4),
            grundgebuehr_netto_eur_monat=round(grundgebuehr_netto_monat, 2),
            netto_energie_eur=round(netto_energie, 2),
            netto_grund_eur=round(netto_grund, 2),
            netto_gesamt_eur=round(netto_gesamt, 2),
            co2_bepreisung_eur=round(co2_eur, 2),
            gebrauchsabgabe_rate=gebrauchsabgabe_rate,
            gebrauchsabgabe_eur=round(gab_eur, 2),
            netto_inkl_abgaben_eur=round(netto_gesamt + co2_eur + gab_eur, 2),
            ust_eur=round(jahreskosten - (netto_gesamt + co2_eur + gab_eur), 2),
            brutto_jahreskosten_eur=round(jahreskosten, 2),
            quelle="e-control-api",
        )

        return GasTariff(
            anbieter=lieferant,
            tarif_name=tarif_name,
            gaspreis_ct_kwh=round(gaspreis_brutto, 2),
            grundgebuehr_eur_monat=round(grundgebuehr_brutto_monat, 2),
            jahreskosten_eur=round(jahreskosten, 2),
            ist_biogas=ist_biogas,
            tariftyp=tariftyp,
            quelle="e-control",
            rechenweg=rechenweg,
        )
    except (KeyError, TypeError, ZeroDivisionError) as e:
        log.warning("Gas-Tarif konnte nicht geparst werden: %s — %s", e, raw.get("productName", "?"))
        return None
