# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Deterministische Rechnungs-Extraktion (Text-PDF -> strukturierte Felder).

energietools bündelt **keinen** LLM/OCR-Client: die nicht-deterministische
Vision-/LLM-Extraktion (eingescannte PDFs, Fotos) lebt in der aufrufenden
Anwendung (gridbert). Hier laufen nur die offline reproduzierbare Regex-
Extraktion aus dem PDF-Text und die auditierbare Aufbereitung
(:func:`finalize_invoice`) mit lückenlosem Rechenweg.
"""

from __future__ import annotations

import datetime
import logging
from pathlib import Path

import pdfplumber

from energietools.models import Invoice

log = logging.getLogger(__name__)

# --- PDF/Bild Helpers (wiederverwendet aus v0.2) ------------------------------

# Keywords indicating a page has pricing-relevant content
_PRICING_KEYWORDS = {
    "kWh", "kwh", "Verbrauch", "Energiepreis", "Arbeitspreis",
    "Verrechnungspreis", "Grundgebühr", "Grundpauschale",
    "Netzentgelt", "Netzkosten", "Zählpunkt", "Detailrechnung",
    "Abrechnungszeitraum", "Verrechnungszeitraum", "Jahresabrechnung",
    "Energiekosten", "Stromkosten", "Gaskosten", "Cent/kWh", "ct/kWh",
}
# Keywords indicating a page is informational/AGB (low priority)
_INFO_KEYWORDS = {
    "Grundversorgung", "Konsumentenschutzgesetz", "KSchG",
    "Schlichtungsstelle", "Energieverbraucher", "Streitschlichtung",
    "ENERGIESPARTIPP", "Datenschutz", "Allgemeine Geschäftsbedingungen",
}


def _pdf_to_text(pdf_path: Path) -> str:
    """Extrahiere Text aus PDF.

    Prioritizes pages with pricing data and deprioritizes AGB/info pages
    to stay within token limits.
    """
    page_texts: list[tuple[str, bool]] = []  # (text, is_pricing)
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text or not text.strip():
                continue
            is_pricing = any(kw in text for kw in _PRICING_KEYWORDS)
            is_info = any(kw in text for kw in _INFO_KEYWORDS) and not is_pricing
            if is_info and len(text) > 2000:
                # Skip long info/AGB pages entirely
                log.debug("Skipping info page (%d chars)", len(text))
                continue
            page_texts.append((text, is_pricing))

    return "\n\n".join(text for text, _ in page_texts)


def _clean_pdf_text(text: str) -> str:
    """Clean garbled text from PDF extraction.

    Some PDFs (e.g. Wien Energie) have pages with garbled/garbage characters
    that confuse the LLM. This removes lines that are mostly non-readable.
    """
    cleaned_lines = []
    for line in text.split("\n"):
        if not line.strip():
            cleaned_lines.append(line)
            continue
        # Count printable/readable characters vs garbage
        readable = sum(1 for c in line if c.isalnum() or c in " .,;:/-€%(){}[]&+*@#\"'!?=<>äöüÄÖÜß\t")
        total = len(line.strip())
        if total > 0 and readable / total < 0.5:
            # Skip garbled lines (< 50% readable)
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def _parse_date(date_str: str) -> datetime.date | None:
    """Parse a date string in common Austrian invoice formats."""
    if not date_str or not date_str.strip():
        return None
    date_str = date_str.strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def _compute_period_days(von: str, bis: str) -> int | None:
    """Compute the number of days between two date strings.

    Returns None if either date cannot be parsed.
    """
    d_von = _parse_date(von)
    d_bis = _parse_date(bis)
    if d_von is None or d_bis is None:
        return None
    days = (d_bis - d_von).days
    return days if days > 0 else None


def _annualize_invoice(raw: dict) -> dict:
    """Annualisiert Teilzeitraum-Rechnungen deterministisch (kein LLM).

    Nimmt das Roh-Dict (verbrauch_kwh, energiekosten_eur, zeitraum_von/bis)
    und produziert jahresverbrauch_kwh/energiekosten_eur auf Jahresbasis plus
    Zeitraum-Metadaten und ``jahreskosten_brutto_eur`` (annualisierter
    Rechnungsbetrag — die Hauptkostenmetrik).

    EVU-Prognose (B.4-Merge): weist die Rechnung einen "voraussichtlichen
    Jahresverbrauch" aus, hat der Vorrang vor der naiven Tages-Hochrechnung —
    aber NUR innerhalb des ±30%-Plausibilitätsfensters gegen die Hochrechnung
    (implausible EVU-Werte werden ignoriert, nie still übernommen).

    Mutates and returns the dict.
    """
    von = raw.get("zeitraum_von", "")
    bis = raw.get("zeitraum_bis", "")
    period_days = _compute_period_days(von, bis)

    # Map new field names to model field names
    raw_verbrauch = raw.pop("verbrauch_kwh", 0.0) or 0.0
    raw_kosten = raw.get("energiekosten_eur", 0.0) or 0.0
    raw_netzkosten = raw.pop("netzkosten_eur", None)
    # Optionale EVU-Prognose (saisonbereinigt) — nur mit Plausibilitäts-Check.
    prognose = float(raw.pop("jahresverbrauch_prognose_kwh", 0.0) or 0.0)

    # Store period metadata
    raw["zeitraum_von"] = von
    raw["zeitraum_bis"] = bis
    raw["zeitraum_tage"] = period_days

    # Threshold: invoices >= 300 days are treated as annual (allow billing variations)
    if period_days is not None and period_days < 300 and period_days > 0:
        # Annualize: scale to 365 days
        factor = 365.0 / period_days
        hochgerechnet = round(raw_verbrauch * factor, 1)
        raw["energiekosten_eur"] = round(raw_kosten * factor, 2)
        raw["ist_hochgerechnet"] = True
        raw["original_verbrauch_kwh"] = raw_verbrauch
        raw["original_energiekosten_eur"] = raw_kosten
        # Annualize network costs too if present
        if raw_netzkosten and raw_netzkosten > 0:
            raw["netzkosten_eur_jahr"] = round(raw_netzkosten * factor, 2)
        # EVU-Prognose nur im ±30%-Fenster gegen die Hochrechnung übernehmen.
        if prognose > 0 and 0.7 * hochgerechnet <= prognose <= 1.3 * hochgerechnet:
            raw["jahresverbrauch_kwh"] = prognose
            raw["jahresverbrauch_prognose_kwh"] = prognose
            log.info(
                "Invoice annualized via EVU prognose: %d days, %.1f kWh "
                "(prognose=%.1f, hochgerechnet=%.1f)",
                period_days, prognose, prognose, hochgerechnet,
            )
        else:
            raw["jahresverbrauch_kwh"] = hochgerechnet
            if prognose > 0:
                log.warning(
                    "Implausible EVU-Prognose %.1f ignoriert (hochgerechnet=%.1f, "
                    "ratio=%.2fx) — deterministischer Wert bleibt",
                    prognose, hochgerechnet, prognose / max(hochgerechnet, 1),
                )
            log.info(
                "Invoice annualized: %d days → factor %.2f, "
                "%.1f kWh → %.1f kWh/year, %.2f EUR → %.2f EUR/year",
                period_days, factor,
                raw_verbrauch, hochgerechnet,
                raw_kosten, raw["energiekosten_eur"],
            )
    else:
        # Jahres- (>= 300 Tage) oder unbekannter Zeitraum — Ist-Werte nutzen.
        # Bei fast-jährlichen Rechnungen (>= 350 Tage) KEINE Prognose-Übernahme:
        # der tatsächliche Verbrauch ist verlässlicher als die EVU-Schätzung.
        raw["ist_hochgerechnet"] = False
        is_near_annual = period_days is not None and period_days >= 350
        if (
            not is_near_annual
            and prognose > 0
            and raw_verbrauch > 0
            and 0.7 * raw_verbrauch <= prognose <= 1.3 * raw_verbrauch
        ):
            raw["jahresverbrauch_kwh"] = prognose
            raw["jahresverbrauch_prognose_kwh"] = prognose
        else:
            raw["jahresverbrauch_kwh"] = raw_verbrauch
        # Map netzkosten_eur → netzkosten_eur_jahr (already annual or close enough)
        if raw_netzkosten and raw_netzkosten > 0:
            raw["netzkosten_eur_jahr"] = raw_netzkosten

    # Rechnungsbetrag → jahreskosten_brutto_eur annualisieren: EINE deterministisch
    # hergeleitete Jahres-Kostenzahl aus Endbetrag + Zeitraum (Hauptmetrik, B.4).
    rb_periode = float(raw.get("rechnungsbetrag_brutto_eur", 0.0) or 0.0)
    if rb_periode > 0:
        if period_days and 0 < period_days < 300:
            raw["jahreskosten_brutto_eur"] = round(rb_periode * 365.0 / period_days, 2)
        else:
            raw["jahreskosten_brutto_eur"] = round(rb_periode, 2)
    else:
        raw["jahreskosten_brutto_eur"] = 0.0

    return raw


# --- Deterministic PDF table extraction (Option 3) ---------------------------

import re as _re_module


def _parse_austrian_number(s: str, expect_large: bool = False) -> float:
    """Parse Austrian number format: '1.234,56' or '1234,56' or '1234.56'.

    Austrian convention: dot=thousands, comma=decimal.

    Args:
        s: Number string to parse.
        expect_large: If True, ambiguous dot-only numbers like '3.240' are
            treated as thousands separators (=3240). If False, treated as
            decimal points (=3.240). Callers should set this based on context
            (e.g. kWh values are large, ct/kWh prices are small).
    """
    s = s.strip().replace('\xa0', '').replace(' ', '')
    # If comma AND dot: '1.234,56' → remove dots, comma=decimal
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    elif '.' in s and expect_large:
        # Treat dots as thousands separators when we expect large numbers
        parts = s.split('.')
        if all(p.isdigit() for p in parts) and all(len(p) == 3 for p in parts[1:]):
            if 1 <= len(parts[0]) <= 3:
                s = s.replace('.', '')  # e.g. '3.240' → 3240, '12.145' → 12145
    # If not expect_large or doesn't match pattern, keep dot as decimal point
    try:
        return float(s)
    except ValueError:
        return 0.0


# --- Anlagen-/Verbrauchsadresse (B.4-Merge) -----------------------------------

# Keywords, die die VERBRAUCHS-Adresse ankern (Anlagen-/Lieferadresse) — nie
# die Absender-/Footer-Adresse des Lieferanten.
_ADDRESS_KEYWORDS = (
    "Anlagenadresse",
    "Anlageadresse",
    "Verbrauchsstelle",
    "Verbrauchsadresse",
    "Lieferadresse",
    "Lieferanschrift",
    "Lieferstelle",
    "Abnahmestelle",
)

# Tokens, die das ENDE eines Adressblocks markieren — die Regex muss hier
# stoppen, damit kein folgender Rechnungsabschnitt in die Adresse rutscht.
_ADDRESS_STOP = (
    r"Zählpunkt|Zaehlpunkt|Zählpunkte|Zaehlpunkte|Zähler|Zaehler|"
    r"Abrechnungszeitraum|Verrechnungszeitraum|Rechnungszeitraum|"
    r"Abrechnung\b|Netzbetreiber|Anlagennummer|Vertragskonto|Kundennummer|"
    r"Sehr geehrte"
)

# PLZ + Ort, z.B. "8010 Graz" oder "1100 Wien". Der Ort beginnt mit einem
# Großbuchstaben (inkl. Umlaute), um Firmenbuch-/FN-Nummern nicht zu matchen.
_PLZ_ORT_RE = _re_module.compile(r"\b(\d{4})\s+([A-ZÄÖÜ][\wäöüß .\-]+)")

# Adressblock: Keyword, optionaler Doppelpunkt, dann bis zu 5 Zeilen Adresse.
_ADDRESS_BLOCK_RE = _re_module.compile(
    r"(?:" + "|".join(_ADDRESS_KEYWORDS) + r")"
    r"\s*:?\s*"
    r"(?P<body>(?:[^\n]+\n?){1,5}?)"
    r"(?=" + _ADDRESS_STOP + r"|\Z)",
    _re_module.IGNORECASE,
)


def _compose_address_from_block(body: str) -> tuple[str, str]:
    """Macht aus einem rohen Adressblock ('Strasse Hausnr, PLZ Ort', plz).

    - splittet den Block an Zeilenumbrüchen UND Kommas
    - verwirft führende Namens-Segmente (Segment ohne Ziffer = kein Straßenteil)
    - fügt die restlichen Teile kommagetrennt zusammen
    Returns ('', ''), wenn der Block keine Straßen-/Hausnummern-Info trägt.
    """
    parts = [p.strip() for p in _re_module.split(r"[\n,]", body) if p.strip()]
    while len(parts) > 1 and not _re_module.search(r"\d", parts[0]):
        parts.pop(0)
    if not parts:
        return "", ""
    full = ", ".join(parts)
    if not _re_module.search(r"\d", full):
        return "", ""
    plz_match = _PLZ_ORT_RE.search(full)
    plz = plz_match.group(1) if plz_match else ""
    return full, plz


def _extract_address_from_text(text: str) -> tuple[str, str]:
    """Extrahiert die vollständige Verbrauchs-Adresse deterministisch.

    Ankert strikt auf Anlagen-/Verbrauchs-/Lieferadresse-Keywords, damit nie
    die Footer-Adresse des Lieferanten erwischt wird. Returns
    ('Strasse Hausnr, PLZ Ort', plz); beides '' ohne geankerte Adresse.
    """
    for m in _ADDRESS_BLOCK_RE.finditer(text):
        full, plz = _compose_address_from_block(m.group("body"))
        if full:
            return full, plz
    return "", ""


def _is_address_incomplete(adresse: str) -> bool:
    """True, wenn der Adresse Hausnummer oder PLZ+Ort fehlen.

    Eine wechselformular-taugliche Adresse braucht Straße MIT Hausnummer und
    PLZ + Ort. Leer, nur-PLZ oder Straße-ohne-Nummer zählen als unvollständig.
    """
    a = (adresse or "").strip()
    if not a:
        return True
    has_plz_ort = bool(_PLZ_ORT_RE.search(a))
    # Hausnummer: eine Ziffer, die NICHT Teil der 4-stelligen PLZ ist.
    without_plz = _PLZ_ORT_RE.sub("", a)
    has_house_no = bool(_re_module.search(r"\d", without_plz))
    return not (has_plz_ort and has_house_no)


def _extract_deterministic_from_text(text: str) -> dict | None:
    """Try to extract invoice data deterministically from PDF text using regex.

    Returns a partial dict with reliably extracted fields, or None if the
    text doesn't match any known provider pattern. Fields that can't be
    reliably extracted are omitted (LLM fills them in).

    This function extracts the MOST RELIABLE fields:
    - summe_energieentgelte_eur (from "Energiekosten" / "Summe Energieentgelte" lines)
    - summe_netzentgelte_eur
    - verbrauch_kwh
    - grundgebuehr
    - arbeitspreis (only if a single, unambiguous price line exists)
    - plz, zaehlpunkt
    - zeitraum_von/bis
    """
    if not text or len(text) < 200:
        return None

    result: dict = {}
    found_anything = False

    # --- Verbrauch (kWh) ---
    # Pattern: "wurden 13.666,99 kWh verbraucht" (Sturm Energie, many Austrian providers)
    m = _re_module.search(r'wurden\s+([\d.,]+)\s*kWh\s+verbraucht', text)
    if m:
        result['verbrauch_kwh'] = _parse_austrian_number(m.group(1), expect_large=True)
        found_anything = True
    # Pattern: "aktuell 3.240 kWh in 365 Tagen" or "aktuell3.240kWh in365 Tagen" (Wien Energie)
    if 'verbrauch_kwh' not in result:
        m = _re_module.search(r'aktuell\s*([\d.,]+)\s*kWh\s+in\s*(\d+)\s*Tagen', text)
        if m:
            result['verbrauch_kwh'] = _parse_austrian_number(m.group(1), expect_large=True)
            result['_verbrauch_tage'] = int(m.group(2))
            found_anything = True
    if 'verbrauch_kwh' not in result:
        # Pattern: "Gesamtverbrauch: 3.200 kWh"
        m = _re_module.search(r'Gesamtverbrauch[:\s]+([\d.,]+)\s*kWh', text)
        if m:
            result['verbrauch_kwh'] = _parse_austrian_number(m.group(1), expect_large=True)
            found_anything = True
    if 'verbrauch_kwh' not in result:
        # Generic: look for "NNNN kWh" preceded by consumption context
        # "Verbrauch ... NNNN kWh" on same line
        # EXCLUDE "kWh/Tag" matches (those are daily rates, not total consumption)
        for m in _re_module.finditer(r'(?:Verbrauch|Bezug)\D{0,40}?([\d.,]+)\s*kWh(?!/Tag)', text):
            val = _parse_austrian_number(m.group(1), expect_large=True)
            if 10 < val < 200_000:
                result.setdefault('verbrauch_kwh', val)
                found_anything = True
                break

    # --- Summe Energieentgelte / Energiekosten ---
    # Wien Energie: "Energiekosten 359,83"
    # Energie Steiermark: "Summe Energieentgelte 23,80"
    # MAXENERGY/oekostrom: "Summe Energielieferung 123,45"
    for pattern in [
        r'Energiekosten\s+([\d.,]+)',
        r'Summe\s+Energieentgelte\s+([\d.,]+)',
        r'Summe\s+Energielieferung\s+([\d.,]+)',
        r'Summe\s+Energie\s+([\d.,]+)',
    ]:
        matches = _re_module.findall(pattern, text)
        if matches:
            # Take the LAST match (in multi-section invoices, Strom comes after Gas)
            val = _parse_austrian_number(matches[-1], expect_large=True)
            if val > 0:
                result['summe_energieentgelte_eur'] = val
                result['summe_energieentgelte_ist_netto'] = True  # these are always netto
                found_anything = True
                break

    # --- Summe Netzentgelte ---
    for pattern in [
        r'Summe\s+Netzentgelte\s+([\d.,]+)',
        r'Summe\s+Netzkosten\s+([\d.,]+)',
        r'Summe\s+Netz\s+([\d.,]+)',
    ]:
        m = _re_module.search(pattern, text)
        if m:
            val = _parse_austrian_number(m.group(1), expect_large=True)
            if val > 0:
                result['summe_netzentgelte_eur'] = val
                result['summe_netzentgelte_ist_netto'] = True
                found_anything = True
                break

    # --- Summe Steuern und Abgaben ---
    for pattern in [
        r'Summe\s+Steuern\s+und\s+Abgaben\s+([\d.,]+)',
        r'Steuern\s+und\s+Abgaben\s+([\d.,]+)',
    ]:
        m = _re_module.search(pattern, text)
        if m:
            val = _parse_austrian_number(m.group(1), expect_large=True)
            if val > 0:
                result['summe_steuern_abgaben_eur'] = val
                result['summe_steuern_abgaben_ist_netto'] = True
                found_anything = True
                break

    # --- Summe exkl. USt ---
    # Wien Energie has multiple "Summe exkl. USt" (per Strom/Gas section)
    # We want the one from the Strom section
    for pattern in [
        r'Summe\s+exkl\.\s*USt\.?\s+([\d.,]+)',
        r'Gesamtbetrag\s+netto\s+([\d.,]+)',
    ]:
        matches = _re_module.findall(pattern, text)
        if matches:
            val = _parse_austrian_number(matches[-1], expect_large=True)
            if val > 0:
                result['_summe_exkl_ust'] = val
                found_anything = True
                break

    # --- Rechnungsbetrag brutto ---
    for pattern in [
        r'Rechnungsbetrag.*?inkl.*?USt.*?([\d.,]+)',
        r'Gesamtbetrag.*?brutto.*?([\d.,]+)',
        r'Gesamtbetrag.*?inkl.*?USt.*?([\d.,]+)',
        r'Endbetrag.*?([\d.,]+)\s*EUR',
    ]:
        m = _re_module.search(pattern, text)
        if m:
            val = _parse_austrian_number(m.group(1), expect_large=True)
            if val > 0:
                result['rechnungsbetrag_brutto_eur'] = val
                found_anything = True
                break

    # --- Grundpreis / Grundgebühr ---
    # Wien Energie: "Energie-Grundpreis ... 40,000000 EUR/Jahr"
    # Energie Steiermark: "Grundpreis 01.12.25-31.12.25 ... 4,16 EUR/Monat  3,47"
    # Generic: "Grundpauschale ... 3,50 EUR/Monat"
    for pattern in [
        r'Energie-Grundpreis.*?([\d.,]+)\s*EUR/Jahr',
        r'Grundpreis.*?([\d.,]+)\s*EUR/Monat',
        r'Grundpreis.*?([\d.,]+)\s*EUR/Jahr',
        r'Grundpauschale.*?([\d.,]+)\s*EUR/Monat',
        r'Grundpauschale.*?([\d.,]+)\s*EUR/Jahr',
        r'Grundgeb.*?hr.*?([\d.,]+)\s*EUR/Monat',
        r'Grundgeb.*?hr.*?([\d.,]+)\s*EUR/Jahr',
    ]:
        m = _re_module.search(pattern, text)
        if m:
            val = _parse_austrian_number(m.group(1))
            if val > 0:
                if 'EUR/Jahr' in pattern:
                    result['grundgebuehr_eur'] = val
                    result['grundgebuehr_zeitraum'] = 'jahr'
                else:
                    result['grundgebuehr_eur'] = val
                    result['grundgebuehr_zeitraum'] = 'monat'
                result['grundgebuehr_ist_netto'] = True
                found_anything = True
                break

    # --- Arbeitspreis / Energiepreis (only if SINGLE unambiguous line) ---
    # Collect all energy price lines
    energie_preis_lines = []
    for pattern in [
        r'(?:Energie-Verbrauchspreis|Energiepreis|Arbeitspreis(?:\s+Energie)?)'
        r'\s+\d{2}\.\d{2}\.\d{2,4}.\d{2}\.\d{2}\.\d{2,4}'
        r'\s+[\d.,]+\s+kWh\s+([\d.,]+)\s*(?:Cent|ct)/kWh',
    ]:
        for m in _re_module.finditer(pattern, text):
            val = _parse_austrian_number(m.group(1))
            if 1 < val < 100:
                energie_preis_lines.append(val)

    if len(set(energie_preis_lines)) == 1:
        # All lines have the same price → unambiguous
        result['arbeitspreis_ct_kwh'] = energie_preis_lines[0]
        result['arbeitspreis_ist_netto'] = True
        found_anything = True
        log.info("Deterministic: Einheitlicher Arbeitspreis %.2f ct/kWh (%d Zeilen)",
                 energie_preis_lines[0], len(energie_preis_lines))
    elif len(set(energie_preis_lines)) > 1:
        # Multiple different prices → DON'T set arbeitspreis, let Plan B handle it
        log.info("Deterministic: %d verschiedene Arbeitspreise gefunden: %s → verwende Summe",
                 len(set(energie_preis_lines)), sorted(set(energie_preis_lines)))

    # --- Zählpunkt ---
    m = _re_module.search(r'(AT\d{30,35})', text.replace(' ', ''))
    if not m:
        m = _re_module.search(r'(AT[.\s]?\d[\d.\s]{28,38})', text)
    if m:
        zp = _re_module.sub(r'[\s.]', '', m.group(1))
        if len(zp) >= 33:
            result['zaehlpunkt'] = zp[:33]
            found_anything = True

    # --- PLZ (Anlagenadresse) ---
    # Look near "Anlagenadresse" or "Verbrauchsstelle"
    for pattern in [
        r'(?:Anlagenadresse|Verbrauchsstelle)[^\n]{0,100}(\d{4})\s+\w',
        r'(?:Anlagenadresse|Verbrauchsstelle).*?\n.*?(\d{4})\s+\w',
    ]:
        m = _re_module.search(pattern, text)
        if m:
            result['plz'] = m.group(1)
            found_anything = True
            break

    # --- Adresse (vollständige Verbrauchs-Adresse, B.4-Merge) ---
    # "Strasse Hausnummer, PLZ Ort", geankert auf Anlagen-/Verbrauchs-/
    # Lieferadresse-Keywords — die wechselformular-relevante Adresse.
    adresse_full, adresse_plz = _extract_address_from_text(text)
    if adresse_full:
        result['adresse'] = adresse_full
        # PLZ aus der Adresse nachziehen, wenn die dedizierte PLZ-Regex leer blieb.
        if not result.get('plz') and adresse_plz:
            result['plz'] = adresse_plz
        found_anything = True

    # --- Jahresverbrauch (EVU-Prognose, B.4-Merge) ---
    # Viele AT-Rechnungen weisen einen saisonbereinigten "voraussichtlichen
    # Jahresverbrauch" aus — mit Lastprofildaten des EVU die bessere Zahl als
    # eine naive Tages-Hochrechnung (Übernahme nur im ±30%-Fenster).
    for pattern in [
        r'voraussichtlich\w*\s+Jahresverbrauch\w*\s+von\s+([\d.,]+)\s*kWh',
        r'voraussichtlich\w*\s+Verbrauch\w*\s+von\s+([\d.,]+)\s*kWh',
        r'gesch\w+\s+Jahresverbrauch\w*\s+von\s+([\d.,]+)\s*kWh',
        r'prognostiziert\w*\s+Jahresverbrauch\w*\s+von\s+([\d.,]+)\s*kWh',
    ]:
        m = _re_module.search(pattern, text)
        if m:
            val = _parse_austrian_number(m.group(1), expect_large=True)
            if val > 0:
                result['jahresverbrauch_prognose_kwh'] = val
                found_anything = True
                break

    # --- Abrechnungszeitraum ---
    # "Abrechnungszeitraum: 01.01.2024 - 31.12.2024"
    # "Rechnungszeitraum 01.07.2024 -04.07.2025" (Sturm Energie)
    # "19.03.2024–18.03.2025" in Wien Energie
    for pattern in [
        r'Abrechnungszeitraum[:\s]+(\d{2}\.\d{2}\.\d{4})\s*[-–]\s*(\d{2}\.\d{2}\.\d{4})',
        r'Verrechnungszeitraum[:\s]+(\d{2}\.\d{2}\.\d{4})\s*[-–]\s*(\d{2}\.\d{2}\.\d{4})',
        r'Rechnungszeitraum[:\s]+(\d{2}\.\d{2}\.\d{4})\s*[-–]\s*(\d{2}\.\d{2}\.\d{4})',
    ]:
        m = _re_module.search(pattern, text)
        if m:
            result['zeitraum_von'] = m.group(1)
            result['zeitraum_bis'] = m.group(2)
            found_anything = True
            break

    if not found_anything:
        return None

    log.info("Deterministic extraction: %s", {k: v for k, v in result.items() if not k.startswith('_')})
    return result


# --- Haupt-Funktion -----------------------------------------------------------

def parse_invoice(file_path: str | Path) -> Invoice:
    """Extrahiere Rechnungsdaten **deterministisch** aus einem Text-PDF.

    energietools bündelt keinen LLM/OCR-Client: die nicht-deterministische
    Vision-/LLM-Extraktion (eingescannte PDFs, Fotos, schwierige Layouts) lebt in
    der aufrufenden Anwendung (gridbert). Hier läuft nur die offline
    reproduzierbare Regex-Extraktion aus dem PDF-Text plus die auditierbare
    Aufbereitung (:func:`finalize_invoice`) mit Rechenweg.

    Args:
        file_path: Pfad zu einem durchsuchbaren Text-PDF (kein Scan/Bild).

    Raises:
        FileNotFoundError: Datei fehlt.
        ValueError: kein durchsuchbarer Text (Scan/Bild) oder kein bekanntes
            Layout — dann ist die LLM/OCR-Extraktion (gridbert) zuständig.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Datei nicht gefunden: {path}")

    if path.suffix.lower() != ".pdf":
        raise ValueError(
            f"energietools liest nur durchsuchbare Text-PDFs deterministisch; "
            f"'{path.suffix}' (Bild/Scan) braucht die LLM/OCR-Extraktion der "
            f"aufrufenden Anwendung (gridbert)."
        )

    text = _pdf_to_text(path)
    if text.strip():
        text = _clean_pdf_text(text)
    if not text.strip() or len(text) <= 200:
        raise ValueError(
            "PDF enthält keinen verwertbaren Text (vermutlich ein Scan) — die "
            "OCR-/Vision-Extraktion liegt in der aufrufenden Anwendung (gridbert)."
        )

    raw = _extract_deterministic_from_text(text)
    if not raw:
        raise ValueError(
            "Konnte aus dem PDF-Text keine Rechnungsfelder deterministisch "
            "extrahieren (unbekanntes Layout) — LLM-Extraktion (gridbert) zuständig."
        )

    raw = finalize_invoice(raw)
    log.info("Deterministisch extrahierte Rechnungsdaten: %s", raw)
    return Invoice(**raw)


# --- Deterministic post-processing (NO LLM, pure Python) ---------------------

# Plausibility bounds for Austrian energy invoices
_PLAUSIBILITY = {
    "arbeitspreis_ct_kwh": (3.0, 80.0),      # ct/kWh brutto (3-80 is wide)
    "grundgebuehr_eur_monat": (0.0, 30.0),    # EUR/month brutto
    "verbrauch_kwh": (10.0, 100_000.0),       # kWh/year
    "energiekosten_eur_brutto": (5.0, 50_000.0),
}


def _safe_float(val: object, default: float = 0.0) -> float:
    """Convert to float, handling dicts (Strom+Gas) and garbage."""
    if isinstance(val, dict):
        val = next(iter(val.values()), default)
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_str(val: object, max_len: int = 200) -> str:
    """Convert to string, handling dicts."""
    if isinstance(val, dict):
        val = next(iter(val.values()), "")
    return str(val)[:max_len] if val else ""


def _to_brutto(value: float, ist_netto: bool) -> float:
    """Netto → Brutto (20% österreichische USt)."""
    return value * 1.2 if ist_netto else value


def _to_netto(value: float, ist_brutto: bool) -> float:
    """Brutto → Netto."""
    return value / 1.2 if ist_brutto else value


def _plausibility_check(field: str, value: float) -> bool:
    """Check if value is within plausible bounds."""
    bounds = _PLAUSIBILITY.get(field)
    if not bounds:
        return True
    lo, hi = bounds
    ok = lo <= value <= hi
    if not ok:
        log.warning("Plausibilitätscheck fehlgeschlagen: %s = %.2f (erwartet %.1f–%.1f)",
                    field, value, lo, hi)
    return ok


def _pick_arbeitspreis_from_preiszeilen(preiszeilen: list[dict], verbrauch: float) -> tuple[float, bool, str]:
    """Deterministically pick the energy Arbeitspreis from extracted price lines.

    Returns (arbeitspreis_value, ist_netto, plan_description).
    Priority:
    1. Single "energie" line in ct/kWh → use directly
    2. Multiple "energie" lines → weighted average if we have kWh, else first
    3. Fallback to 0.0 (caller should use Plan B)
    """
    # Filter for energy price lines with ct/kWh or EUR/kWh
    energie_lines = [
        z for z in preiszeilen
        if z.get("kategorie") == "energie"
        and _safe_float(z.get("wert")) > 0
        and z.get("einheit", "").lower() in ("ct/kwh", "eur/kwh", "cent/kwh")
    ]

    if not energie_lines:
        return 0.0, True, ""

    if len(energie_lines) == 1:
        z = energie_lines[0]
        wert = _safe_float(z["wert"])
        # Normalize to ct/kWh
        if z.get("einheit", "").lower() == "eur/kwh":
            wert *= 100
        ist_netto = z.get("ist_netto", True)
        log.info("Preiszeilen Plan A: 1 Energiepreis-Zeile: '%s' = %.2f ct/kWh (%s)",
                 z.get("label", "?"), wert, "netto" if ist_netto else "brutto")
        return wert, ist_netto, f"A-preiszeilen ('{z.get('label', '?')}')"

    # Multiple energy lines — could be HT/NT or multi-period
    # Check for HT/NT pattern
    ht_lines = [z for z in energie_lines if any(k in z.get("label", "").upper() for k in ("HT", "HOCHTARIF", "TAG"))]
    if ht_lines:
        z = ht_lines[0]
        wert = _safe_float(z["wert"])
        if z.get("einheit", "").lower() == "eur/kwh":
            wert *= 100
        ist_netto = z.get("ist_netto", True)
        log.info("Preiszeilen Plan A: HT-Zeile: '%s' = %.2f ct/kWh", z.get("label", "?"), wert)
        return wert, ist_netto, f"A-preiszeilen HT ('{z.get('label', '?')}')"

    # Multi-period: take simple average (all are the Arbeitspreis at different times)
    werte = []
    for z in energie_lines:
        w = _safe_float(z["wert"])
        if z.get("einheit", "").lower() == "eur/kwh":
            w *= 100
        werte.append(w)
    avg = sum(werte) / len(werte)
    ist_netto = energie_lines[0].get("ist_netto", True)
    log.info("Preiszeilen Plan A: %d Energiepreis-Zeilen, Durchschnitt %.2f ct/kWh (Werte: %s)",
             len(werte), avg, werte)
    return avg, ist_netto, f"A-preiszeilen avg ({len(werte)} Zeilen)"


def finalize_invoice(raw: dict) -> dict:
    """Deterministische Aufbereitung einer rohen Extraktion zu Invoice-Feldern.

    Nimmt das Roh-Dict (aus der deterministischen Regex-Extraktion oder einer
    externen LLM-Extraktion in gridbert) und rechnet alles **deterministisch +
    auditierbar** aus:
    - preiszeilen parsen, um den Arbeitspreis zu wählen
    - Netto/Brutto-Umrechnung
    - Plan A: Arbeitspreis aus preiszeilen (bzw. legacy arbeitspreis_ct_kwh)
    - Plan B: aus summe_energieentgelte / kWh ableiten
    - Plan C: aus rechnungsbetrag ableiten
    - Cross-check: Plan A vs Plan B — bei >15% Abweichung Plan B bevorzugen
    - Hochrechnung von Teilzeitraum-Rechnungen
    - Plausibilitätsprüfungen

    Das Ergebnis trägt einen ``rechenweg`` (welcher Plan, Kandidaten, Annahmen,
    Plausibilitäts-Hinweise) — keine stillen Defaults.
    """
    import re as _re

    # --- 1. Handle combined Strom+Gas invoices ---
    from energietools.models.invoice import EnergieBlock

    has_strom = "strom" in raw and isinstance(raw["strom"], dict)
    has_gas = "gas" in raw and isinstance(raw["gas"], dict)

    if has_strom and has_gas:
        # Kombi-Rechnung: Strom als Hauptdaten, Gas als separater Block.
        #
        # Wichtig (B.4-Merge): bei Kombi MUSS der strom-Block Vorrang vor den
        # Top-Level-Feldern haben — die deterministische Regex legt oft die
        # zuerst gefundenen Werte (häufig Gas) in die Top-Level, und der
        # Strom-Block ist die einzig verlässliche Quelle für die strom-
        # spezifischen Verbrauch-/Zählpunkt-Werte.
        strom_data = raw.pop("strom")
        gas_data = raw.pop("gas")
        raw["energieart"] = "kombi"
        raw["gas"] = EnergieBlock(
            lieferant=_safe_str(gas_data.get("lieferant", "")),
            tarif_name=_safe_str(gas_data.get("tarif_name", "")),
            energiepreis_ct_kwh=_safe_float(gas_data.get("arbeitspreis_ct_kwh") or gas_data.get("energiepreis_ct_kwh")),
            grundgebuehr_eur_monat=_safe_float(gas_data.get("grundgebuehr_eur_monat") or gas_data.get("grundgebuehr_eur")),
            jahresverbrauch_kwh=_safe_float(gas_data.get("verbrauch_kwh") or gas_data.get("jahresverbrauch_kwh")),
            zaehlpunkt=_safe_str(gas_data.get("zaehlpunkt", "")),
        )
        # Felder, die per-Energie bestimmt sind: Strom-Block überschreibt immer.
        _per_energy_fields = ("verbrauch_kwh", "jahresverbrauch_kwh",
                              "zaehlpunkt", "tarif_name")
        for key in _per_energy_fields:
            val = strom_data.get(key)
            if val not in (None, "", 0, 0.0):
                raw[key] = val
        # Andere Felder (lieferant, plz, adresse, …) nur füllen, wenn leer.
        for key, val in strom_data.items():
            if key in _per_energy_fields:
                continue
            if key not in raw or raw.get(key) in (0, 0.0, "", "Unbekannt", None):
                raw[key] = val
            elif isinstance(raw.get(key), dict) and key != "gas":
                raw[key] = val
        log.info("Kombi-Rechnung erkannt — Strom als Hauptdaten, Gas-Block extrahiert")
    elif has_strom and not has_gas:
        # Nur Strom-Sektion im LLM-Output (trotzdem reine Strom-Rechnung)
        strom_data = raw.pop("strom")
        raw["energieart"] = "strom"
        for key, val in strom_data.items():
            if key not in raw or raw.get(key) in (0, 0.0, "", "Unbekannt", None):
                raw[key] = val
            elif isinstance(raw.get(key), dict):
                raw[key] = val
        log.info("Strom-Rechnung erkannt (strom-Sektion im LLM-Output)")
    elif has_gas and not has_strom:
        # Reine Gas-Rechnung
        gas_data = raw.pop("gas")
        raw["energieart"] = "gas"
        for key, val in gas_data.items():
            if key not in raw or raw.get(key) in (0, 0.0, "", "Unbekannt", None):
                raw[key] = val
        log.info("Gas-Rechnung erkannt")
    elif raw.get("energieart") in ("strom", "gas", "kombi"):
        # Explizit gesetzte Energieart (z.B. aus validierten InvoiceFacts, §6 F6)
        # respektieren — keine Heuristik-Übersteuerung.
        pass
    else:
        # Kein strom/gas dict → Heuristik anhand Tarif/Lieferant
        tarif = _safe_str(raw.get("tarif_name", "")).lower()
        lieferant = _safe_str(raw.get("lieferant", "")).lower()
        if any(kw in tarif for kw in ("gas", "erdgas", "biogas")) and "strom" not in tarif:
            raw["energieart"] = "gas"
            log.info("Gas-Rechnung erkannt (Heuristik: Tarif enthält 'gas')")
        elif any(kw in lieferant for kw in ("gas",)) and "strom" not in lieferant and lieferant.strip().endswith("gas"):
            raw["energieart"] = "gas"
            log.info("Gas-Rechnung erkannt (Heuristik: Lieferant endet auf 'gas')")
        else:
            raw["energieart"] = "strom"

    # --- 2. Sanitize string fields ---
    for str_field in ("lieferant", "tarif_name", "kunde_name", "adresse", "zaehlpunkt"):
        raw[str_field] = _safe_str(raw.get(str_field, ""))
    raw.setdefault("lieferant", "Unbekannt")

    # Zählpunkt auf die kanonische 33-Zeichen-Form normalisieren (B.4-Merge:
    # punktierte/gespationierte Transkriptions-Varianten + Pauschal-Sentinel).
    # Nicht auf AT kanonisierbare Werte (LLM-Platzhalter, Prosa) fliegen raus.
    if raw.get("zaehlpunkt"):
        from energietools.tools.zaehlpunkt import canonical_zaehlpunkt

        canonical = canonical_zaehlpunkt(raw["zaehlpunkt"])
        raw["zaehlpunkt"] = canonical if canonical.startswith("AT") else ""

    plz = _safe_str(raw.get("plz", ""))
    raw["plz"] = plz if _re.match(r"^\d{4}$", plz) else ""

    # --- 3. Parse numeric fields from LLM output ---
    verbrauch = _safe_float(raw.get("verbrauch_kwh"))

    # New: extract from preiszeilen
    preiszeilen = raw.get("preiszeilen", [])
    if not isinstance(preiszeilen, list):
        preiszeilen = []

    # Legacy: arbeitspreis_ct_kwh (for backward compat with old prompt)
    arbeitspreis_raw = _safe_float(raw.get("arbeitspreis_ct_kwh"))
    arbeitspreis_netto_flag = raw.get("arbeitspreis_ist_netto", True)

    grundgebuehr_raw = _safe_float(raw.get("grundgebuehr_eur"))
    grundgebuehr_zeitraum = _safe_str(raw.get("grundgebuehr_zeitraum", "monat")).lower()
    grundgebuehr_netto_flag = raw.get("grundgebuehr_ist_netto", True)

    summe_energie = _safe_float(raw.get("summe_energieentgelte_eur"))
    summe_energie_netto_flag = raw.get("summe_energieentgelte_ist_netto", True)

    summe_netz = _safe_float(raw.get("summe_netzentgelte_eur"))
    summe_netz_netto_flag = raw.get("summe_netzentgelte_ist_netto", True)

    summe_steuern = _safe_float(raw.get("summe_steuern_abgaben_eur"))
    summe_steuern_netto_flag = raw.get("summe_steuern_abgaben_ist_netto", True)

    rechnungsbetrag_brutto = _safe_float(raw.get("rechnungsbetrag_brutto_eur"))

    # Backward compat: old LLM format with energiepreis_ct_kwh / energiekosten_eur
    if arbeitspreis_raw <= 0:
        arbeitspreis_raw = _safe_float(raw.get("energiepreis_ct_kwh"))
    if summe_energie <= 0:
        summe_energie = _safe_float(raw.get("energiekosten_eur"))
    if verbrauch <= 0:
        verbrauch = _safe_float(raw.get("jahresverbrauch_kwh"))
    netzkosten_legacy = _safe_float(raw.get("netzkosten_eur") or raw.get("netzkosten_eur_jahr"))
    if summe_netz <= 0 and netzkosten_legacy > 0:
        summe_netz = netzkosten_legacy
    grundgebuehr_legacy = _safe_float(raw.get("grundgebuehr_eur_monat"))
    if grundgebuehr_raw <= 0 and grundgebuehr_legacy > 0:
        grundgebuehr_raw = grundgebuehr_legacy
        grundgebuehr_zeitraum = "monat"

    # --- 4. Convert grundgebuehr to EUR/Monat brutto ---
    if grundgebuehr_zeitraum == "jahr":
        grundgebuehr_eur_monat_netto = grundgebuehr_raw / 12
    elif grundgebuehr_zeitraum == "zeitraum":
        # Divide by number of months in the billing period
        period_days = _compute_period_days(
            raw.get("zeitraum_von", ""), raw.get("zeitraum_bis", ""))
        months = (period_days / 30.44) if period_days and period_days > 0 else 12
        grundgebuehr_eur_monat_netto = grundgebuehr_raw / months
    else:
        grundgebuehr_eur_monat_netto = grundgebuehr_raw

    # Netto → Brutto
    if not grundgebuehr_netto_flag:
        grundgebuehr_eur_monat_netto = grundgebuehr_eur_monat_netto / 1.2
    grundgebuehr_eur_monat_brutto = grundgebuehr_eur_monat_netto * 1.2

    # --- 5. Convert summen to NETTO for calculation ---
    energie_netto = _to_netto(summe_energie, not summe_energie_netto_flag) if summe_energie > 0 else 0
    netz_netto = _to_netto(summe_netz, not summe_netz_netto_flag) if summe_netz > 0 else 0
    steuern_netto = _to_netto(summe_steuern, not summe_steuern_netto_flag) if summe_steuern > 0 else 0

    # --- 6. Determine Arbeitspreis (Plan A / Plan B / Plan C) ---
    energiepreis_ct_kwh_brutto = 0.0
    plan_used = ""

    # Plan A1: From preiszeilen (new, preferred)
    pz_preis, pz_netto, pz_plan = _pick_arbeitspreis_from_preiszeilen(preiszeilen, verbrauch)
    if pz_preis > 0:
        if pz_netto:
            plan_a_brutto = round(pz_preis * 1.2, 2)
        else:
            plan_a_brutto = round(pz_preis, 2)
        energiepreis_ct_kwh_brutto = plan_a_brutto
        plan_used = pz_plan
    # Plan A2: Legacy arbeitspreis_ct_kwh (backward compat)
    elif arbeitspreis_raw > 0 and verbrauch > 0:
        if arbeitspreis_netto_flag:
            plan_a_brutto = round(arbeitspreis_raw * 1.2, 2)
        else:
            plan_a_brutto = round(arbeitspreis_raw, 2)
        energiepreis_ct_kwh_brutto = plan_a_brutto
        plan_used = "A (Arbeitspreis legacy)"
    else:
        plan_a_brutto = 0.0

    # Plan B: Derive from summe_energieentgelte
    plan_b_brutto = 0.0
    if energie_netto > 0 and verbrauch > 0:
        period_days = _compute_period_days(
            raw.get("zeitraum_von", ""), raw.get("zeitraum_bis", ""))
        months = (period_days / 30.44) if period_days and period_days > 0 else 12
        grundgebuehr_im_zeitraum = grundgebuehr_eur_monat_netto * months
        reine_energie_netto = energie_netto - grundgebuehr_im_zeitraum
        if reine_energie_netto > 0:
            plan_b_brutto = round(reine_energie_netto / verbrauch * 100 * 1.2, 2)
            log.info("Plan B: Energieentgelte %.2f - Grundgebühr %.2f = %.2f netto → %.2f ct/kWh brutto",
                     energie_netto, grundgebuehr_im_zeitraum, reine_energie_netto, plan_b_brutto)

    # Plan C: Derive from Rechnungsbetrag
    plan_c_brutto = 0.0
    if rechnungsbetrag_brutto > 0 and verbrauch > 0:
        gesamt_netto = rechnungsbetrag_brutto / 1.2
        reine_energie_netto = gesamt_netto - netz_netto - steuern_netto
        period_days = _compute_period_days(
            raw.get("zeitraum_von", ""), raw.get("zeitraum_bis", ""))
        months = (period_days / 30.44) if period_days and period_days > 0 else 12
        reine_energie_netto -= grundgebuehr_eur_monat_netto * months
        if reine_energie_netto > 0:
            plan_c_brutto = round(reine_energie_netto / verbrauch * 100 * 1.2, 2)
            log.info("Plan C: Rechnungsbetrag → %.2f ct/kWh brutto", plan_c_brutto)

    # --- 6b. Cross-check & fallback (Option 6) ---
    # If Plan A and Plan B both exist, cross-check. If >15% divergence,
    # prefer Plan B (derived from totals = more reliable than single price line).
    if plan_a_brutto > 0 and plan_b_brutto > 0:
        diff_pct = abs(plan_a_brutto - plan_b_brutto) / plan_b_brutto * 100
        if diff_pct > 15:
            log.warning(
                "Cross-check FAILED: Plan A %.2f vs Plan B %.2f ct/kWh (%.1f%% Differenz) "
                "→ verwende Plan B (abgeleitet aus Summe Energieentgelte)",
                plan_a_brutto, plan_b_brutto, diff_pct)
            energiepreis_ct_kwh_brutto = plan_b_brutto
            plan_used = "B (cross-check fallback)"
        else:
            log.info("Cross-check OK: Plan A %.2f vs Plan B %.2f ct/kWh (%.1f%%)",
                     plan_a_brutto, plan_b_brutto, diff_pct)
    elif energiepreis_ct_kwh_brutto <= 0:
        # No Plan A → use Plan B or C
        if plan_b_brutto > 0:
            energiepreis_ct_kwh_brutto = plan_b_brutto
            plan_used = "B (abgeleitet)"
        elif plan_c_brutto > 0:
            energiepreis_ct_kwh_brutto = plan_c_brutto
            plan_used = "C (Rechnungsbetrag)"

    if plan_used:
        log.info("Arbeitspreis: %.2f ct/kWh brutto (Plan %s)", energiepreis_ct_kwh_brutto, plan_used)
    else:
        log.warning("Konnte keinen Arbeitspreis ermitteln")

    # --- 7. Compute energiekosten_eur (brutto) for the period ---
    energiekosten_eur_brutto = 0.0
    if energie_netto > 0:
        energiekosten_eur_brutto = round(energie_netto * 1.2, 2)
    elif energiepreis_ct_kwh_brutto > 0 and verbrauch > 0:
        energiekosten_eur_brutto = round(
            energiepreis_ct_kwh_brutto * verbrauch / 100 + grundgebuehr_eur_monat_brutto * 12, 2)

    # Netzkosten brutto
    netzkosten_brutto = round(netz_netto * 1.2, 2) if netz_netto > 0 else 0.0

    # --- 8. Plausibility checks ---
    if energiepreis_ct_kwh_brutto > 0 and not _plausibility_check("arbeitspreis_ct_kwh", energiepreis_ct_kwh_brutto):
        # Outside bounds — if Plan B is available and plausible, use it
        if plan_b_brutto > 0 and _plausibility_check("arbeitspreis_ct_kwh", plan_b_brutto):
            log.warning("Arbeitspreis %.2f implausibel → Fallback auf Plan B %.2f ct/kWh",
                        energiepreis_ct_kwh_brutto, plan_b_brutto)
            energiepreis_ct_kwh_brutto = plan_b_brutto
            plan_used = "B (plausibility fallback)"
        else:
            log.warning("Arbeitspreis %.2f ct/kWh außerhalb Plausibilitätsgrenzen — verwende trotzdem",
                        energiepreis_ct_kwh_brutto)
    if grundgebuehr_eur_monat_brutto > 0 and not _plausibility_check("grundgebuehr_eur_monat", grundgebuehr_eur_monat_brutto):
        log.warning("Grundgebühr %.2f EUR/Monat außerhalb Plausibilitätsgrenzen", grundgebuehr_eur_monat_brutto)
    if verbrauch > 0 and not _plausibility_check("verbrauch_kwh", verbrauch):
        log.warning("Verbrauch %.0f kWh außerhalb Plausibilitätsgrenzen", verbrauch)

    # --- 8b. Rechenweg (auditierbar): wie die Felder hergeleitet wurden ---
    # Macht die deterministischen Schritte + Annahmen sichtbar (keine stillen
    # Defaults): welcher Arbeitspreis-Plan, die Kandidaten, ob der Zeitraum
    # bekannt war, und welche Werte außerhalb der Plausibilitätsgrenzen liegen.
    period_days_rw = _compute_period_days(raw.get("zeitraum_von", ""), raw.get("zeitraum_bis", ""))
    hinweise: list[str] = []
    if period_days_rw is None:
        hinweise.append(
            "Abrechnungszeitraum nicht erkannt — 12 Monate angenommen "
            "(Schätzung der Grundgebühr-Periode, keine Abrechnung)."
        )
    if energiepreis_ct_kwh_brutto > 0 and not _plausibility_check(
        "arbeitspreis_ct_kwh", energiepreis_ct_kwh_brutto
    ):
        hinweise.append(
            f"Arbeitspreis {energiepreis_ct_kwh_brutto:.2f} ct/kWh außerhalb der "
            f"Plausibilitätsgrenzen — bitte prüfen."
        )
    if grundgebuehr_eur_monat_brutto > 0 and not _plausibility_check(
        "grundgebuehr_eur_monat", grundgebuehr_eur_monat_brutto
    ):
        hinweise.append(
            f"Grundgebühr {grundgebuehr_eur_monat_brutto:.2f} EUR/Monat außerhalb "
            f"der Plausibilitätsgrenzen — bitte prüfen."
        )
    if verbrauch > 0 and not _plausibility_check("verbrauch_kwh", verbrauch):
        hinweise.append(
            f"Verbrauch {verbrauch:.0f} kWh außerhalb der Plausibilitätsgrenzen — bitte prüfen."
        )

    rechenweg = {
        "arbeitspreis_plan": plan_used or "keiner",
        "arbeitspreis_kandidaten_ct_kwh_brutto": {
            "plan_a": round(plan_a_brutto, 2),
            "plan_b": round(plan_b_brutto, 2),
            "plan_c": round(plan_c_brutto, 2),
        },
        "arbeitspreis_ct_kwh_brutto": round(energiepreis_ct_kwh_brutto, 2),
        "grundgebuehr_eur_monat_brutto": round(grundgebuehr_eur_monat_brutto, 2),
        "ust_faktor": 1.2,
        "zeitraum_tage": period_days_rw,
        "zeitraum_bekannt": period_days_rw is not None,
        "energieart": raw.get("energieart", "strom"),
        "hinweise": hinweise,
    }

    # --- 9. Build output dict in Invoice-compatible format ---
    result = {
        "lieferant": raw.get("lieferant", "Unbekannt"),
        "tarif_name": raw.get("tarif_name", ""),
        "energiepreis_ct_kwh": energiepreis_ct_kwh_brutto,
        "grundgebuehr_eur_monat": round(grundgebuehr_eur_monat_brutto, 2),
        "energiekosten_eur": energiekosten_eur_brutto,
        "verbrauch_kwh": verbrauch,
        "zeitraum_von": raw.get("zeitraum_von", ""),
        "zeitraum_bis": raw.get("zeitraum_bis", ""),
        "plz": raw.get("plz", ""),
        "zaehlpunkt": raw.get("zaehlpunkt", ""),
        "netzkosten_eur": netzkosten_brutto,
        "kunde_name": raw.get("kunde_name", ""),
        "adresse": raw.get("adresse", ""),
        "energieart": raw.get("energieart", "strom"),
        "gas": raw.get("gas"),
        "rechenweg": rechenweg,
        # B.4-Merge: Rechnungsbetrag (Basis der Hauptmetrik) + EVU-Prognose.
        "rechnungsbetrag_brutto_eur": rechnungsbetrag_brutto,
        "jahresverbrauch_prognose_kwh": _safe_float(
            raw.get("jahresverbrauch_prognose_kwh"),
        ),
    }

    # --- 10. Annualize partial-year invoices (setzt jahreskosten_brutto_eur) ---
    result = _annualize_invoice(result)

    # --- 11. Warnings (Extraktionsqualität, B.4-Merge) ---
    result["warnings"] = _collect_warnings(result)

    return result


def _collect_warnings(result: dict) -> list[str]:
    """Extraktionsqualitäts-Hinweise für Konsumenten (leer = saubere Extraktion).

    Deterministische Flags auf dem fertig aufbereiteten Dict (post-
    Annualisierung): fehlender Rechnungsbetrag/Verbrauch, unvollständige
    Wechselformular-Adresse, implausibler effektiver All-in-Preis.
    """
    out: list[str] = []
    rb = float(result.get("rechnungsbetrag_brutto_eur", 0.0) or 0.0)
    jv = float(result.get("jahresverbrauch_kwh", 0.0) or 0.0)
    # jahreskosten_brutto_eur ist bereits auf dieselbe Jahresbasis annualisiert
    # wie jahresverbrauch_kwh (beide × 365/Periodentage). rechnungsbetrag_brutto_eur
    # bleibt dagegen ein Periodenwert — ihn mit dem Jahres-kWh zu teilen ergäbe bei
    # jeder unterjährigen Rechnung einen zu niedrigen Effektivpreis und eine falsche
    # Warnung (Fund gridbert-Gegenlese).
    jk = float(result.get("jahreskosten_brutto_eur", 0.0) or 0.0)
    if rb <= 0:
        out.append("rechnungsbetrag_missing")
    if jv <= 0:
        out.append("verbrauch_missing")
    if _is_address_incomplete(_safe_str(result.get("adresse", ""))):
        out.append("adresse_incomplete")
    if jk > 0 and jv > 0:
        # Effektiver All-in ct/kWh — Österreich liegt typisch zwischen 18 und
        # 60 ct/kWh brutto inkl. Netz/Steuern. Außerhalb 8–80 ist ein starkes
        # Signal für eine Feldverwechslung. Zähler und Nenner auf gleicher
        # Jahresbasis (jahreskosten_brutto_eur / jahresverbrauch_kwh).
        eff = jk / jv * 100.0
        if eff < 8 or eff > 80:
            out.append(f"effective_price_implausible:{eff:.1f}ct_kwh")
    return out
