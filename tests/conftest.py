from __future__ import annotations

import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
FILES_DIR = REPO_ROOT / "files"


@pytest.fixture(scope="session")
def lbrn2_file():
    return FILES_DIR / "shelf.lbrn2"


@pytest.fixture(scope="session")
def stl_file():
    return FILES_DIR / "testfile.stl"


@pytest.fixture(scope="session")
def svg_file():
    return FILES_DIR / "octopus.svg"


@pytest.fixture(scope="session")
def three_mf_file():
    return FILES_DIR / "princess_donut.3mf"


@pytest.fixture(scope="session")
def cdr_file():
    return FILES_DIR / "live_laugh.cdr"


@pytest.fixture(scope="session")
def scad_file():
    return FILES_DIR / "sample.scad"


@pytest.fixture
def dxf_file(tmp_path):
    """Create a minimal valid DXF file using ezdxf."""
    import ezdxf

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_line((0, 0), (100, 0))
    msp.add_line((100, 0), (100, 100))
    msp.add_line((100, 100), (0, 100))
    msp.add_line((0, 100), (0, 0))
    msp.add_circle((50, 50), 30)
    path = tmp_path / "sample.dxf"
    doc.saveas(str(path))
    return path
