from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def pytest_addoption(parser):
    parser.addoption("--offline-geometry", action="store_true",
                     help="Skip tests that access the external simulator checkout")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--offline-geometry"):
        return
    external = {"test_actual_marl_race_loads_new_backend_bundle",
                "test_vehicle_sources_and_advisory_are_separate_from_validity"}
    for item in items:
        if item.path.name == "test_marl_race_integration.py" or item.originalname in external:
            item.add_marker(pytest.mark.skip(reason="Offline geometry run: external checkout access disabled"))


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
