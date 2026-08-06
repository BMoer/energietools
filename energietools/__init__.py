# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

# Single Source of Truth ist die Version in pyproject.toml — hier nur gelesen,
# nicht gepflegt (sonst driftet sie, wie 0.1.0 vs. 0.7.2 vor v0.7.3).
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

try:
    __version__ = _version("energietools")
except PackageNotFoundError:  # nicht installiert (Repo-Checkout ohne pip install)
    __version__ = "0.0.0+unknown"

__description__ = "Open-Source Toolkit für den österreichischen Energiemarkt"
