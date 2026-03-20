# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Rechnungs-Extraktion via Claude Vision API oder Ollama (Fallback)."""

from __future__ import annotations

import base64
import datetime
import io
import json
import logging
from pathlib import Path
from typing import Any

import pdfplumber

from energietools.models import Invoice

log = logging.getLogger(__name__)

EXTRACTION_PROMPT = """\
Extrahiere aus dieser österreichischen Strom- oder Gasrechnung die folgenden Felder. \
Antworte AUSSCHLIESSLICH mit einem JSON-Objekt. Kein Text davor, kein Text danach. \
Nur das JSON.

```json
{
  "lieferant": "Name des Stromlieferanten",
  "tarif_name": "Name des Tarifs",
  "energiepreis_ct_kwh": 0.0,
  "grundgebuehr_eur_monat": 0.0,
  "energiekosten_eur": 0.0,
  "verbrauch_kwh": 0.0,
  "zeitraum_von": "",
  "zeitraum_bis": "",
  "plz": "0000",
  "zaehlpunkt": "AT00...",
  "netzkosten_eur": 0.0,
  "kunde_name": "Vor- und Nachname des Kunden",
  "adresse": "Straße Hausnummer/Tür, PLZ Ort"
}
```

Regeln:
- energiepreis_ct_kwh = Arbeitspreis/Energiepreis in CENT pro kWh, BRUTTO (inkl. 20% MwSt). \
Falls nur netto angegeben: × 1.2 rechnen.
- grundgebuehr_eur_monat = Grundpauschale/Grundgebühr in EURO pro MONAT, BRUTTO. \
Falls als €/Jahr angegeben: durch 12 teilen.
- energiekosten_eur = Gesamte Energiekosten (Arbeitspreis + Grundgebühr) in EURO, BRUTTO, \
für den Abrechnungszeitraum. Auf der Rechnung oft als "Energiekosten" oder "Summe Energie" \
ausgewiesen. OHNE Netzkosten. NICHT hochrechnen — den EXAKTEN Betrag von der Rechnung.
- verbrauch_kwh = Gesamtverbrauch in kWh für den Abrechnungszeitraum. \
NICHT hochrechnen — den EXAKTEN Verbrauch wie auf der Rechnung angegeben.
- zeitraum_von = Beginn des Abrechnungszeitraums im Format TT.MM.JJJJ (z.B. "01.01.2024"). \
Steht auf der Rechnung als "Abrechnungszeitraum", "Verrechnungszeitraum", "von ... bis ...".
- zeitraum_bis = Ende des Abrechnungszeitraums im Format TT.MM.JJJJ (z.B. "31.12.2024").
- netzkosten_eur = Netzkosten (Netzentgelt + Abgaben + Steuern) in EURO, BRUTTO, \
für den Abrechnungszeitraum. NICHT hochrechnen — den EXAKTEN Betrag von der Rechnung. \
Oft als "Netzkosten", "Netzentgelt" oder "Systemnutzungsentgelt" ausgewiesen.
- kunde_name = Name des Kunden/Rechnungsempfängers (z.B. "Helene Markom"). \
Ohne Titel (Mag., Dr., etc.) — nur Vor- und Nachname.
- adresse = Vollständige Adresse des Kunden EXAKT wie auf der Rechnung. \
Lies die Straße sorgfältig ab — achte auf ähnliche Buchstaben (u/ri/ch).
- Alle Zahlenfelder als Dezimalzahlen (z.B. 19.68, nicht "19,68")
- Falls ein Feld nicht gefunden wird: 0 für Zahlen, "" für Strings

WICHTIG: Antworte NUR mit dem JSON. Keine Erklärung, keine Markdown-Überschriften, \
nur das JSON-Objekt. Alle Werte EXAKT wie auf der Rechnung — NICHTS hochrechnen oder umrechnen \
(außer netto→brutto und Jahr→Monat bei der Grundgebühr).
"""


# --- PDF/Bild Helpers (wiederverwendet aus v0.2) ------------------------------

def _pdf_to_images(pdf_path: Path) -> list[bytes]:
    """Konvertiere PDF-Seiten zu PNG-Bildern für Vision-Modell."""
    images: list[bytes] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            img = page.to_image(resolution=200)
            buf = io.BytesIO()
            img.original.save(buf, format="PNG")
            images.append(buf.getvalue())
    return images


def _pdf_to_text(pdf_path: Path) -> str:
    """Extrahiere Text aus PDF."""
    pages: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n\n".join(pages)


def _parse_json_response(text: str) -> dict:
    """Extrahiere JSON aus LLM-Antwort (auch wenn drumherum Text steht)."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Suche nach JSON-Block in Markdown-Codeblock
    if "```" in text:
        for block in text.split("```"):
            block = block.strip()
            if block.startswith("json"):
                block = block[4:].strip()
            try:
                return json.loads(block)
            except json.JSONDecodeError:
                continue

    # Suche nach erstem { ... } Block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Konnte kein JSON aus LLM-Antwort extrahieren: {text[:200]}")


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
    """Annualize partial-year invoice data deterministically in Python.

    Takes the raw LLM extraction dict (with verbrauch_kwh, energiekosten_eur,
    zeitraum_von, zeitraum_bis) and produces annualized jahresverbrauch_kwh
    and energiekosten_eur plus period metadata.

    Mutates and returns the dict.
    """
    von = raw.get("zeitraum_von", "")
    bis = raw.get("zeitraum_bis", "")
    period_days = _compute_period_days(von, bis)

    # Map new field names to model field names
    raw_verbrauch = raw.pop("verbrauch_kwh", 0.0) or 0.0
    raw_kosten = raw.get("energiekosten_eur", 0.0) or 0.0
    raw_netzkosten = raw.pop("netzkosten_eur", None)

    # Store period metadata
    raw["zeitraum_von"] = von
    raw["zeitraum_bis"] = bis
    raw["zeitraum_tage"] = period_days

    # Threshold: invoices >= 300 days are treated as annual (allow billing variations)
    if period_days is not None and period_days < 300 and period_days > 0:
        # Annualize: scale to 365 days
        factor = 365.0 / period_days
        raw["jahresverbrauch_kwh"] = round(raw_verbrauch * factor, 1)
        raw["energiekosten_eur"] = round(raw_kosten * factor, 2)
        raw["ist_hochgerechnet"] = True
        raw["original_verbrauch_kwh"] = raw_verbrauch
        raw["original_energiekosten_eur"] = raw_kosten
        # Annualize network costs too if present
        if raw_netzkosten and raw_netzkosten > 0:
            raw["netzkosten_eur_jahr"] = round(raw_netzkosten * factor, 2)
        log.info(
            "Invoice annualized: %d days → factor %.2f, "
            "%.1f kWh → %.1f kWh/year, %.2f EUR → %.2f EUR/year",
            period_days, factor,
            raw_verbrauch, raw["jahresverbrauch_kwh"],
            raw_kosten, raw["energiekosten_eur"],
        )
    else:
        # Annual or unknown period — use values as-is
        raw["jahresverbrauch_kwh"] = raw_verbrauch
        raw["ist_hochgerechnet"] = False
        # Map netzkosten_eur → netzkosten_eur_jahr (already annual or close enough)
        if raw_netzkosten and raw_netzkosten > 0:
            raw["netzkosten_eur_jahr"] = raw_netzkosten

    return raw


def _detect_image_media_type(image_b64: str) -> str:
    """Detect actual image media type from base64 data using magic bytes."""
    raw = base64.b64decode(image_b64[:32])  # first few bytes suffice
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return "image/png"  # fallback


# --- LLM-based extraction (Claude or OpenAI via LLMProvider) ------------------

def _extract_via_llm(
    llm_provider: Any = None,
    text: str = "",
    image_b64: str = "",
) -> dict:
    """Extrahiere Rechnungsdaten via LLM Provider (Claude Vision, OpenAI, etc.)."""
    if llm_provider is None:
        # Fallback: create Claude provider from server config
        import os; ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', ''); CLAUDE_MODEL = os.environ.get('CLAUDE_MODEL', 'claude-sonnet-4-20250514')
        from energietools.llm import create_provider

        llm_provider = create_provider("claude", ANTHROPIC_API_KEY, CLAUDE_MODEL)

    if image_b64:
        media_type = _detect_image_media_type(image_b64)
        attachments = [{"media_type": media_type, "data": image_b64, "file_name": "rechnung"}]
        user_content = llm_provider.build_user_content(EXTRACTION_PROMPT, attachments)
    else:
        prompt = (
            f"Hier ist der Text einer österreichischen Stromrechnung:\n\n"
            f"{text}\n\n{EXTRACTION_PROMPT}"
        )
        user_content = prompt

    response = llm_provider.chat(
        system="Du bist ein Experte für österreichische Stromrechnungen.",
        messages=[{"role": "user", "content": user_content}],
        tools=[],
        max_tokens=1024,
    )

    response_text = "\n".join(response.text_parts)
    return _parse_json_response(response_text)


# --- Ollama Fallback (für self-hosted) ----------------------------------------

def _extract_via_ollama(text: str = "", image_b64: str = "") -> dict:
    """Extrahiere Rechnungsdaten via Ollama (Fallback für self-hosted)."""
    import ollama

    import os; OLLAMA_HOST = os.environ.get('OLLAMA_HOST', 'http://localhost:11434'); OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'llama3.2'); OLLAMA_VISION_MODEL = os.environ.get('OLLAMA_VISION_MODEL', 'llama3.2-vision')

    client = ollama.Client(host=OLLAMA_HOST, timeout=300)

    if image_b64:
        response = client.chat(
            model=OLLAMA_VISION_MODEL,
            messages=[{
                "role": "user",
                "content": EXTRACTION_PROMPT,
                "images": [image_b64],
            }],
        )
    else:
        response = client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": f"Hier ist der Text einer österreichischen Stromrechnung:\n\n{text}",
                },
                {
                    "role": "assistant",
                    "content": "Ich habe den Rechnungstext gelesen. Was soll ich damit tun?",
                },
                {"role": "user", "content": EXTRACTION_PROMPT},
            ],
        )

    return _parse_json_response(response.message.content)


# --- Haupt-Funktion -----------------------------------------------------------

def parse_invoice(file_path: str | Path, llm_provider: Any = None) -> Invoice:
    """Extrahiere Rechnungsdaten aus PDF oder Bild.

    Uses the provided LLM provider, falls back to Claude API or Ollama.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Datei nicht gefunden: {path}")

    # Determine extraction backend
    import os; _server_key = os.environ.get('ANTHROPIC_API_KEY', '')

    if llm_provider is not None or _server_key:
        def extract_fn(text: str = "", image_b64: str = "") -> dict:
            return _extract_via_llm(llm_provider=llm_provider, text=text, image_b64=image_b64)
        backend_name = llm_provider.provider_name if llm_provider else "Claude"
    else:
        extract_fn = _extract_via_ollama
        backend_name = "Ollama"

    if path.suffix.lower() == ".pdf":
        text = _pdf_to_text(path)
        if text.strip():
            # Text kürzen falls zu lang
            if len(text) > 6000:
                text = text[:6000]
                log.info("PDF-Text auf 6000 Zeichen gekürzt")
            log.info("Sende PDF-Text (%d Zeichen) an %s", len(text), backend_name)
            raw = extract_fn(text=text)
        else:
            # Scan-PDF → Vision mit erster Seite
            images = _pdf_to_images(path)
            if not images:
                raise ValueError(f"PDF enthält weder Text noch Bilder: {path}")
            log.info("PDF ist Scan — sende Seite 1 an %s Vision", backend_name)
            raw = extract_fn(image_b64=base64.b64encode(images[0]).decode())
    else:
        # Bild (JPG, PNG, etc.)
        log.info("Sende Bild an %s Vision", backend_name)
        raw = extract_fn(image_b64=base64.b64encode(path.read_bytes()).decode())

    # Defaults für fehlende Felder
    raw.setdefault("lieferant", "Unbekannt")
    raw.setdefault("energiepreis_ct_kwh", 0.0)
    raw.setdefault("energiekosten_eur", 0.0)
    raw.setdefault("verbrauch_kwh", 0.0)
    raw.setdefault("plz", "")

    # --- Backward compat: old LLM responses may use jahresverbrauch_kwh ---
    if "jahresverbrauch_kwh" in raw and "verbrauch_kwh" not in raw:
        raw["verbrauch_kwh"] = raw.pop("jahresverbrauch_kwh")
    elif "jahresverbrauch_kwh" in raw:
        raw.pop("jahresverbrauch_kwh", None)

    # --- Backward compat: old field name netzkosten_eur_jahr ---------------
    if "netzkosten_eur_jahr" in raw and "netzkosten_eur" not in raw:
        raw["netzkosten_eur"] = raw.pop("netzkosten_eur_jahr")

    # --- Deterministic annualization in Python (NOT the LLM) ---------------
    raw = _annualize_invoice(raw)

    # Fallback: derive energiepreis from energiekosten if extraction missed per-kWh price
    kwh = raw.get("jahresverbrauch_kwh", 0.0)
    preis = raw.get("energiepreis_ct_kwh", 0.0)
    kosten = raw.get("energiekosten_eur", 0.0)
    grundgebuehr = raw.get("grundgebuehr_eur_monat", 0.0)

    if preis <= 0 and kosten > 0 and kwh > 0:
        # Derive per-kWh price: (energiekosten - grundgebuehr*12) / kWh * 100
        reine_energie = kosten - grundgebuehr * 12
        if reine_energie > 0:
            raw["energiepreis_ct_kwh"] = round(reine_energie / kwh * 100, 2)
            log.info("Energiepreis abgeleitet: %.2f ct/kWh (aus Energiekosten %.2f EUR)",
                     raw["energiepreis_ct_kwh"], kosten)

    # Fallback: derive energiekosten from energiepreis if total wasn't extracted
    if kosten <= 0 and preis > 0 and kwh > 0:
        raw["energiekosten_eur"] = round(kwh * preis / 100 + grundgebuehr * 12, 2)

    log.info("Extrahierte Rechnungsdaten: %s", raw)
    return Invoice(**raw)
