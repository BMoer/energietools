# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Energieversorger (Lieferanten) — Stammdaten + Abdeckung je Netzgebiet.

Beantwortet: *Welche Stromlieferanten sind an einer PLZ / in einem Netzgebiet
verfügbar?* Bundesweite Anbieter überall, Landesversorger/Stadtwerke nur in
ihrem Bundesland (``region`` aus ``data/providers/anbieter.json``).
"""

from energietools.capabilities.providers.abdeckung import (
    Versorger,
    VersorgerAbdeckung,
    lade_anbieter,
    versorger_abdeckung,
)

__all__ = ["Versorger", "VersorgerAbdeckung", "lade_anbieter", "versorger_abdeckung"]
