"""Frozen Windows helper entry point: deliberately independent of Qt/mpv."""
from firemedia.update_worker import main
if __name__ == '__main__':
    raise SystemExit(main())
