# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Der v1-MCP-Tool-Katalog außerhalb von energietools (ARCHITECTURE-2.0.md §3.3 WP-G1).

Ein Prozess darf Tools referenzieren, die nicht in diesem Repo leben — die
Engram-Vault-Tools (Tool-Familie 1) und die Gridbert-Domänen-Tools (Tool-
Familie 3). Diese Liste ist die dokumentierte Lint-Grundlage für
``tool_mapping``-Einträge mit ``quelle: extern``; sie ist bewusst NICHT gegen
``default_registry()`` prüfbar, weil diese Tools in anderen Repos (engram,
gridbert-gateway) implementiert werden. Ändert sich der v1-Katalog, ändert
sich diese Liste — sie ist die Quelle der Wahrheit für den Struktur-Linter,
nicht für die Tools selbst.
"""

from __future__ import annotations

# Tool-Familie 1 — Engram-Vault-Tools (D1/D4).
_ENGRAM_VAULT_TOOLS = frozenset(
    {
        "ingest",
        "search_pages",
        "get_page",
        "upsert_page",
        "compile_next",
        "compile_done",
        "get_tbox",
    },
)

# Tool-Familie 3 — Gridbert-Domänen-Tools (D2.2/D6).
_GRIDBERT_DOMAIN_TOOLS = frozenset(
    {
        "submit_invoice_facts",
        "get_switch_info",
        "capability_gap",
        # EDA-Kanal (WP2-E) + Lastgang-Prozess (WP2-P/WP2-M, Durchstich 2):
        # kein generisches ``submit_facts`` auf gridbert origin/main
        # (Stand `4f0dd7e`, geprüft beim Baustart von WP2-P) — deshalb das
        # schmale ``submit_lastgang_facts`` statt eines Neubaus.
        "request_data_release",
        "get_data_release_status",
        "list_load_series",
        "submit_lastgang_facts",
    },
)

EXTERN_TOOLS_V1: frozenset[str] = _ENGRAM_VAULT_TOOLS | _GRIDBERT_DOMAIN_TOOLS
