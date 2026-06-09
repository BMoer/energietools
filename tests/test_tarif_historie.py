# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""S7: Tarif-Historie — Gültigkeitsfelder + Stichtags-Filter (additiv).

Der Katalog wird von einem reinen Aktuell-Snapshot zu einer Zeitreihe: jede
Tarif-Version trägt ``gueltig_ab``/``gueltig_bis``. ``load()`` liefert den aktuell
gültigen Schnitt, ``load(stand=...)`` / ``gueltig_am(stand)`` jeden historischen Stand.
"""

from __future__ import annotations

from energietools.capabilities.tariffs.catalog import TariffCatalog
from energietools.capabilities.tariffs.models import CatalogManifest, CatalogTariff


def _v(key: str, ep: float, ab: str = "", bis: str = "") -> CatalogTariff:
    return CatalogTariff(
        key=key, lieferant="X", tarif_name="Tarif A", energiepreis_ct_kwh=ep,
        gueltig_ab=ab, gueltig_bis=bis,
    )


def test_catalog_tariff_has_gueltigkeit_default_offen() -> None:
    t = CatalogTariff(key="x", lieferant="X", tarif_name="T")
    assert t.gueltig_ab == ""
    assert t.gueltig_bis == ""  # leer = aktuell gültig/offen


def test_manifest_has_stand_und_versionen() -> None:
    m = CatalogManifest(catalog_version="2", generated_at="2026-06-09")
    assert m.stand == ""
    assert m.versionen_gesamt == 0


def test_gueltig_am_liefert_aktuelle_version() -> None:
    """Zwei Versionen eines Tarifs: am heutigen Stand greift nur die offene."""
    alt = _v("a", 10.0, ab="2026-01-01", bis="2026-03-31")
    neu = _v("a", 12.0, ab="2026-04-01", bis="")
    cat = TariffCatalog([alt, neu])
    aktuell = cat.gueltig_am("2026-06-09").all()
    assert len(aktuell) == 1
    assert aktuell[0].energiepreis_ct_kwh == 12.0  # die offene Version


def test_gueltig_am_historischer_stand() -> None:
    """Ein Stichtag im alten Zeitfenster liefert die damals gültige Version."""
    alt = _v("a", 10.0, ab="2026-01-01", bis="2026-03-31")
    neu = _v("a", 12.0, ab="2026-04-01", bis="")
    cat = TariffCatalog([alt, neu])
    historisch = cat.gueltig_am("2026-02-15").all()
    assert len(historisch) == 1
    assert historisch[0].energiepreis_ct_kwh == 10.0  # die damals gültige


def test_gueltig_am_schliesst_zukunft_aus() -> None:
    """Eine noch nicht gültige (zukünftige) Version wird am Stichtag ausgeschlossen."""
    zukunft = _v("a", 12.0, ab="2026-07-01", bis="")
    cat = TariffCatalog([zukunft])
    assert cat.gueltig_am("2026-06-09").all() == []


def test_leere_gueltigkeit_immer_aktuell() -> None:
    """Backward-compat: ein alter Eintrag ohne Gültigkeitsfelder ist immer gültig."""
    t = _v("a", 10.0)  # ab="" / bis=""
    cat = TariffCatalog([t])
    assert len(cat.gueltig_am("2020-01-01").all()) == 1
    assert len(cat.gueltig_am("2030-01-01").all()) == 1


def test_load_bundled_snapshot_aktuell() -> None:
    """Smoke: load() auf dem gebündelten Snapshot liefert den aktuellen Schnitt (>0)."""
    cat = TariffCatalog.load()
    assert len(cat) > 0
    # Der gebündelte Snapshot ist (noch) reiner Aktuell-Stand → alle Versionen offen.
    assert all(t.gueltig_bis == "" for t in cat.all())
