"""Run with python3 -m firemedia [files, directories, M3U/M3U8 or URLs]."""
import argparse
import os
import sys
import signal

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import QTimer, Qt
from . import __version__


def main():
    # Background update invocations do not construct Qt, mpv, or visual effects.
    if '--update-worker' in sys.argv:
        from .update_worker import main as updater
        return updater(['check'])
    from .window import Window, STYLE
    from .backend import MpvError
    parser=argparse.ArgumentParser(description='FireMedia native media player')
    parser.add_argument('--version',action='version',version=f'FireMedia {__version__}')
    parser.add_argument('sources',nargs='*',help='Media files, folders, M3U/M3U8 playlists or HTTP(S) streams')
    parser.add_argument('--fullscreen',action='store_true')
    parser.add_argument('--state',help='Use a separate state file')
    parser.add_argument('--resume-update',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app=QApplication(sys.argv[:1]);app.setApplicationName('FireMedia');app.setOrganizationName('FireMedia')
    app.setStyle('Fusion');app.setStyleSheet(STYLE)
    try: window=Window(args.state)
    except MpvError as error:
        QMessageBox.critical(None,'FireMedia',str(error));return 1
    signal.signal(signal.SIGINT, lambda *_: window.close())
    signal.signal(signal.SIGTERM, lambda *_: window.close())
    window.show()
    if args.fullscreen: window.toggle_fullscreen()
    if args.sources: QTimer.singleShot(0,lambda:window.add_sources(args.sources))
    if args.resume_update:
        from .update_core import read_json
        path=window.state_path.parent/'update-resume.json';resume=read_json(path);path.unlink(missing_ok=True)
        if resume.get('source'):
            QTimer.singleShot(0,lambda:window.resume_after_update(resume))
    return app.exec()

if __name__=='__main__':
    sys.exit(main())
