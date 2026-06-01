# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Wechsel-Dokumente — vorausgefüllte PDFs für Tarifwechsel und BEG-Beitritt."""

from __future__ import annotations

import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fpdf import FPDF

from energietools.models import BEGCalculation, Invoice, Tariff

log = logging.getLogger(__name__)


class _GridbertPDF(FPDF):
    """PDF mit Gridbert-Branding."""

    def header(self) -> None:
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(22, 163, 74)  # green-dark
        self.cell(0, 8, "Gridbert - Dein Energie-Agent", align="R")
        self.ln(12)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(100, 116, 139)
        self.cell(0, 10, f"Erstellt am {datetime.now(tz=timezone.utc).strftime('%d.%m.%Y')} | Alle Preise brutto inkl. 20% MwSt.", align="C")


def _add_section(pdf: _GridbertPDF, title: str) -> None:
    """Abschnitts-Überschrift."""
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 10, title)
    pdf.ln(8)
    pdf.set_draw_color(34, 197, 94)
    pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 180, pdf.get_y())
    pdf.ln(4)


def _add_field(pdf: _GridbertPDF, label: str, value: str) -> None:
    """Label + Wert auf einer Zeile."""
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(55, 7, label)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 7, value)
    pdf.ln(7)


def generate_switching_pdf(
    *,
    user_name: str = "",
    user_address: str = "",
    plz: str = "",
    zaehlpunkt: str = "",
    iban: str = "",
    email: str = "",
    current_lieferant: str = "",
    current_tarif: str = "",
    current_energiepreis: float = 0.0,
    current_grundgebuehr: float = 0.0,
    target_lieferant: str = "",
    target_tarif: str = "",
    target_energiepreis: float = 0.0,
    target_grundgebuehr: float = 0.0,
    target_jahreskosten: float = 0.0,
    target_ist_oekostrom: bool = False,
    jahresverbrauch_kwh: float = 0.0,
    savings_eur: float = 0.0,
) -> Path:
    """Gridbert-Vollmacht als PDF generieren.

    Vollmacht an Ben Moerzinger / Gridbert (nicht an den neuen Lieferanten).
    Basiert auf dem OGH-orientierten Energy Hero Modell.
    """
    pdf = _GridbertPDF()
    pdf.add_page()

    # Titel
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 12, "VOLLMACHT")
    pdf.ln(12)

    # Vollmachtgeber
    _add_section(pdf, "Vollmachtgeber")
    _add_field(pdf, "Name:", user_name or "____________________________")
    _add_field(pdf, "Adresse:", user_address or "____________________________")
    _add_field(pdf, "PLZ / Ort:", plz or "________")
    _add_field(pdf, "E-Mail:", email or "____________________________")
    pdf.ln(4)

    # Bevollmächtigter
    _add_section(pdf, "Bevollmächtigter")
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 7, "Ben Mörzinger / Gridbert")
    pdf.ln(7)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(0, 6, "E-Mail: ben@moerzinger.eu | Web: www.gridbert.at")
    pdf.ln(10)

    # Zählpunkt + Verbrauch
    _add_section(pdf, "Anschlussdaten")
    _add_field(pdf, "Zählpunkt:", zaehlpunkt or "AT00____________________________")
    _add_field(pdf, "Jahresverbrauch:", f"{jahresverbrauch_kwh:.0f} kWh" if jahresverbrauch_kwh else "________")
    _add_field(pdf, "IBAN:", iban or "____________________________")
    _add_field(pdf, "Akt. Lieferant:", current_lieferant or "____________________________")
    pdf.ln(2)

    # Wechsel-Details
    _add_section(pdf, "Geplanter Wechsel")
    _add_field(pdf, "Neuer Lieferant:", target_lieferant)
    _add_field(pdf, "Tarif:", target_tarif)
    if target_energiepreis > 0:
        _add_field(pdf, "Energiepreis:", f"{target_energiepreis:.2f} ct/kWh")
    if target_grundgebuehr > 0:
        _add_field(pdf, "Grundgebühr:", f"{target_grundgebuehr:.2f} EUR/Monat")
    if target_jahreskosten > 0:
        _add_field(pdf, "Jahreskosten:", f"{target_jahreskosten:.2f} EUR/Jahr")
    oeko = "Ja" if target_ist_oekostrom else "Nein"
    _add_field(pdf, "Ökostrom:", oeko)

    if savings_eur > 0:
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(22, 163, 74)
        pdf.cell(0, 8, f"Geschätzte Ersparnis: {savings_eur:.2f} EUR/Jahr")
        pdf.ln(10)
    else:
        pdf.ln(6)

    # Vollmachts-Text (OGH-orientiert, Energy Hero Modell)
    _add_section(pdf, "1. Energieanbieterwechsel")
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(30, 41, 59)
    pdf.multi_cell(0, 4.5,
        "Der Bevollmächtigte wird ermächtigt, in meinem Namen und auf meine Rechnung:\n\n"
        "a) Strom- und/oder Gastarife am österreichischen Energiemarkt zu vergleichen "
        "und den für mich wirtschaftlich günstigsten Tarif zu ermitteln;\n\n"
        "b) Vertragserklärungen, die für einen Strom- und/oder Gasanbieterwechsel "
        "erforderlich sind, rechtsverbindlich für mich abzugeben, insbesondere:\n"
        "   - den Abschluss eines neuen Energieliefervertrags beim günstigsten Anbieter;\n"
        "   - die Kündigung des bestehenden Energieliefervertrags, sofern keine "
        "Bindungsfrist entgegensteht;\n"
        "   - das Ausfüllen und Absenden von Online-Formularen, internetbasierten "
        "Eingabemasken und vergleichbaren elektronischen Wechselvorgängen beim "
        "Netzbetreiber und/oder Energieanbieter;\n\n"
        "c) Erklärungen und Informationen im Zusammenhang mit dem Anbieterwechsel "
        "für mich entgegenzunehmen."
    )
    pdf.ln(6)

    # Scope 2 (Datenzugang) und Umfang auf Seite 2
    pdf.add_page()

    _add_section(pdf, "2. Umfang und Dauer")
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(30, 41, 59)
    pdf.multi_cell(0, 4.5,
        "Diese Vollmacht ist auf die oben genannten Handlungen beschränkt. "
        "Sie berechtigt insbesondere NICHT zur Änderung meiner Netzanschluss-Bedingungen, "
        "zur Stilllegung oder Änderung meines Zählers, oder zur Weitergabe meiner "
        "Daten an Dritte.\n\n"
        "Diese Vollmacht gilt bis auf Widerruf. Der Widerruf ist jederzeit schriftlich "
        "(auch per E-Mail an ben@moerzinger.eu) möglich und wird unverzüglich wirksam."
    )
    pdf.ln(6)

    _add_section(pdf, "3. Datenschutz")
    pdf.set_font("Helvetica", "", 8.5)
    pdf.multi_cell(0, 4.5,
        "Der Bevollmächtigte verpflichtet sich, meine personenbezogenen Daten "
        "(einschließlich Zugangsdaten und Verbrauchsdaten) ausschließlich zum Zweck "
        "der Tarifoptimierung zu verwenden, verschlüsselt zu speichern und bei "
        "Widerruf der Vollmacht unverzüglich zu löschen."
    )
    pdf.ln(6)

    # Digitale Bestätigung
    now = datetime.now(tz=timezone.utc)
    _add_section(pdf, "Digitale Bestätigung")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(30, 41, 59)
    pdf.multi_cell(0, 5,
        f"Diese Vollmacht wurde am {now.strftime('%d.%m.%Y')} um {now.strftime('%H:%M')} Uhr (UTC) "
        f"von {user_name or '[Name]'} über die Gridbert-Plattform digital erteilt und bestätigt. "
        f"Die Erteilung erfolgte in Textform gemäß § 886a ABGB."
    )
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(55, 7, "Vollmachtgeber:")
    pdf.cell(0, 7, user_name or "____________________________")
    pdf.ln(7)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(55, 7, "")
    pdf.cell(0, 7, f"E-Mail: {email}" if email else "")

    # Speichern
    tmpdir = tempfile.mkdtemp(prefix="gridbert_pdf_")
    out_path = Path(tmpdir) / "gridbert_vollmacht.pdf"
    pdf.output(str(out_path))
    log.info("Gridbert-Vollmacht erstellt: %s", out_path)
    return out_path


def generate_beg_joining_pdf(
    invoice: Invoice,
    beg: BEGCalculation,
    profile: dict | None = None,
    netzbetreiber: str = "",
) -> Path:
    """BEG-Beitritts-Checkliste als PDF generieren."""
    profile = profile or {}

    pdf = _GridbertPDF()
    pdf.add_page()

    # Titel
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 12, f"Beitritt: {beg.beg_name}")
    pdf.ln(16)

    # Deine Daten
    _add_section(pdf, "Deine Daten")
    _add_field(pdf, "Name:", profile.get("name", "____________________________"))
    _add_field(pdf, "PLZ / Ort:", invoice.plz or profile.get("plz", "________"))
    _add_field(pdf, "Zählpunkt:", invoice.zaehlpunkt or "AT00____________________________")
    _add_field(pdf, "Netzbetreiber:", netzbetreiber or profile.get("netzbetreiber", "-"))
    _add_field(pdf, "Akt. Lieferant:", invoice.lieferant)
    pdf.ln(4)

    # BEG-Details
    _add_section(pdf, "Energiegemeinschaft")
    _add_field(pdf, "Name:", beg.beg_name)
    _add_field(pdf, "Website:", beg.beg_url)
    _add_field(pdf, "BEG-Preis:", f"{beg.beg_preis_ct_kwh:.2f} ct/kWh")
    _add_field(pdf, "Dein akt. Preis:", f"{beg.aktueller_preis_ct_kwh:.2f} ct/kWh")
    _add_field(pdf, "Versorgungsanteil:", f"{beg.versorgungsanteil * 100:.0f}%")
    if beg.einmalkosten_eur > 0:
        _add_field(pdf, "Einmalkosten:", f"{beg.einmalkosten_eur:.0f} EUR")
    pdf.ln(2)

    # Ersparnis
    if beg.ersparnis_jahr_eur > 0:
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(22, 163, 74)
        pdf.cell(0, 8, f"Geschaetzte Ersparnis: {beg.ersparnis_jahr_eur:.2f} EUR/Jahr")
        pdf.ln(12)

    # Checkliste
    _add_section(pdf, "Beitritts-Checkliste")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(30, 41, 59)

    steps = [
        f"[ ] Online-Registrierung auf {beg.beg_url}",
        f"[ ] Datenfreigabe beim Netzbetreiber ({netzbetreiber or '?'}) aktivieren",
        f"[ ] Zählpunkt {invoice.zaehlpunkt or 'AT00...'} bei {beg.beg_name} hinterlegen",
        "[ ] Bestätigung der Zuweisung abwarten (kann einige Wochen dauern)",
        "[ ] Bisherigen Stromlieferant als Reststromlieferant beibehalten",
    ]
    for step in steps:
        pdf.cell(0, 7, step)
        pdf.ln(7)
    pdf.ln(6)

    # Hinweis
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(100, 116, 139)
    pdf.multi_cell(0, 5,
        "Hinweis: Der Beitritt zu einer Energiegemeinschaft ersetzt NICHT deinen "
        "Stromlieferanten. Du behältst deinen bisherigen Vertrag und beziehst "
        "zusätzlich günstigeren Strom aus der BEG. Der BEG-Anteil wird direkt "
        "mit deinem Verbrauch verrechnet."
    )
    if beg.notiz:
        pdf.ln(4)
        pdf.multi_cell(0, 5, f"Info: {beg.notiz}")

    # Speichern
    tmpdir = tempfile.mkdtemp(prefix="gridbert_pdf_")
    out_path = Path(tmpdir) / "beg_beitritt.pdf"
    pdf.output(str(out_path))
    log.info("BEG-PDF erstellt: %s", out_path)
    return out_path
