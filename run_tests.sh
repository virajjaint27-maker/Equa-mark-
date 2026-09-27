#!/usr/bin/env bash
# AquaMark test suite — renders real videos, verifies real pixels.
set -u
cd "$(dirname "$0")"
echo "=== AquaMark test suite ==="
# discover from the project root so tests are imported as `tests.test_*`
# (this runs tests/__init__.py, which bootstraps the vendored dependencies)
python3 -m unittest discover -s . -p "test_*.py" -v 2>&1 | tail -n 60
