# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Energy News & Impact Monitor — Nachrichten, Preise, Förderungen.

Three pillars:
1. Geopolitics & Markets — RSS feeds + Claude summarization
2. Spot & Wholesale Prices — ENTSO-E price alerts
3. Förderungen & Subsidies — Curated JSON catalog filtered by user profile
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime

import defusedxml.ElementTree as ET
import httpx

from energietools.capabilities.foerderungen.data import load_foerderungen, load_manifest
from energietools.capabilities.foerderungen.models import FoerderungEntry
from energietools.models.energy_news import (
    EnergyMonitorResult,
    EnergyNewsItem,
    Foerderung,
)

log = logging.getLogger(__name__)

# RSS Feeds für Energie-News
_RSS_FEEDS = [
    {
        "url": "https://www.orf.at/stories/rss/orf-stories.xml",
        "name": "ORF",
        "kategorie": "allgemein",
    },
    {
        "url": "https://oesterreichsenergie.at/rss.xml",
        "name": "Oesterreichs Energie",
        "kategorie": "markt",
    },
]

# Energie-relevante Schlüsselwörter
_ENERGY_KEYWORDS = [
    "strom", "gas", "energie", "tarif", "preis", "solar", "photovoltaik",
    "windkraft", "netz", "blackout", "kraftwerk", "erneuerbar", "fossil",
    "opec", "pipeline", "russland", "iran", "saudi", "lng", "öl",
    "co2", "klima", "förderung", "subvention", "wärmepumpe", "heizung",
    "elektrizität", "kwh", "megawatt", "gigawatt", "spot", "börse",
    "ukraine", "sanktion", "embargo", "nahost",
]

# PLZ → Bundesland Mapping (erste Ziffer)
_PLZ_BUNDESLAND: dict[str, str] = {
    "1": "Wien",
    "2": "Niederösterreich",
    "3": "Niederösterreich",
    "4": "Oberösterreich",
    "5": "Salzburg",
    "6": "Tirol",
    "7": "Burgenland",
    "8": "Steiermark",
    "9": "Kärnten",
}

# Warnung wenn Katalog älter als 60 Tage
_KATALOG_MAX_AGE_DAYS = 60


def load_foerderungen_catalog() -> tuple[list[FoerderungEntry], str]:
    """Lade Förderungskatalog aus dem gebündelten Förderungen-Package.

    Migriert vom losen ``data/foerderungen.json`` (17 Einträge, Stand 2026-03-05)
    auf ``energietools.capabilities.foerderungen`` (45 Einträge, Stand 2026-07-31,
    Bund + 9 Länder, mit Rechtsquellen/Status/Fenstern).

    Returns:
        Tuple von (Förderungs-Einträge, Stand-Datum des Katalogs).
    """
    try:
        return list(load_foerderungen()), load_manifest().stand_recherche or "unbekannt"
    except Exception as exc:
        log.error("Förderungskatalog konnte nicht geladen werden: %s", exc)
        return [], "unbekannt"


def _check_catalog_freshness(stand: str) -> str:
    """Prüfe ob der Katalog aktuell ist. Gibt Warntext zurück wenn veraltet."""
    if not stand or stand == "unbekannt":
        return "Förderungskatalog: Stand unbekannt — Angaben bitte selbst verifizieren."

    try:
        stand_date = date.fromisoformat(stand)
        age_days = (date.today() - stand_date).days
        if age_days > _KATALOG_MAX_AGE_DAYS:
            return (
                f"Förderungskatalog ist {age_days} Tage alt (Stand: {stand}). "
                "Angaben könnten veraltet sein — bitte offizielle Quellen prüfen."
            )
    except ValueError:
        return "Förderungskatalog: Stand-Datum ungültig."

    return ""


def monitor_energy_news(
    user_plz: str = "",
    user_interests: list[str] | None = None,
    heating_type: str = "",
) -> EnergyMonitorResult:
    """Energie-Nachrichten, Preiswarnung und Förderungen abrufen.

    Args:
        user_plz: PLZ des Users für regionale Filterung.
        user_interests: User-Interessen (z.B. ["pv", "spot", "bkw"]).
        heating_type: Heizungsart (z.B. "gas", "strom", "fernwärme").

    Returns:
        EnergyMonitorResult mit Nachrichten, Förderungen und ggf. Preiswarnung.
    """
    nachrichten = _fetch_energy_news()
    foerderungen_raw, katalog_stand = load_foerderungen_catalog()
    foerderungen = _filter_foerderungen(foerderungen_raw, user_plz, user_interests)
    preis_warnung = _check_price_alert()

    freshness_warning = _check_catalog_freshness(katalog_stand)
    zusammenfassung = freshness_warning

    return EnergyMonitorResult(
        nachrichten=nachrichten,
        foerderungen=foerderungen,
        preis_warnung=preis_warnung,
        zusammenfassung=zusammenfassung,
        katalog_stand=katalog_stand,
    )


def _fetch_energy_news() -> list[EnergyNewsItem]:
    """Energie-relevante Nachrichten aus RSS-Feeds laden."""
    all_items: list[EnergyNewsItem] = []

    for feed in _RSS_FEEDS:
        try:
            items = _parse_rss_feed(feed["url"], feed["name"], feed["kategorie"])
            all_items.extend(items)
        except Exception as exc:
            log.debug("RSS Feed %s fehlgeschlagen: %s", feed["name"], exc)

    # Nach Relevanz filtern
    relevant = [item for item in all_items if _is_energy_relevant(item.titel + " " + item.zusammenfassung)]

    # Nach Datum sortieren (neueste zuerst), maximal 10
    relevant.sort(key=lambda x: x.datum or datetime.min.replace(tzinfo=UTC), reverse=True)
    return relevant[:10]


def _parse_rss_feed(url: str, source_name: str, kategorie: str) -> list[EnergyNewsItem]:
    """RSS Feed parsen und EnergyNewsItems erstellen."""
    items: list[EnergyNewsItem] = []

    resp = httpx.get(url, timeout=15, follow_redirects=True)
    resp.raise_for_status()

    root = ET.fromstring(resp.text)

    for item in root.iter("item"):
        title = item.findtext("title", "")
        description = item.findtext("description", "")
        link = item.findtext("link", "")
        pub_date_str = item.findtext("pubDate", "")

        datum = None
        if pub_date_str:
            try:
                datum = datetime.strptime(pub_date_str[:25], "%a, %d %b %Y %H:%M:%S").replace(
                    tzinfo=UTC
                )
            except ValueError:
                pass

        items.append(EnergyNewsItem(
            titel=title.strip(),
            zusammenfassung=_clean_html(description)[:300],
            quelle=source_name,
            url=link.strip(),
            datum=datum,
            kategorie=kategorie,
        ))

    return items


def _is_energy_relevant(text: str) -> bool:
    """Prüfen ob ein Text energie-relevant ist."""
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in _ENERGY_KEYWORDS)


def _clean_html(text: str) -> str:
    """Einfache HTML-Tag-Entfernung."""
    import re
    return re.sub(r"<[^>]+>", "", text).strip()


def _filter_foerderungen(
    catalog: list[FoerderungEntry],
    plz: str,
    user_interests: list[str] | None = None,
) -> list[Foerderung]:
    """Förderungen nach PLZ/Bundesland und Status filtern.

    Nur offene, primärquellenverifizierte Förderungen für die Region des Users
    (bundesweite + passende Landesförderungen). ``verlaesslichkeit='unsicher'``
    Einträge werden nie ausgespielt (Rohdaten-Grundsatz: nie als Fakt zeigen).
    """
    bundesland = ""
    if plz:
        bundesland = _PLZ_BUNDESLAND.get(plz[0], "")

    stand = load_manifest().stand_recherche
    result: list[Foerderung] = []

    for f in catalog:
        # Nur primärquellenverifizierte Einträge ausspielen.
        if f.verlaesslichkeit != "verifiziert":
            continue

        # Nur offene Förderungen (geschlossen/unsicherer Status wird nicht beworben).
        if f.status != "offen":
            continue

        # Regional filter: bundesweite Förderungen (bundesland=None) + passendes Bundesland
        f_bl = f.bundesland or ""
        if f_bl and f_bl != bundesland:
            continue

        result.append(Foerderung(
            name=f.name,
            beschreibung=f.status_detail,
            betrag_eur=0.0,  # neues Schema hat keinen einzelnen €-Betrag mehr, siehe betrag_text
            betrag_text=f.foerderhoehe.text,
            bundesland=f_bl,
            zielgruppe=f.zielgruppe,
            kategorie=f.kategorie,
            url=f.antrags_url or "",
            quelle=f.foerderstelle,
            status=f.status,
            gueltig_ab=f.status_seit or "",
            gueltig_bis="",
            stand=stand,
            voraussetzungen="; ".join(f.bedingungen),
            hinweis=f"Nächstes Fenster: {f.naechstes_fenster}" if f.naechstes_fenster else "",
        ))

    return result


def _check_price_alert() -> str:
    """Spot-Preis-Warnung prüfen (vereinfacht)."""
    try:
        import os

        entsoe_api_key = os.environ.get("ENTSOE_API_KEY", "")

        if not entsoe_api_key:
            return ""

        # Simplifiziert — in Zukunft: ENTSO-E day-ahead prices prüfen
        # und mit 30-Tage-Durchschnitt vergleichen
        return ""
    except Exception:
        return ""
