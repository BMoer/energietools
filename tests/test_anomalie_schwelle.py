# energietools — Rechenwerk für Strom- und Gaskosten
# SPDX-License-Identifier: AGPL-3.0-only

"""Tests für die Anomalie-Schwelle in tools/load_profile.py.

Befund (Gridbert-Demo-Account, nachgemessen 31.07.2026 an 937 Tagesprofilen):
der produktive Pfad markierte **542 Tage = 57,8 %** als Anomalie. Der Median
der Tages-Kennzahl lag bei 2,68, die Schwelle bei 2,5 — sie lag also *unter*
dem Median. Ein Label, das mehr als jeden zweiten Tag trifft, trägt keine
Information, und die echten Ausreißer (im Demo-Fall drei Urlaubsfenster) gehen
darin unter.

Der Konstruktionsfehler steckt in beiden Erkennungspfaden gleich: verglichen
wurde ein **Extremwert über 96 Slots** gegen eine **punktweise** Streuung. Bei
96 Ziehungen reißt das Maximum eine 2–2,5-Sigma-Grenze fast beliebig oft — die
Schwelle prüft damit nicht "ist dieser Tag ungewöhnlich", sondern "hat dieser
Tag irgendeinen ungewöhnlichen Moment", und das hat jeder Tag.

Die Korrektur vergleicht eine **Tages**-Kennzahl gegen die Verteilung genau
dieser Kennzahl über alle Tage, robust (Median + k·MAD). Entscheidend ist die
Eigenschaft, die eine feste Quantils-Schwelle nicht hat: bei gleichförmigen
Tagen kommt **null** heraus, nicht ein konstanter Prozentsatz.
"""

from __future__ import annotations

import numpy as np
import pytest

from energietools.tools.load_profile import (
    tages_ausreisser,
    tages_ausreisser_typisiert,
)


def _flacher_tag(hoehe: float = 1.0) -> np.ndarray:
    return np.full(96, hoehe)


def _tag_mit_spitze(hoehe: float = 1.0, spitze: float = 9.0, slot: int = 40) -> np.ndarray:
    tag = np.full(96, hoehe)
    tag[slot] = spitze
    return tag


class TestGleichfoermigeTageErgebenNullAnomalien:
    def test_identische_tage_haben_keine_ausreisser(self) -> None:
        tage = np.array([_flacher_tag() for _ in range(30)])
        assert tages_ausreisser(tage) == []

    def test_leichtes_rauschen_erzeugt_keine_ausreisser(self) -> None:
        """Der Alltagsfall: jeder Tag etwas anders, keiner ungewöhnlich."""
        rng = np.random.default_rng(42)
        tage = np.array([_flacher_tag() + rng.normal(0, 0.05, 96) for _ in range(60)])
        assert len(tages_ausreisser(tage)) == 0

    def test_feste_quantilsschwelle_wuerde_hier_falsch_liegen(self) -> None:
        """Ein 95%-Quantil meldete per Konstruktion 5 % — hier sind es 0 %."""
        rng = np.random.default_rng(7)
        tage = np.array([_flacher_tag() + rng.normal(0, 0.05, 96) for _ in range(100)])
        gefunden = tages_ausreisser(tage)
        assert len(gefunden) < 5


class TestEchteAusreisserWerdenGefunden:
    def test_ein_abweichender_tag_unter_vielen_gleichen(self) -> None:
        rng = np.random.default_rng(1)
        tage = [_flacher_tag() + rng.normal(0, 0.05, 96) for _ in range(40)]
        tage.append(_flacher_tag(hoehe=0.05))  # Urlaubstag: fast kein Verbrauch
        gefunden = tages_ausreisser(np.array(tage))
        assert 40 in gefunden

    def test_mehrere_urlaubstage_werden_alle_gefunden(self) -> None:
        rng = np.random.default_rng(2)
        tage = [_flacher_tag() + rng.normal(0, 0.05, 96) for _ in range(50)]
        for _ in range(5):
            tage.append(_flacher_tag(hoehe=0.05))
        gefunden = set(tages_ausreisser(np.array(tage)))
        assert {50, 51, 52, 53, 54} <= gefunden

    def test_ein_einzelner_ausreisser_slot_macht_noch_keinen_anomalen_tag(self) -> None:
        """Genau der alte Fehler: ein Moment ≠ ein ungewöhnlicher Tag.

        Alle Tage tragen eine Spitze an wechselnder Stelle — das ist normales
        Haushaltsverhalten (Herd, Waschmaschine), kein Ausreißer.
        """
        tage = np.array([_tag_mit_spitze(slot=i % 96) for i in range(60)])
        gefunden = tages_ausreisser(tage)
        assert len(gefunden) <= 3, f"{len(gefunden)} von 60 Tagen markiert"


class TestRobustheit:
    def test_wenige_tage_ergeben_keine_aussage(self) -> None:
        """Unter einer Mindestzahl ist keine Verteilung schätzbar."""
        tage = np.array([_flacher_tag(), _tag_mit_spitze()])
        assert tages_ausreisser(tage) == []

    def test_haelfte_identisch_bricht_die_streuung_nicht(self) -> None:
        """MAD = 0, wenn über die Hälfte der Tage exakt gleich ist.

        Ohne Guard wäre die Schwelle gleich dem Median und JEDER auch nur
        minimal abweichende Tag eine Anomalie — der alte Fehler in neuem Gewand.
        """
        tage = [_flacher_tag() for _ in range(30)]
        tage += [_flacher_tag(hoehe=1.001) for _ in range(10)]
        tage.append(_flacher_tag(hoehe=50.0))
        gefunden = tages_ausreisser(np.array(tage))
        assert 40 in gefunden
        assert len(gefunden) <= 11

    def test_ausreisser_verschieben_die_schwelle_nicht(self) -> None:
        """Robustheit: 5 Extremtage dürfen die Schwelle nicht so hochziehen,
        dass sie sich selbst verstecken (das täte ein Mittelwert+Sigma)."""
        rng = np.random.default_rng(3)
        tage = [_flacher_tag() + rng.normal(0, 0.05, 96) for _ in range(50)]
        for _ in range(5):
            tage.append(_flacher_tag(hoehe=100.0))
        gefunden = set(tages_ausreisser(np.array(tage)))
        assert {50, 51, 52, 53, 54} <= gefunden

    def test_gibt_sortierte_indizes_zurueck(self) -> None:
        rng = np.random.default_rng(4)
        tage = [_flacher_tag() + rng.normal(0, 0.05, 96) for _ in range(30)]
        tage.insert(5, _flacher_tag(hoehe=0.01))
        tage.insert(20, _flacher_tag(hoehe=0.01))
        gefunden = tages_ausreisser(np.array(tage))
        assert gefunden == sorted(gefunden)

    @pytest.mark.parametrize("k", [2.0, 3.0, 5.0])
    def test_hoeheres_k_meldet_nie_mehr(self, k: float) -> None:
        rng = np.random.default_rng(5)
        tage = [_flacher_tag() + rng.normal(0, 0.2, 96) for _ in range(80)]
        tage.append(_flacher_tag(hoehe=0.02))
        anzahl = len(tages_ausreisser(np.array(tage), k=k))
        assert anzahl <= len(tages_ausreisser(np.array(tage), k=k - 1.0))


class TestTypUnterscheidetNiveauUndForm:
    """Der Typ war bisher eine Heuristik über dieselbe Zahl, die schon die
    Schwelle bildete. Jetzt benennt er, welche der beiden Kennzahlen gerissen
    hat — die Unterscheidung, die ``AnomalyResult.typ`` immer behauptet hat."""

    def test_urlaubstag_ist_eine_niveau_anomalie(self) -> None:
        rng = np.random.default_rng(11)
        tage = [_flacher_tag() + rng.normal(0, 0.05, 96) for _ in range(40)]
        tage.append(_flacher_tag(hoehe=0.05))
        typen = tages_ausreisser_typisiert(np.array(tage))
        assert typen[40] in ("magnitude", "both")

    def test_verschobener_tagesablauf_ist_eine_form_anomalie(self) -> None:
        """Gleiche Menge Strom, anderer Zeitpunkt — Nachtschicht statt Tag."""
        tag = np.concatenate([np.full(48, 2.0), np.full(48, 0.2)])
        gedreht = np.concatenate([np.full(48, 0.2), np.full(48, 2.0)])
        rng = np.random.default_rng(12)
        tage = [tag + rng.normal(0, 0.02, 96) for _ in range(40)]
        tage.append(gedreht)
        typen = tages_ausreisser_typisiert(np.array(tage))
        assert typen.get(40) in ("shape", "both")

    def test_niveau_und_form_gleichzeitig_ergibt_both(self) -> None:
        tag = np.concatenate([np.full(48, 2.0), np.full(48, 0.2)])
        rng = np.random.default_rng(13)
        tage = [tag + rng.normal(0, 0.02, 96) for _ in range(40)]
        tage.append(np.concatenate([np.full(48, 0.01), np.full(48, 0.30)]))
        typen = tages_ausreisser_typisiert(np.array(tage))
        assert typen.get(40) == "both"

    def test_nur_gemeldete_tage_stehen_im_ergebnis(self) -> None:
        rng = np.random.default_rng(14)
        tage = np.array([_flacher_tag() + rng.normal(0, 0.05, 96) for _ in range(40)])
        assert tages_ausreisser_typisiert(tage) == {}

    def test_typen_sind_auf_das_vereinbarte_vokabular_beschraenkt(self) -> None:
        rng = np.random.default_rng(15)
        tage = [_flacher_tag() + rng.normal(0, 0.1, 96) for _ in range(50)]
        tage.append(_flacher_tag(hoehe=0.02))
        tage.append(np.concatenate([np.full(48, 0.05), np.full(48, 2.0)]))
        typen = tages_ausreisser_typisiert(np.array(tage))
        assert set(typen.values()) <= {"magnitude", "shape", "both"}

    def test_indizes_stimmen_mit_der_untypisierten_liste_ueberein(self) -> None:
        rng = np.random.default_rng(16)
        tage = [_flacher_tag() + rng.normal(0, 0.05, 96) for _ in range(30)]
        tage.append(_flacher_tag(hoehe=0.02))
        matrix = np.array(tage)
        assert sorted(tages_ausreisser_typisiert(matrix)) == tages_ausreisser(matrix)
