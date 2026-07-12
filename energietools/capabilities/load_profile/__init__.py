# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Load-Profile-Capability — Lastprofil-Analyse (Grundlast, Spitzen, Anomalien).

Dedizierte Capability-Klasse (WP2-S 2/3, Durchstich 2) statt der früheren
generischen ``FunctionCapability``-Brücke — übersetzt den in-band-Fehlerpfad von
``tools.load_profile.analyze_load_profile`` in die einheitliche ok/error-Envelope-
Semantik und befüllt ``_meta`` (stand/quelle/snapshot_version).
"""

from __future__ import annotations

from energietools.capabilities.load_profile.capability import LoadProfileCapability

__all__ = ["LoadProfileCapability"]
