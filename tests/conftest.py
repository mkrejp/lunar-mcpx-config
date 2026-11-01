"""Pytest path setup so tests can import helpers from docker/."""

from __future__ import annotations

import sys
from pathlib import Path

DOCKER_DIR = Path(__file__).resolve().parents[1] / "docker"
if str(DOCKER_DIR) not in sys.path:
    sys.path.insert(0, str(DOCKER_DIR))
