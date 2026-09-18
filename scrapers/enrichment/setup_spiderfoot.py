"""One-time setup for the SpiderFoot integration: clones SpiderFoot (MIT
licensed) into vendor/spiderfoot/ and installs its dependencies into a
dedicated virtual environment there, kept separate from this project's own
venv since SpiderFoot pins some much older library versions.

vendor/ is gitignored - every teammate runs this once, locally, rather than
committing someone else's ~900-file repo into ours.

Run once: python -m scrapers.enrichment.setup_spiderfoot
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VENDOR_ROOT = REPO_ROOT / "vendor" / "spiderfoot"
REQUIREMENTS = Path(__file__).resolve().parent / "spiderfoot_requirements.txt"
SPIDERFOOT_URL = "https://github.com/smicallef/spiderfoot.git"


def main() -> None:
    if not VENDOR_ROOT.exists():
        print(f"Cloning SpiderFoot into {VENDOR_ROOT} ...")
        subprocess.run(
            ["git", "clone", "--depth", "1", SPIDERFOOT_URL, str(VENDOR_ROOT)],
            check=True,
        )
    else:
        print(f"{VENDOR_ROOT} already exists, skipping clone.")

    venv_dir = VENDOR_ROOT / ".venv"
    venv_python = venv_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not venv_python.exists():
        print("Creating SpiderFoot's dedicated virtual environment ...")
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)

    print("Installing SpiderFoot's dependencies (this can take a few minutes) ...")
    subprocess.run(
        [str(venv_python), "-m", "pip", "install", "--quiet", "--upgrade", "pip"],
        check=True,
    )
    subprocess.run(
        [str(venv_python), "-m", "pip", "install", "--quiet", "-r", str(REQUIREMENTS)],
        check=True,
    )
    print("Done. Try it: python -m scripts.demo_spiderfoot_synthesis")


if __name__ == "__main__":
    main()
