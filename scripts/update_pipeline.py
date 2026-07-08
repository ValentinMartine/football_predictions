from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    run([sys.executable, "scripts/download_data.py"])
    run([sys.executable, "-m", "src.export"])


if __name__ == "__main__":
    main()
