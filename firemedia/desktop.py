"""Keep Linux desktop integration optional on other operating systems."""
import sys

if sys.platform.startswith('linux'):
    from .mpris import Mpris
else:
    class Mpris:
        available = False

        def __init__(self, window):
            pass

        def refresh(self, *unused):
            pass

        def close(self):
            pass
