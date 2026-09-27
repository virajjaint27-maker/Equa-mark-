"""Test package bootstrap: make vendored deps + ffmpeg available."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import bootstrap  # noqa: E402
bootstrap.setup()
