# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Serialisierungs-/Envelope-Tests (B.6, Durchstich-1-Subset).

Pin gegen Format-Drift: ``_to_jsonable`` liefert stdlib-json-fähige Werte
(date → ISO), ``CapabilityRejection`` hat eine einheitliche ok/error-Semantik,
und die MCP-exponierten Capabilities befüllen ``meta``.
"""

from __future__ import annotations

import json
from datetime import date, datetime

from pydantic import BaseModel

from energietools.capabilities.base import (
    Capability,
    CapabilityRejection,
    FunctionCapability,
)
from energietools.capabilities.registry import default_registry


class _DateModel(BaseModel):
    datum: date
    zeit: datetime


class TestToJsonable:
    def test_pydantic_date_wird_iso(self):
        out = FunctionCapability._to_jsonable(
            _DateModel(datum=date(2026, 1, 1), zeit=datetime(2026, 1, 1, 12, 0)),
        )
        json.dumps(out)  # darf nicht werfen (stdlib-json-MCP-Server-Fall)
        assert out["datum"] == "2026-01-01"

    def test_nacktes_date_in_dict_und_liste(self):
        out = FunctionCapability._to_jsonable(
            {"anomalien": [{"datum": date(2026, 2, 2)}], "stand": datetime(2026, 2, 2, 8)},
        )
        json.dumps(out)
        assert out["anomalien"][0]["datum"] == "2026-02-02"

    def test_skalare_unveraendert(self):
        assert FunctionCapability._to_jsonable(1.5) == 1.5
        assert FunctionCapability._to_jsonable(None) is None
        assert FunctionCapability._to_jsonable("x") == "x"


class _RejectingCapability(Capability):
    name = "rejecting_test"
    summary = "wirft eine strukturierte Ablehnung"

    def _run(self, **kwargs):
        raise CapabilityRejection(
            "Nichts wurde gespeichert.",
            [{"feld": "x", "regel": "test_regel", "wert": 1, "rueckfrage": "Bitte prüfen."}],
        )


class TestRejectionEnvelope:
    def test_ok_false_mit_strukturierten_fehlern(self):
        result = _RejectingCapability().run()
        assert result.ok is False
        assert result.error == "Nichts wurde gespeichert."
        assert result.data["fehler"][0]["regel"] == "test_regel"
        json.dumps(result.model_dump(mode="json"))


class TestMetaBefuellung:
    """B.6: die WP-G1-exponierten Tools tragen meta (stand/quelle/snapshot_version)."""

    def test_exponierte_tools_haben_meta(self):
        reg = default_registry()
        # versorger_abdeckung (Snapshot-basiert): stand + quelle + version
        result = reg.get("versorger_abdeckung").run(plz="1060")
        assert result.ok is True
        assert result.meta.get("stand")
        assert result.meta.get("quelle")
        assert result.meta.get("snapshot_version")
        # validate_invoice_facts / finalize_invoice: quelle + version (kein Snapshot)
        for name in ("validate_invoice_facts", "finalize_invoice"):
            r = reg.get(name).run()  # leeres Payload → Rejection, meta trotzdem da
            assert r.ok is False
            assert r.meta.get("quelle"), name

    def test_meta_fehler_kippt_nie_das_result(self):
        class _KaputtesMeta(Capability):
            name = "kaputtes_meta_test"
            summary = "meta wirft"

            def _meta(self, **kwargs):
                raise RuntimeError("boom")

            def _run(self, **kwargs):
                return {"ok": 1}

        result = _KaputtesMeta().run()
        assert result.ok is True
        assert result.meta == {}
