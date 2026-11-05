#!/usr/bin/env python3
"""Check every exact dependency pin before reusing the private virtual environment."""
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import sys


def matches(path):
    """Recursively compare pinned requirements with installed distribution versions."""
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('-r '):
            if not matches(path.parent / line[3:].strip()):
                return False
            continue
        name, separator, wanted = line.partition('==')
        if not separator:
            return False
        try:
            if version(name) != wanted:
                return False
        except PackageNotFoundError:
            return False
    return True


if __name__ == '__main__':
    sys.exit(0 if matches(Path(__file__).resolve().parents[1] / 'requirements.txt') else 1)
