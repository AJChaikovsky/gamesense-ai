from __future__ import annotations

from pathlib import Path

import pytest
from gamesense.tools.make_sample_clip import make_clip


@pytest.fixture(scope="session")
def sample_clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return make_clip(tmp_path_factory.mktemp("clips") / "sample.mp4", seconds=2.0, fps=30)
