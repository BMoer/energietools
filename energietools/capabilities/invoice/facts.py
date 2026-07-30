# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""InvoiceFacts — das validierende Fakten-Schema (D2.2) mit Rejection-Semantik.

Ein (User-)LLM liest die Rechnung und übergibt FAKTEN — gerechnet wird hier,
deterministisch. Das Schema ist strikt: Garbage wird ABGELEHNT, nie still zu
0.0 koerziert (das ``_safe_float``-Erbe gilt hier ausdrücklich nicht).
``PreisCtKwh`` und ``Betrag`` sind getrennte Typen — der Feldname trägt die
Einheit, damit die ct-vs-EUR-Ambiguität (Faktor-100-Fehler) nicht im Schema
selbst angelegt ist.

Bei Verstoß liefert :func:`pruefe_invoice_facts` strukturierte Fehler
(``{feld, regel, wert, rueckfrage}``) — die Rückfrage geht über das Tool-
Result zurück an das LLM (Ablösung des serverseitigen Verifier-Recalls).

Logging-Policy: dieses Modul loggt NIE Eingabewerte (Beträge, Zählpunkt,
Adresse, Zitate) — die vollständige Fehlerinformation gehört ausschließlich
ins Tool-Result.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from energietools.tools.zaehlpunkt import validate as _zp_validate

_UST = 1.2

# DE-Rechnungsdatum (TT.MM.JJJJ) → wird im Before-Validator nach ISO normalisiert.
_DE_DATUM_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")

# Plausibilitätsgrenzen (brutto) für österreichische Energierechnungen —
# identisch zu ``tools.invoice_parser._PLAUSIBILITY`` (eine Quelle der Zahlen).
#
# Die Obergrenzen fangen **Einheiten- und Zahlendreher**, sie unterstellen keine
# Kundengröße. Bis 2026-07-28 taten sie genau das: `verbrauch_kwh <= 100.000` und
# `grundgebuehr <= 30 EUR/Monat` beschrieben einen Haushalt und wiesen damit reale
# Betriebe ab — ein betreuter Kunde liegt bei rund 136.300 kWh im Jahr, und
# Grundgebühren von 50 bis 200 EUR/Monat sind mit Lastprofilzähler normal. Das traf
# ausgerechnet die Fälle, für die das Berater-Tier gebaut ist.
#
# Die Grenzen liegen jetzt dort, wo ein Wert nur noch ein Erfassungsfehler sein kann:
# 20 GWh Jahresverbrauch fängt den Wh-statt-kWh-Dreher (Faktor 1.000), 1.000 EUR
# Grundgebühr im Monat den Jahres-statt-Monats-Dreher bei realen Gewerbewerten. Gegen
# vertauschte Größenordnungen innerhalb des plausiblen Bereichs schützen nicht diese
# Schranken, sondern die Untergrenzen, der Anker-Zwang (jede Zahl braucht ein
# wörtliches Zitat) und die Cross-Field-Prüfungen.
PLAUSIBILITAET = {
    "arbeitspreis_ct_kwh": (3.0, 80.0),
    "grundgebuehr_eur_monat": (0.0, 1_000.0),
    "verbrauch_kwh": (10.0, 20_000_000.0),
    "kosten_eur": (5.0, 5_000_000.0),
}

# Effektivpreis-Anker (EUR/kWh) + Brutto-Floor des deterministischen
# Rechnungsbetrag-Detektors (Port von ``_needs_brutto_verification``).
_EFFEKTIV_MIN_EUR_KWH = 0.05
_EFFEKTIV_MAX_EUR_KWH = 1.00
_BRUTTO_FLOOR_EUR = 30.0

# Netto/Brutto-Konsistenz: Summe der Netto-Blöcke × 1,2 vs. Rechnungsbetrag.
# Toleranz ±15 % (Rundungen, Rabatte, Teilbeträge) — NEU per D2.2, kein Port.
_KONSISTENZ_TOLERANZ = 0.15

# Prognose-Fenster: EVU-Jahresprognose vs. Tages-Hochrechnung (±30 %).
_PROGNOSE_FENSTER = 0.30


class Betrag(BaseModel):
    """EUR-Summe eines Rechnungsblocks. ``ist_netto`` ist PFLICHT — keine Default-Annahme."""

    model_config = ConfigDict(extra="forbid", strict=True)

    wert_eur: float
    ist_netto: bool


class PreisCtKwh(BaseModel):
    """Energiepreis in ct/kWh — eigener Typ, Feldname trägt die Einheit."""

    model_config = ConfigDict(extra="forbid", strict=True)

    wert_ct_kwh: float
    ist_netto: bool


class Grundgebuehr(BaseModel):
    """Grundgebühr mit Pflicht-Zeitraum (monat/jahr) und Netto-Flag."""

    model_config = ConfigDict(extra="forbid", strict=True)

    wert_eur: float
    zeitraum: Literal["monat", "jahr"]
    ist_netto: bool


class QuellenAnker(BaseModel):
    """Fundstelle eines Faktums: wörtliche Zeile von der Rechnung."""

    # strict=True wie Betrag/PreisCtKwh: keine stille Koersion (auch nicht für
    # die Audit-Metadaten seite, damit '2' nicht lautlos zu int 2 wird).
    model_config = ConfigDict(extra="forbid", strict=True)

    feld: str = Field(min_length=1)
    zitat: str = Field(min_length=3)
    seite: int | None = None


class InvoiceFacts(BaseModel):
    """Die vom LLM transkribierten Rechnungs-Fakten (D2.2-Schema, strict)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    energieart: Literal["strom", "gas", "kombi"]
    lieferant: str = Field(min_length=2)
    tarif_name: str | None = None
    # Datumsfelder bewusst lax (ISO-String ODER date) — Tool-Args kommen als JSON.
    # Aber KEIN Int/Float-Unixzeitstempel (siehe _datum_kein_timestamp).
    zeitraum_von: date = Field(strict=False)
    zeitraum_bis: date = Field(strict=False)
    verbrauch_kwh: float = Field(gt=0)
    # [0-9] statt \d: \d würde Unicode-Ziffern (arabisch-indisch, Fullwidth)
    # akzeptieren, die gegen ASCII-Referenzdaten (PLZ→Netzbetreiber) nie matchen.
    plz: str = Field(pattern=r"^[0-9]{4}$")
    zaehlpunkt: str | None = None
    summe_energieentgelte: Betrag | None = None
    summe_netzentgelte: Betrag | None = None
    summe_steuern_abgaben: Betrag | None = None
    rechnungsbetrag_brutto_eur: float | None = None
    grundgebuehr: Grundgebuehr | None = None
    arbeitspreis: PreisCtKwh | None = None
    jahresverbrauch_prognose_kwh: float | None = None
    anlagen_adresse: str | None = None
    quellen_anker: list[QuellenAnker]

    @field_validator("plz")
    @classmethod
    def _plz_nur_ascii(cls, v: str) -> str:
        # Regressions-Netz gegen ein versehentliches Zurückdrehen des Patterns
        # auf \d: nur ASCII-Ziffern sind eine gültige PLZ.
        if not v.isascii():
            raise ValueError("PLZ darf nur ASCII-Ziffern (0-9) enthalten")
        return v

    @field_validator("zeitraum_von", "zeitraum_bis", mode="before")
    @classmethod
    def _datum_normalisieren(cls, v: Any) -> Any:
        # Nur ISO-String, DE-Datum (TT.MM.JJJJ) oder date zulassen — ein reiner
        # Int/Float würde sonst still als Unixzeitstempel zu einem Datum koerziert
        # (bricht die "kein Feld koerziert lautlos"-Philosophie des Moduls).
        if isinstance(v, (bool, int, float)):
            raise ValueError(
                "Datum muss ein ISO-String (YYYY-MM-DD), ein DE-Datum (TT.MM.JJJJ) "
                "oder ein date sein, kein Zahlen-Zeitstempel — lies das "
                "Rechnungsdatum wörtlich von der Rechnung ab",
            )
        # DE-Schreibweise (TT.MM.JJJJ, wie auf AT-Rechnungen) → ISO, damit ein
        # (schwaches) LLM das Datum wörtlich abtippen kann, ohne umzurechnen. Die
        # eigentliche Kalender-Plausibilität (z.B. 31.02.) prüft danach pydantic.
        if isinstance(v, str):
            m = _DE_DATUM_RE.fullmatch(v.strip())
            if m:
                tag, monat, jahr = m.groups()
                return f"{jahr}-{monat}-{tag}"
        return v


def _fehler(feld: str, regel: str, wert: Any, rueckfrage: str) -> dict[str, Any]:
    return {"feld": feld, "regel": regel, "wert": wert, "rueckfrage": rueckfrage}


def _schema_fehler(exc: ValidationError) -> list[dict[str, Any]]:
    """Pydantic-Fehler → strukturierte D2.2-Fehler (Werte nur im Result, nie im Log)."""
    out: list[dict[str, Any]] = []
    for err in exc.errors(include_url=False):
        feld = ".".join(str(p) for p in err.get("loc", ())) or "input"
        wert = err.get("input")
        # Nur skalare Werte zurückspiegeln — keine ganzen Objekte duplizieren.
        if not isinstance(wert, (str, int, float, bool)) and wert is not None:
            wert = None
        out.append(_fehler(
            feld,
            f"schema_{err.get('type', 'invalid')}",
            wert,
            f"Feld '{feld}' ist ungültig ({err.get('msg', 'Schema-Verstoß')}). "
            "Lies den Wert erneut wörtlich von der Rechnung ab — rechne nichts um; "
            "frag den User, falls die Rechnung mehrdeutig ist.",
        ))
    return out


def _brutto(wert: float, ist_netto: bool) -> float:
    return wert * _UST if ist_netto else wert


# Belegpflichtige Anker-Felder für die Betrags-Seite des Quellen-Anker-Gates.
_BETRAG_ANKER_FELDER = (
    "summe_energieentgelte", "summe_netzentgelte", "summe_steuern_abgaben",
    "rechnungsbetrag_brutto_eur", "grundgebuehr", "arbeitspreis",
)

# Leerzeichen, die in Rechnungstexten als Tausendertrenner auftreten. PDF-Copy
# und deutsche Typografie liefern nicht das ASCII-Leerzeichen, sondern schmale
# geschuetzte Varianten - die galten vorher gar nicht als Trenner (L16).
_TRENN_LEERZEICHEN = "\u00a0\u202f\u2009\u2007\u2008\u2005\u2006"

# Ein Zahl-Token ist eine Ziffernfolge OHNE Leerzeichen. Bis 30.07.2026 stand das
# Leerzeichen in der Zeichenklasse - dadurch verschmolz eine Rechnungs-Tabellen-
# zeile ("01.01.2025 31.12.2025 3.500,00") zu EINEM Token, das keinen Wert mehr
# traf. Wer die Zeile woertlich zitierte (genau das verlangt die Ablehnung), bekam
# deshalb `anker_verbrauch_fehlt` - die haeufigste Ablehnung im Live-Betrieb.
_ZAHL_TOKEN_RE = re.compile(r"[0-9][0-9.,]*[0-9]|[0-9]")

# Der Tausendertrenner-Fall, den das Leerzeichen in der Klasse abdecken sollte:
# ein 1-3-stelliger Kopf plus mindestens eine per Leerzeichen abgesetzte
# Dreiergruppe ("3 500", "2 562,30"). Die Lookarounds verhindern, dass die Gruppe
# mitten in einer laengeren Ziffernfolge ansetzt ("41230 3500" bleibt zwei Zahlen).
_ZAHL_GRUPPE_RE = re.compile(r"(?<![0-9])[0-9]{1,3}(?: [0-9]{3})+(?:[.,][0-9]+)?(?![0-9])")


def _normalisiere_trenn_leerzeichen(text: str) -> str:
    """Typografische Leerzeichen auf das ASCII-Leerzeichen heben (neuer String)."""
    for zeichen in _TRENN_LEERZEICHEN:
        text = text.replace(zeichen, " ")
    return text


def _ist_tausendergruppierung(t: str, trenner: str) -> bool:
    """True, wenn ``trenner`` in ``t`` echte Dreiergruppen abtrennt (``3.500``,
    ``1.200.000``) — und nicht bloß irgendwo steht.

    Ohne diese Prüfung galt die Tausender-Deutung für JEDES Vorkommen: ``350,0``
    wurde damit auch als ``3500`` gelesen und belegte im Anker-Gate einen Wert,
    der zehnmal so groß ist wie der zitierte. Für ein Gate, das die Zahlenkette
    einer Rechnung beweisen soll, ist das der teuerste denkbare Fehler.
    """
    return re.fullmatch(rf"[0-9]{{1,3}}(?:{re.escape(trenner)}[0-9]{{3}})+", t) is not None


def _zahl_kandidaten(token: str) -> set[float]:
    """Plausible numerische Deutungen eines Zahl-Tokens.

    ',' und '.' können Tausender- ODER Dezimaltrenner sein; ohne Locale-Annahme
    werden beide Deutungen erzeugt, sodass der Aufrufer prüfen kann, ob EINE den
    Zielwert trifft. Bewusst rein syntaktisch — kein Semantik-Anspruch. Die
    Tausender-Deutung setzt aber echte Dreiergruppen voraus (s.
    ``_ist_tausendergruppierung``).
    """
    t = _normalisiere_trenn_leerzeichen(token).replace(" ", "")
    if not any(c.isdigit() for c in t):
        return set()
    kandidaten: set[float] = set()

    def _try(s: str) -> None:
        try:
            kandidaten.add(float(s))
        except ValueError:
            pass

    hat_punkt, hat_komma = "." in t, "," in t
    if hat_punkt and hat_komma:
        if t.rfind(".") > t.rfind(","):
            _try(t.replace(",", ""))                    # '.' Dezimal, ',' Tausender
        else:
            _try(t.replace(".", "").replace(",", "."))  # ',' Dezimal, '.' Tausender
    elif hat_komma:
        _try(t.replace(",", "."))                       # ',' als Dezimaltrenner
        if _ist_tausendergruppierung(t, ","):
            _try(t.replace(",", ""))                    # ',' als Tausendertrenner
    elif hat_punkt:
        _try(t)                                         # '.' als Dezimaltrenner
        if _ist_tausendergruppierung(t, "."):
            _try(t.replace(".", ""))                    # '.' als Tausendertrenner
    else:
        _try(t)
    return kandidaten


def _wert_im_zitat(wert: float, zitat: str) -> bool:
    """True, wenn der transkribierte Zahlenwert wörtlich im Zitat vorkommt.

    Deterministischer Zahlen-Match mit Separator-Normalisierung (',' / '.' /
    Leerzeichen inkl. der typografischen Varianten). KEIN semantischer Abgleich —
    nur die Ziffernfolge muss (in einer der Trenner-Deutungen) den Wert ergeben.

    Zwei Token-Wege, weil das Leerzeichen beides sein kann: **Trenner zwischen**
    zwei Zahlen (Tabellenzeile) und Trenner **innerhalb** einer Zahl
    (Tausendergruppe). Statt sich für eine Deutung zu entscheiden, werden beide
    erzeugt — dieselbe Logik, mit der ``_zahl_kandidaten`` '.' und ',' behandelt.
    """
    ziel = round(float(wert), 2)
    normalisiert = _normalisiere_trenn_leerzeichen(zitat)
    tokens = [
        *_ZAHL_TOKEN_RE.findall(normalisiert),    # Zahlen ohne Leerzeichen
        *_ZAHL_GRUPPE_RE.findall(normalisiert),   # Tausendergruppen mit Leerzeichen
    ]
    for token in tokens:
        for kandidat in _zahl_kandidaten(token):
            if abs(round(kandidat, 2) - ziel) <= 0.01:
                return True
    return False


def _numerische_feldwerte(facts: InvoiceFacts) -> dict[str, float]:
    """Feldname → transkribierter Zahlenwert der belegpflichtigen Felder."""
    werte: dict[str, float] = {"verbrauch_kwh": facts.verbrauch_kwh}
    if facts.rechnungsbetrag_brutto_eur is not None:
        werte["rechnungsbetrag_brutto_eur"] = facts.rechnungsbetrag_brutto_eur
    if facts.summe_energieentgelte is not None:
        werte["summe_energieentgelte"] = facts.summe_energieentgelte.wert_eur
    if facts.summe_netzentgelte is not None:
        werte["summe_netzentgelte"] = facts.summe_netzentgelte.wert_eur
    if facts.summe_steuern_abgaben is not None:
        werte["summe_steuern_abgaben"] = facts.summe_steuern_abgaben.wert_eur
    if facts.grundgebuehr is not None:
        werte["grundgebuehr"] = facts.grundgebuehr.wert_eur
    if facts.arbeitspreis is not None:
        werte["arbeitspreis"] = facts.arbeitspreis.wert_ct_kwh
    return werte


def _belegte_anker_felder(facts: InvoiceFacts) -> set[str]:
    """Felder mit einem Anker, der den EXAKTEN Feldnamen trägt UND dessen Wert
    im Zitat belegt.

    Schließt das Substring-/Feldnamen-Schlupfloch: ein Anker ``verbrauchszeitraum``
    (statt ``verbrauch_kwh``) oder ein Anker ohne die transkribierte Zahl im
    Zitat zählt nicht mehr als Beleg (Anti-Halluzinations-Gate, Fund 3).
    """
    werte = _numerische_feldwerte(facts)
    belegt: set[str] = set()
    for anker in facts.quellen_anker:
        wert = werte.get(anker.feld)
        if wert is not None and _wert_im_zitat(wert, anker.zitat):
            belegt.add(anker.feld)
    return belegt


def _wert_deutsch(wert: float) -> str:
    """Zahl in der Schreibweise, in der sie auf einer österreichischen Rechnung
    steht (``2.562,30``) — das Beispiel in der Ablehnung dient dem User-LLM als
    Vorlage, und eine Python-``repr``-Zahl (``2562.3``) steht dort nie."""
    mit_gruppen = f"{wert:,.2f}"
    return mit_gruppen.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _zitat_gekuerzt(zitat: str, grenze: int = 80) -> str:
    """Zitat für die Rückfrage kürzen — es geht ins Tool-Result zurück an den
    Absender, nie ins Log (D2.2-Logging-Policy), soll die Meldung aber nicht
    fluten, wenn jemand eine halbe Rechnungsseite eingereicht hat."""
    einzeilig = " ".join(zitat.split())
    return einzeilig if len(einzeilig) <= grenze else einzeilig[: grenze - 1] + "…"


def _anker_ursache(facts: InvoiceFacts, kandidaten: tuple[str, ...]) -> str:
    """Benennt, WORAN der fehlende Beleg liegt — statt nur, DASS er fehlt.

    Zwei Ursachen, die bis 30.07.2026 dieselbe Meldung bekamen: der Anker nennt
    gar nicht das erwartete Feld, oder er nennt es, trägt den transkribierten
    Wert aber nicht im Zitat. Das User-LLM konnte daraus nicht ableiten, was zu
    ändern ist, und probierte blind weiter (L16: fünf Anläufe in 32 Sekunden).
    """
    werte = _numerische_feldwerte(facts)
    # Nur Anker auf ein Feld, das auch einen Wert trägt — ein Anker auf ein
    # unbefülltes Feld kann nichts belegen und hat keinen Wert zum Gegenlesen.
    treffer = [
        a for a in facts.quellen_anker
        if a.feld in kandidaten and werte.get(a.feld) is not None
    ]
    if treffer:
        anker = treffer[0]
        wert = werte[anker.feld]
        return (
            f"Dein Anker für '{anker.feld}' zitiert \"{_zitat_gekuerzt(anker.zitat)}\" — "
            f"darin kommt der von dir übermittelte Wert {_wert_deutsch(wert)} nicht vor. "
            "Zitiere die Rechnungszeile, in der genau diese Zahl steht."
        )
    erwartet = " oder ".join(f"'{k}'" for k in kandidaten)
    genannt = sorted({a.feld for a in facts.quellen_anker})
    if not genannt:
        return f"Du hast gar keinen Quellen-Anker geschickt; erwartet wird einer für {erwartet}."
    return (
        f"Deine Anker nennen {', '.join(repr(f) for f in genannt)} — erwartet wird "
        f"{erwartet}. Das Feld im Anker muss exakt so heißen wie im Payload."
    )


def _pruefe_plausibilitaet(facts: InvoiceFacts) -> list[dict[str, Any]]:
    """Regel 2: Plausibilitätsgrenzen (Arbeitspreis, Grundgebühr, Verbrauch, Kosten)."""
    fehler: list[dict[str, Any]] = []

    lo, hi = PLAUSIBILITAET["verbrauch_kwh"]
    if not lo <= facts.verbrauch_kwh <= hi:
        fehler.append(_fehler(
            "verbrauch_kwh", f"plausibilitaet_{lo:g}_{hi:g}_kwh", facts.verbrauch_kwh,
            f"{facts.verbrauch_kwh:g} kWh ist unplausibel (erwartet {lo:g}–{hi:g}). "
            "Prüfe, ob Periodenverbrauch und Jahresverbrauch verwechselt wurden.",
        ))

    if facts.arbeitspreis is not None:
        ap_brutto = _brutto(facts.arbeitspreis.wert_ct_kwh, facts.arbeitspreis.ist_netto)
        lo, hi = PLAUSIBILITAET["arbeitspreis_ct_kwh"]
        if not lo <= ap_brutto <= hi:
            fehler.append(_fehler(
                "arbeitspreis", f"plausibilitaet_{lo:g}_{hi:g}_ct",
                facts.arbeitspreis.wert_ct_kwh,
                f"{facts.arbeitspreis.wert_ct_kwh:g} ct/kWh ist unplausibel. Lies den "
                "Arbeitspreis erneut ab — steht er in ct/kWh oder EUR/kWh? Frag den "
                "User, falls die Rechnung mehrdeutig ist.",
            ))

    if facts.grundgebuehr is not None:
        gg = facts.grundgebuehr
        pro_monat = gg.wert_eur / 12.0 if gg.zeitraum == "jahr" else gg.wert_eur
        pro_monat_brutto = _brutto(pro_monat, gg.ist_netto)
        lo, hi = PLAUSIBILITAET["grundgebuehr_eur_monat"]
        if not lo <= pro_monat_brutto <= hi:
            fehler.append(_fehler(
                "grundgebuehr", f"plausibilitaet_max_{hi:g}_eur_monat", gg.wert_eur,
                f"{gg.wert_eur:g} EUR ({gg.zeitraum}) entspricht {pro_monat_brutto:.2f} "
                "EUR/Monat brutto — unplausibel hoch. Prüfe Zeitraum (monat/jahr) und "
                "ob eine andere Preiszeile erwischt wurde.",
            ))

    lo, hi = PLAUSIBILITAET["kosten_eur"]
    kosten_kandidaten: list[tuple[str, float]] = []
    if facts.rechnungsbetrag_brutto_eur is not None:
        kosten_kandidaten.append(("rechnungsbetrag_brutto_eur", facts.rechnungsbetrag_brutto_eur))
    for name, betrag in (
        ("summe_energieentgelte", facts.summe_energieentgelte),
        ("summe_netzentgelte", facts.summe_netzentgelte),
        ("summe_steuern_abgaben", facts.summe_steuern_abgaben),
    ):
        if betrag is not None:
            kosten_kandidaten.append((name, betrag.wert_eur))
    for name, wert in kosten_kandidaten:
        if not lo <= wert <= hi:
            fehler.append(_fehler(
                name, f"plausibilitaet_{lo:g}_{hi:g}_eur", wert,
                f"{wert:g} EUR liegt außerhalb des Plausibilitätsfensters "
                f"({lo:g}–{hi:g} EUR). Lies den Betrag erneut ab.",
            ))
    return fehler


def _pruefe_cross_field(facts: InvoiceFacts) -> list[dict[str, Any]]:
    """Regel 3: Cross-Field-Checks (Rechnungsbetrag-Anker, Netto/Brutto, Prognose)."""
    fehler: list[dict[str, Any]] = []

    # (a) Deterministischer Rechnungsbetrag-Detektor (Port von
    # ``_needs_brutto_verification``): Effektivpreis-Anker 5–100 ct/kWh gegen
    # den Periodenverbrauch + absoluter Brutto-Floor 30 EUR.
    rb = facts.rechnungsbetrag_brutto_eur
    if rb is not None:
        if rb <= 0 or rb < _BRUTTO_FLOOR_EUR:
            fehler.append(_fehler(
                "rechnungsbetrag_brutto_eur", "brutto_floor_30_eur", rb,
                f"{rb:g} EUR ist als Brutto-Rechnungsbetrag unplausibel niedrig — "
                "vermutlich eine einzelne Preiszeile oder ein Teilbetrag. Lies den "
                "Endbetrag inkl. USt ab ('Rechnungsbetrag', 'Zu zahlen', 'Endbetrag').",
            ))
        else:
            eff_min = facts.verbrauch_kwh * _EFFEKTIV_MIN_EUR_KWH
            eff_max = facts.verbrauch_kwh * _EFFEKTIV_MAX_EUR_KWH
            if rb < eff_min or rb > eff_max:
                fehler.append(_fehler(
                    "rechnungsbetrag_brutto_eur", "effektivpreis_anker_5_100_ct", rb,
                    f"{rb:.2f} EUR passt nicht zu {facts.verbrauch_kwh:g} kWh "
                    f"(erwartet {eff_min:.0f}–{eff_max:.0f} EUR). Prüfe, ob ein "
                    "Akonto-/Teilbetrag statt des Rechnungsbetrags erwischt wurde.",
                ))

    # (b) Netto/Brutto-Konsistenz (NEU per D2.2): Summe der Netto-Blöcke × 1,2
    # muss ≈ Rechnungsbetrag brutto sein (±15 %). Nur prüfbar, wenn alle drei
    # Blöcke UND der Rechnungsbetrag vorliegen.
    bloecke = [facts.summe_energieentgelte, facts.summe_netzentgelte, facts.summe_steuern_abgaben]
    if rb is not None and rb > 0 and all(b is not None for b in bloecke):
        netto_summe = sum(
            (b.wert_eur if b.ist_netto else b.wert_eur / _UST) for b in bloecke  # type: ignore[union-attr]
        )
        erwartet_brutto = netto_summe * _UST
        if erwartet_brutto > 0:
            abweichung = abs(rb - erwartet_brutto) / erwartet_brutto
            if abweichung > _KONSISTENZ_TOLERANZ:
                fehler.append(_fehler(
                    "rechnungsbetrag_brutto_eur", "netto_brutto_konsistenz", rb,
                    f"Die drei Netto-Summen ergeben × 1,2 ≈ {erwartet_brutto:.2f} EUR, "
                    f"der Rechnungsbetrag ist {rb:.2f} EUR (>{_KONSISTENZ_TOLERANZ:.0%} "
                    "Abweichung). Prüfe die ist_netto-Flags und ob alle Summen aus "
                    "derselben Energieart-Sektion stammen.",
                ))

    # (c) Prognose-Fenster ±30 % gegen die Tages-Hochrechnung des Periodenverbrauchs.
    if facts.jahresverbrauch_prognose_kwh is not None:
        tage = (facts.zeitraum_bis - facts.zeitraum_von).days
        if tage > 0:
            hochrechnung = facts.verbrauch_kwh * 365.0 / tage
            lo = (1 - _PROGNOSE_FENSTER) * hochrechnung
            hi = (1 + _PROGNOSE_FENSTER) * hochrechnung
            if not lo <= facts.jahresverbrauch_prognose_kwh <= hi:
                fehler.append(_fehler(
                    "jahresverbrauch_prognose_kwh", "prognose_fenster_30_pct",
                    facts.jahresverbrauch_prognose_kwh,
                    f"Die EVU-Prognose {facts.jahresverbrauch_prognose_kwh:g} kWh weicht "
                    f">30 % von der Hochrechnung ({hochrechnung:.0f} kWh aus {tage} Tagen) "
                    "ab. Prüfe, ob wirklich der 'voraussichtliche Jahresverbrauch' "
                    "abgelesen wurde — sonst Feld weglassen.",
                ))
    return fehler


def _pruefe_gates(facts: InvoiceFacts) -> list[dict[str, Any]]:
    """Regel 1b/4: Zeitraum, Zählpunkt-Kanon, Pflichtfeld-Gate, Quellen-Anker."""
    fehler: list[dict[str, Any]] = []

    if facts.zeitraum_bis <= facts.zeitraum_von:
        fehler.append(_fehler(
            "zeitraum_bis", "zeitraum_bis_nach_von", facts.zeitraum_bis.isoformat(),
            "zeitraum_bis muss nach zeitraum_von liegen. Lies den "
            "Abrechnungszeitraum erneut ab.",
        ))

    # Zählpunkt: Kanonisierung + strikte Formprüfung (AT + 33 Zeichen bzw.
    # Pauschal-Sentinel). Fängt genau die WP-C-Fehlerklasse "eine Ziffer
    # verschluckt" (32 statt 33 Zeichen).
    if facts.zaehlpunkt is not None:
        zp = _zp_validate(facts.zaehlpunkt)
        if not zp.valid_strict:
            fehler.append(_fehler(
                "zaehlpunkt", "zaehlpunkt_at_33_stellen", facts.zaehlpunkt,
                f"'{facts.zaehlpunkt}' ist kein gültiger österreichischer Zählpunkt "
                f"(kanonisiert: '{zp.canonical}', {len(zp.canonical)} Zeichen statt 33). "
                "Lies die Zählpunktnummer Ziffer für Ziffer erneut ab (AT + 31 Ziffern).",
            ))

    # Pflichtfeld-Gate (Port des OCR-Service-Gates): arbeitspreis ODER
    # energieentgelte-Summe muss vorliegen (plz + verbrauch erzwingt das Schema).
    if facts.arbeitspreis is None and facts.summe_energieentgelte is None:
        fehler.append(_fehler(
            "arbeitspreis", "pflichtfeld_arbeitspreis_oder_energiesumme", None,
            "Weder Arbeitspreis (ct/kWh) noch Summe der Energieentgelte angegeben — "
            "ohne eines davon ist keine deterministische Kostenrechnung möglich. "
            "Lies eine der beiden Angaben von der Rechnung ab.",
        ))

    # Quellen-Anker (gehärtet, Fund 3): je ein Anker mit EXAKTEM Feldnamen eines
    # befüllten Felds, dessen transkribierter WERT wörtlich im Zitat vorkommt —
    # einer für den Verbrauch und einer für mindestens einen Betrag.
    # Deterministischer Zahlen-Match (Separator-Normalisierung), kein
    # semantischer Abgleich: das Gate schließt nur das Substring-Schlupfloch,
    # es beweist keine inhaltliche Richtigkeit der Zuordnung.
    belegt = _belegte_anker_felder(facts)
    if "verbrauch_kwh" not in belegt:
        fehler.append(_fehler(
            "quellen_anker", "anker_verbrauch_fehlt", None,
            "Es fehlt ein belegter Quellen-Anker für den Verbrauch. "
            + _anker_ursache(facts, ("verbrauch_kwh",))
            + " So sieht ein gültiger Anker aus: "
            + f'{{"feld": "verbrauch_kwh", "zitat": "Jahresverbrauch '
            + f'{_wert_deutsch(facts.verbrauch_kwh)} kWh"}}',
        ))
    werte = _numerische_feldwerte(facts)
    betrags_felder = tuple(f for f in _BETRAG_ANKER_FELDER if f in werte)
    if not belegt & set(_BETRAG_ANKER_FELDER):
        beispiel_feld = betrags_felder[0] if betrags_felder else "rechnungsbetrag_brutto_eur"
        beispiel_wert = werte.get(beispiel_feld)
        beispiel = (
            f'{{"feld": "{beispiel_feld}", "zitat": '
            f'"Rechnungsbetrag {_wert_deutsch(beispiel_wert)}"}}'
            if beispiel_wert is not None
            else '{"feld": "rechnungsbetrag_brutto_eur", "zitat": "Rechnungsbetrag 812,44"}'
        )
        fehler.append(_fehler(
            "quellen_anker", "anker_betrag_fehlt", None,
            "Es fehlt ein belegter Quellen-Anker für mindestens einen Betrag. "
            + _anker_ursache(facts, betrags_felder or _BETRAG_ANKER_FELDER)
            + f" So sieht ein gültiger Anker aus: {beispiel}",
        ))
    return fehler


def pruefe_invoice_facts(
    payload: dict[str, Any],
) -> tuple[InvoiceFacts | None, list[dict[str, Any]]]:
    """Validiert ein Fakten-Payload strikt nach D2.2.

    Returns ``(facts, [])`` bei Erfolg, sonst ``(None, fehler)`` mit
    strukturierten Fehlern ``{feld, regel, wert, rueckfrage}``. Alle Regeln
    deterministisch; KEINE stille Koersion.
    """
    try:
        facts = InvoiceFacts.model_validate(payload)
    except ValidationError as exc:
        return None, _schema_fehler(exc)

    fehler = [
        *_pruefe_gates(facts),
        *_pruefe_plausibilitaet(facts),
        *_pruefe_cross_field(facts),
    ]
    if fehler:
        return None, fehler
    return facts, []
