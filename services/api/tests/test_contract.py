"""The committed response-field list the mobile app is checked against must match the API."""

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_contract.py"


def test_the_mobile_contract_file_is_current() -> None:
    spec = importlib.util.spec_from_file_location("export_contract", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    committed = json.loads(module.TARGET.read_text())
    assert module.build() == committed, (
        "API response fields changed. Regenerate with: "
        "cd services/api && PYTHONPATH=. python scripts/export_contract.py"
    )
