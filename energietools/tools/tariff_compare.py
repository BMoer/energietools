# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tarifvergleich via E-Control Tarifkalkulator (neue Portlet-API 2025+)."""

from __future__ import annotations

import logging
import time

import httpx

from energietools.models import Tariff, TariffComparison

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

    __slots__ = ("tarife", "netzbetreiber", "netzkosten_eur_jahr")

    def __init__(
        self,
        tarife: list[dict],
        netzbetreiber: str,
        netzkosten_eur_jahr: float,
    ) -> None:
        self.tarife = tarife
        self.netzbetreiber = netzbetreiber
        self.netzkosten_eur_jahr = netzkosten_eur_jahr


def _fetch_tariffs_econtrol(
    plz: str,
    jahresverbrauch_kwh: float,
    aktueller_energiepreis_ct: float,
    aktuelle_grundgebuehr_eur_monat: float,
) -> _EControlResult:
    """Tarife vom E-Control Tarifkalkulator holen (neue API)."""
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
                "mainBaseRate": aktuelle_grundgebuehr_eur_monat,
                "mainEnergyRate": aktueller_energiepreis_ct,
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
        if raw_tarife:
            grid_costs = raw_tarife[0].get("calculatedGridCosts", {})
            netzkosten = grid_costs.get("totalGrossSum", 0.0) / 100.0

        return _EControlResult(
            tarife=raw_tarife,
            netzbetreiber=netzbetreiber_name,
            netzkosten_eur_jahr=round(netzkosten, 2),
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


def _parse_tariff(raw: dict, jahresverbrauch_kwh: float) -> Tariff | None:
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

        # → Brutto-Energiepreis ct/kWh (for display)
        if jahresverbrauch_kwh > 0 and energy_netto_cent > 0:
            energiepreis = energy_netto_cent / jahresverbrauch_kwh * 1.2
        else:
            energiepreis = 0.0

        # → Brutto-Grundgebühr EUR/Monat (for display)
        grundgebuehr_monat = base_netto_cent_year / 100.0 / 12.0 * 1.2

        # Jahreskosten: prefer totalGrossSum (includes Gebrauchsabgabe + USt)
        # to match E-Control's displayed numbers exactly.
        total_gross_cent = energy_costs.get("totalGrossSum", 0.0)
        if total_gross_cent > 0:
            jahreskosten = total_gross_cent / 100.0
        else:
            # Fallback: manual calculation (misses Gebrauchsabgabe)
            jahreskosten = (
                jahresverbrauch_kwh * energiepreis / 100.0
                + grundgebuehr_monat * 12.0
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
    """Vergleiche aktuellen Tarif gegen E-Control Alternativen."""

    # Aktuellen Tarif als Referenz aufbauen
    aktuelle_jahreskosten = (
        jahresverbrauch_kwh * aktueller_energiepreis / 100
        + aktuelle_grundgebuehr * 12
    )
    aktueller_tarif = Tariff(
        lieferant=aktueller_lieferant,
        tarif_name="Aktueller Tarif",
        energiepreis_ct_kwh=aktueller_energiepreis,
        grundgebuehr_eur_monat=aktuelle_grundgebuehr,
        jahreskosten_eur=aktuelle_jahreskosten,
        quelle="rechnung",
    )

    try:
        result = _fetch_tariffs_econtrol(
            plz, jahresverbrauch_kwh,
            aktueller_energiepreis, aktuelle_grundgebuehr,
        )
    except Exception as e:
        log.error("E-Control Abfrage fehlgeschlagen: %s", e)
        return TariffComparison(
            aktueller_tarif=aktueller_tarif,
            plz=plz,
            jahresverbrauch_kwh=jahresverbrauch_kwh,
        )

    alternativen: list[Tariff] = []
    for raw in result.tarife:
        tarif = _parse_tariff(raw, jahresverbrauch_kwh)
        if tarif and tarif.jahreskosten_eur > 0:
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
    )
    return comparison.enrich()
