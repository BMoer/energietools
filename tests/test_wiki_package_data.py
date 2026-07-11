# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Package-Data-Regressionstest (D7 Prüfpunkt, WP-P 3).

Der eigentliche Beweis, dass ``wiki/`` und ``prozesse/`` mit jedem
``pip install energietools`` mitreisen, ist ein echter Wheel-Build in eine
frische venv (siehe Session-Report — dort manuell verifiziert, inkl.
``get_knowledge`` und dem Struktur-Linter aus dem installierten Wheel
heraus). Ein Wheel-Build in JEDEM Testlauf wäre langsam und bräuchte eine
zusätzliche Build-Abhängigkeit; dieser Test verhindert stattdessen
deterministisch stillen Drift: JEDE tatsächlich vorhandene Wiki-/Prozesse-
Datei muss von mindestens einem ``package-data``-Glob in ``pyproject.toml``
erfasst sein — legt jemand einen neuen Wiki-Unterordner an und vergisst die
package-data-Liste, schlägt genau das hier fehl.
"""

from __future__ import annotations

import fnmatch
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENERGIETOOLS_ROOT = REPO_ROOT / "energietools"


def _package_data_patterns() -> list[str]:
    with (REPO_ROOT / "pyproject.toml").open("rb") as f:
        data = tomllib.load(f)
    return data["tool"]["setuptools"]["package-data"]["energietools"]


def _matches_any(relpath: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(relpath, pat) for pat in patterns)


class TestWikiIstPackageData:
    def test_alle_wiki_dateien_von_package_data_erfasst(self):
        patterns = _package_data_patterns()
        fehlend = [
            path.relative_to(ENERGIETOOLS_ROOT).as_posix()
            for path in (ENERGIETOOLS_ROOT / "wiki").rglob("*")
            if path.is_file()
            and not _matches_any(path.relative_to(ENERGIETOOLS_ROOT).as_posix(), patterns)
        ]
        assert not fehlend, f"Nicht von package-data erfasst: {fehlend}"

    def test_wiki_liegt_innerhalb_des_packages(self):
        # D7-Prüfpunkt: wiki/ MUSS unter energietools/ liegen, sonst reist es
        # mit keiner package-data-Regel mit (setuptools kann nur Dateien
        # innerhalb des Package-Verzeichnisses ausliefern).
        assert (ENERGIETOOLS_ROOT / "wiki" / "llms.txt").is_file()
        assert not (REPO_ROOT / "wiki").exists(), "wiki/ darf nicht mehr am Repo-Root liegen"


class TestProzesseIstPackageData:
    def test_alle_prozesse_yaml_json_von_package_data_erfasst(self):
        patterns = _package_data_patterns()
        prozesse_root = ENERGIETOOLS_ROOT / "prozesse"
        fehlend = [
            path.relative_to(ENERGIETOOLS_ROOT).as_posix()
            for path in prozesse_root.rglob("*")
            if path.is_file()
            and path.suffix in (".yaml", ".json")
            and not _matches_any(path.relative_to(ENERGIETOOLS_ROOT).as_posix(), patterns)
        ]
        assert not fehlend, f"Nicht von package-data erfasst: {fehlend}"
