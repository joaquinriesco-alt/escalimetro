import os
import subprocess
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "benchmarks"))


@pytest.fixture(scope="session")
def synthetic_case(tmp_path_factory):
    """Genera el fixture sintético en un tmp para no ensuciar cases/."""
    d = tmp_path_factory.mktemp("case") / "900_synthetic_fixture"
    subprocess.run([sys.executable, os.path.join(ROOT, "fixtures", "make_synthetic.py"), str(d)], check=True)
    return str(d)
