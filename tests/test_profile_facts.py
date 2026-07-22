# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für das Fakt-Index-Fundament (``capabilities/profile.py``,
Fakt-vor-Heuristik).

Struktur:
- Wire-Format-Parsing (Kurzform + Objektform, Forward-Compat-Keys).
- Fail-closed-Guards (unbekanntes Feld, Enum-/Zahl-/Bool-Verstöße, unbekannte
  quelle).
- Ontologie-Paritäts-Drift-Guard: PROFIL_FELDER MUSS exakt die 7 Felder
  decken, die ``prozesse/lastganganalyse.yaml`` in seinen ``fragen`` referenziert
  (SSOT-Sync-Punkt zwischen Prozess-YAML und Kern-Ontologie).
- InMemoryProfileFacts als Fake-Basis.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from energietools.capabilities.base import CapabilityError
from energietools.capabilities.profile import (
    PROFIL_FELDER,
    FaktWert,
    InMemoryProfileFacts,
    parse_profil_fakten,
    validiere_fakt_wert,
)
from energietools.prozesse.loader import load_prozess

# ---------------------------------------------------------------------------
# Wire-Format: Kurzform + Objektform
# ---------------------------------------------------------------------------


def test_parse_profil_fakten_kurzform_und_objektform() -> None:
    fakten = parse_profil_fakten(
        {
            "asset.heating.type": "gas",  # Kurzform -> quelle="profil"
            "asset.pv.kwp": {
                "wert": 5.5,
                "quelle": "rechnung",
                "stand": "2026-07-01T00:00:00+00:00",
                "anker": "PV-Anlage 5,5 kWp lt. Rechnung",
            },
        }
    )

    heizung = fakten.get_fakt("asset.heating.type")
    assert heizung is not None
    assert heizung.wert == "gas"
    assert heizung.quelle == "profil"
    assert heizung.stand is None
    assert heizung.anker is None

    pv = fakten.get_fakt("asset.pv.kwp")
    assert pv is not None
    assert pv.wert == 5.5
    assert pv.quelle == "rechnung"
    assert pv.stand == datetime(2026, 7, 1, tzinfo=timezone.utc)
    assert pv.anker == "PV-Anlage 5,5 kWp lt. Rechnung"


def test_parse_profil_fakten_leer_und_none_liefert_leere_quelle() -> None:
    assert parse_profil_fakten(None).get_all() == {}
    assert parse_profil_fakten({}).get_all() == {}


def test_parse_profil_fakten_ignoriert_unbekannte_keys_im_fakt_objekt() -> None:
    """Forward-Compat: das Gateway-Wire-Format darf mehr Keys mitschicken, als
    dieses Repo kennt — sie werden im Objekt selbst ignoriert (NICHT der
    Feld-Key, der bleibt fail-closed geprüft)."""
    fakten = parse_profil_fakten(
        {
            "asset.continuous_loads": {
                "wert": "Pool-Pumpe",
                "quelle": "profil",
                "zukuenftiges_feld": "irgendwas",
            }
        }
    )
    eintrag = fakten.get_fakt("asset.continuous_loads")
    assert eintrag is not None
    assert eintrag.wert == "Pool-Pumpe"


# ---------------------------------------------------------------------------
# Fail-closed: unbekanntes Feld / ungültiger Wert / unbekannte quelle
# ---------------------------------------------------------------------------


def test_parse_profil_fakten_unbekanntes_feld_wirft_capability_error() -> None:
    with pytest.raises(CapabilityError, match="unbekanntes Feld"):
        parse_profil_fakten({"asset.nicht_existent": "foo"})


def test_parse_profil_fakten_enum_verstoss_wirft() -> None:
    with pytest.raises(CapabilityError, match="nicht erlaubt"):
        parse_profil_fakten({"asset.heating.type": "kohle"})


def test_parse_profil_fakten_kwp_null_wirft() -> None:
    with pytest.raises(CapabilityError, match="positive Zahl"):
        parse_profil_fakten({"asset.pv.kwp": 0})


def test_parse_profil_fakten_q15_bool_pflicht() -> None:
    with pytest.raises(CapabilityError, match="Bool-Wert"):
        parse_profil_fakten({"meter.q15_optin": "true"})


def test_parse_profil_fakten_unbekannte_quelle_wirft() -> None:
    with pytest.raises(CapabilityError, match="unbekannte quelle"):
        parse_profil_fakten({"asset.heating.type": {"wert": "gas", "quelle": "heuristik"}})


def test_parse_profil_fakten_raw_kein_dict_wirft() -> None:
    with pytest.raises(CapabilityError):
        parse_profil_fakten("nicht_ein_dict")


def test_parse_profil_fakten_objektform_ohne_wert_wirft() -> None:
    with pytest.raises(CapabilityError, match="'wert'"):
        parse_profil_fakten({"asset.pv.kwp": {"quelle": "profil"}})


# ---------------------------------------------------------------------------
# E5: enum-Werte werden BEIM PARSEN kanonisiert (case-/whitespace-tolerant)
# ---------------------------------------------------------------------------


def test_parse_profil_fakten_kanonisiert_enum_kurzform() -> None:
    """'Gas'/' gas ' landen beide als 'gas' im gespeicherten FaktWert."""
    assert (
        parse_profil_fakten({"asset.heating.type": "Gas"}).get_fakt("asset.heating.type").wert
        == "gas"
    )
    assert (
        parse_profil_fakten({"asset.heating.type": " gas "}).get_fakt("asset.heating.type").wert
        == "gas"
    )


def test_parse_profil_fakten_kanonisiert_enum_objektform() -> None:
    fakten = parse_profil_fakten(
        {"asset.heating.type": {"wert": " Waermepumpe ", "quelle": "profil"}}
    )
    assert fakten.get_fakt("asset.heating.type").wert == "waermepumpe"


def test_parse_profil_fakten_kanonisierung_bleibt_fail_closed_bei_ungueltigem_wert() -> None:
    """Kanonisierung erspart der Ontologie nichts — 'Kohle' bleibt ungültig,
    auch kanonisiert."""
    with pytest.raises(CapabilityError, match="nicht erlaubt"):
        parse_profil_fakten({"asset.heating.type": " Kohle "})


def test_parse_profil_fakten_nicht_string_enum_wert_bleibt_fail_closed() -> None:
    """Nicht-Strings für enum-Felder werden NICHT kanonisiert (kein .lower()
    auf Nicht-Text) und bleiben fail-closed abgelehnt."""
    with pytest.raises(CapabilityError, match="nicht erlaubt"):
        parse_profil_fakten({"asset.heating.type": 123})


# ---------------------------------------------------------------------------
# validiere_fakt_wert — direkte Unit-Tests der Kern-Ontologie-Prüfung
# ---------------------------------------------------------------------------


def test_validiere_fakt_wert_unbekanntes_feld_liefert_meldung() -> None:
    assert validiere_fakt_wert("nicht.existent", "x") is not None


def test_validiere_fakt_wert_gueltige_werte_liefern_none() -> None:
    assert validiere_fakt_wert("asset.heating.type", "waermepumpe") is None
    assert validiere_fakt_wert("asset.pv.kwp", 4.2) is None
    assert validiere_fakt_wert("asset.battery.kwh", 0) is None  # nichtnegativ: 0 ist gültig
    assert validiere_fakt_wert("asset.continuous_loads", "Pool") is None
    assert validiere_fakt_wert("behavior.appliance_timing", "flexibel") is None
    assert validiere_fakt_wert("contract.heiztarif_typ", "heizstromtarif") is None
    assert validiere_fakt_wert("meter.q15_optin", True) is None


def test_validiere_fakt_wert_leerer_text_ist_ungueltig() -> None:
    assert validiere_fakt_wert("asset.continuous_loads", "   ") is not None


def test_validiere_fakt_wert_negative_kwh_ist_ungueltig() -> None:
    assert validiere_fakt_wert("asset.battery.kwh", -1) is not None


def test_validiere_fakt_wert_bool_wird_nicht_als_zahl_akzeptiert() -> None:
    """bool ist ein int-Subtyp in Python — darf hier NICHT als Zahl durchgehen."""
    assert validiere_fakt_wert("asset.pv.kwp", True) is not None


# ---------------------------------------------------------------------------
# InMemoryProfileFacts — Fake-Basis
# ---------------------------------------------------------------------------


def test_in_memory_profile_facts_get_fakt_und_get_all() -> None:
    fakt = FaktWert(feld="asset.heating.type", wert="gas", quelle="profil")
    quelle = InMemoryProfileFacts([fakt])

    assert quelle.get_fakt("asset.heating.type") == fakt
    assert quelle.get_fakt("asset.pv.kwp") is None
    assert quelle.get_all() == {"asset.heating.type": fakt}


def test_in_memory_profile_facts_leer_per_default() -> None:
    assert InMemoryProfileFacts().get_all() == {}


# ---------------------------------------------------------------------------
# Ontologie-Paritäts-Drift-Guard (SSOT-Sync-Punkt Prozess-YAML <-> PROFIL_FELDER)
# ---------------------------------------------------------------------------


def test_profil_felder_decken_alle_sieben_yaml_fragen_felder() -> None:
    prozess = load_prozess("lastganganalyse.yaml")
    yaml_felder = {f.feld for f in prozess.fragen if f.feld}

    assert yaml_felder == set(PROFIL_FELDER)
    assert len(PROFIL_FELDER) == 7
