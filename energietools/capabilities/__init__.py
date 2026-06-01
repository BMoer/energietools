# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Capability-Rückgrat des Toolkits.

Eine Capability ist eine eigenständige, auditierbare Fähigkeit mit einheitlicher
Oberfläche (``run(**kwargs) -> CapabilityResult``). Siehe ``base`` für das
Rückgrat und ``registry`` für die ausgelieferten Fähigkeiten.
"""

from __future__ import annotations

from energietools.capabilities.base import (
    Capability,
    CapabilityError,
    CapabilityRegistry,
    CapabilityResult,
)
from energietools.capabilities.registry import default_registry

__all__ = [
    "Capability",
    "CapabilityError",
    "CapabilityRegistry",
    "CapabilityResult",
    "default_registry",
]
