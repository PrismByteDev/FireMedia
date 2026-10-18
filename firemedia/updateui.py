"""Nonblocking update settings, desktop notifications, and restart handoff."""
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal, QProcess
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QComboBox, QLabel, QPushButton, QWidget, QHBoxLayout,
                            QMessageBox, QSystemTrayIcon, QCheckBox)
from . import __version__
from .update_core import (AUTO_MODES, MODES, INTERVAL, RELEASES, atomic_json, current_version,
                          package_kind, read_json, update_lock, version)
from .update_platform import configure_background, background_supported, appimage_desktop
from .update_worker import check

LABELS = {'background': 'Background updates', 'launch': 'Update on launch', 'notify': 'Notify me', 'disabled': 'Disabled'}


class UpdateManager(QObject):
    completed = pyqtSignal(object)
    changed = pyqtSignal()

    def __init__(self, window, active=True):
        super().__init__(window); self.window = window; self.kind, self.target = package_kind()
        self.config = window.state_path.parent / 'updates.json'; self.active = active
        self.mode = read_json(self.config).get('mode', 'notify'); self.busy = False; self.pending_mode = None
        self.result = {}; self.message = 'Installed version: ' + __version__; self.closed = False; self.manual = False
        self.modes = list(AUTO_MODES if self.kind in ('windows', 'appimage') else MODES)
        self.background = self.kind == 'windows' or (self.kind == 'appimage' and background_supported(self.kind)) if active else False
        if not self.background and 'background' in self.modes: self.modes.remove('background')
        if self.mode not in self.modes: self.mode = 'notify'
        self.completed.connect(self.finish)
        self.timer = QTimer(self); self.timer.setInterval(INTERVAL * 1000); self.timer.timeout.connect(self.check)
        self.restart_timer = QTimer(self); self.restart_timer.setInterval(1500); self.restart_timer.timeout.connect(self.poll_install)
        self.session = None
        if active:
            self.timer.start(); self.restart_timer.start()
            QTimer.singleShot(3000, self.check)
            if self.kind == 'windows':
                self.nonce = secrets.token_hex(32)
                self.session = self.config.parent / 'update-sessions' / (self.nonce + '.json')
                atomic_json(self.session, {'pid': os.getpid(), 'nonce': self.nonce})
            if self.kind == 'appimage' and not read_json(self.config).get('setup_done'):
                QTimer.singleShot(1000, self.setup_appimage)

    def work(self, function, manual=False):
        if self.busy or self.closed: return False
        self.busy = True; self.manual = manual; self.message = 'Checking / applying update settings…'; self.changed.emit()
        def worker():
            try: result = function()
            except Exception as error: result = {'status': 'error', 'message': str(error)}
            if not self.closed:
                try: self.completed.emit(result)
                except RuntimeError: pass
        threading.Thread(target=worker, name='firemedia-updates', daemon=True).start()
        return True

    def check(self, manual=False, install=False):
        if not self.active or (self.mode == 'disabled' and not manual): return
        self.work(lambda: check(self.config, self.kind, self.target, force=manual, install=install), manual)

    def set_mode(self, mode):
        if mode not in self.modes: return
        self.mode = mode
        if self.busy: self.pending_mode = mode; return
        def apply():
            with update_lock(self.config):
                state = read_json(self.config)
                configure_background(self.kind, self.target, mode == 'background', self.config)
                state.update(mode=mode, setup_done=True); atomic_json(self.config, state)
            return {'status': 'settings', 'message': 'Update mode saved.'}
        self.work(apply)

    def finish(self, result):
        if self.closed: return
        self.busy = False; self.result = result
        self.message = result.get('message', 'No new update available.'); self.changed.emit()
        if result.get('status') == 'available':
            self.window.notify(self.message + ' Open Settings → Updates.')
            if self.kind == 'flatpak' and result.get('notify'): self.portal_notification(self.message)
        elif result.get('status') == 'installed': self.window.notify(self.message)
        elif result.get('status') == 'error' and self.manual: self.window.notify('Update check failed: ' + self.message)
        if self.pending_mode is not None:
            mode = self.pending_mode; self.pending_mode = None; self.set_mode(mode)

    def portal_notification(self, message):
        try:
            from PyQt6.QtDBus import QDBusConnection, QDBusMessage
            call = QDBusMessage.createMethodCall('org.freedesktop.portal.Desktop', '/org/freedesktop/portal/desktop',
                                                'org.freedesktop.portal.Notification', 'AddNotification')
            call.setArguments(['firemedia-update', {'title': 'FireMedia update', 'body': message}])
            QDBusConnection.sessionBus().asyncCall(call, 2000)
        except ImportError: pass

    def poll_install(self):
        if self.closed: return
        try:
            installed = current_version(self.target) if self.kind == 'windows' else read_json(self.config).get('installed_version', __version__)
            if version(installed) > version(__version__) and self.result.get('status') != 'installed':
                self.result = {'status': 'installed', 'version': installed}; self.message = f'FireMedia {installed} installed. Restart to apply.'
                self.window.notify(self.message); self.changed.emit()
            if self.session:
                request = read_json(self.session.with_suffix('.restart.json'))
                if request.get('nonce') == self.nonce and request.get('version') == installed and version(installed) > version(__version__):
                    self.save_resume(); self.window.close()
        except (OSError, ValueError): pass

    def save_resume(self):
        w = self.window
        atomic_json(self.config.parent / 'update-resume.json', {'source': w.current.source if w.current else '',
                    'position': w.player.number('time-pos'), 'paused': w.player.get('pause') == 'yes'})

    def restart(self):
        if self.result.get('status') != 'installed': return
        if self.kind == 'windows':
            QProcess.startDetached(str(self.target / 'FireMediaUpdate.exe'), ['restart', '--config', str(self.config)])
        elif self.kind == 'appimage':
            self.save_resume()
            QApplication = __import__('PyQt6.QtWidgets', fromlist=['QApplication']).QApplication
            QApplication.instance().aboutToQuit.connect(lambda: QProcess.startDetached(str(self.target), ['--resume-update']))
            self.window.close()

    def add_settings(self, form, dialog):
        row = QWidget(); layout = QHBoxLayout(row); layout.setContentsMargins(0, 0, 0, 0)
        mode = QComboBox()
        for item in self.modes: mode.addItem(LABELS[item], item)
        mode.setCurrentIndex(max(0, mode.findData(self.mode))); mode.currentIndexChanged.connect(lambda: self.set_mode(mode.currentData()))
        layout.addWidget(mode, 1)
        check_button = QPushButton('Check now'); check_button.clicked.connect(lambda: self.check(manual=True)); layout.addWidget(check_button)
        form.addRow('Updates', row)
        status = QLabel(self.message); status.setWordWrap(True); form.addRow(status)
        actions = QWidget(); buttons = QHBoxLayout(actions); buttons.setContentsMargins(0, 0, 0, 0)
        update = QPushButton('Update now'); restart = QPushButton('Restart to apply'); view = QPushButton('View release / store')
        buttons.addWidget(update); buttons.addWidget(restart); buttons.addWidget(view); form.addRow(actions)
        def install():
            if QMessageBox.question(dialog, 'Update FireMedia', 'Download and install the available update? Playback can continue until you restart.') == QMessageBox.StandardButton.Yes:
                self.check(manual=True, install=True)
        update.clicked.connect(install); restart.clicked.connect(self.restart)
        view.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.result.get('url', RELEASES))))
        def refresh():
            status.setText(self.message); check_button.setEnabled(not self.busy)
            update.setVisible(self.kind in ('windows', 'appimage') and self.result.get('status') == 'available'); update.setEnabled(not self.busy)
            restart.setVisible(self.result.get('status') == 'installed')
        self.changed.connect(refresh); dialog.finished.connect(lambda: self.changed.disconnect(refresh)); refresh()
        info = QLabel('Background updates run every ten minutes while signed in. Notify never installs without your choice.' if self.kind in ('windows', 'appimage')
                      else 'Updates are installed through your software manager or the release download. FireMedia only notifies you.')
        info.setWordWrap(True); form.addRow(info)

    def setup_appimage(self):
        if self.closed: return
        dialog, form = self.window.dialog('Set up FireMedia AppImage')
        info = QLabel('Choose update behavior and whether to make FireMedia available in Open With. You can change updates later in Settings.'); info.setWordWrap(True); form.addRow(info)
        mode = QComboBox()
        for item in self.modes: mode.addItem(LABELS[item], item)
        mode.setCurrentIndex(mode.findData('notify')); form.addRow('Updates', mode)
        associate = QCheckBox('Register FireMedia for media files and add it to the application menu'); form.addRow(associate)
        dialog.exec()
        try:
            if associate.isChecked(): appimage_desktop(self.target)
            self.set_mode(mode.currentData())
        except (OSError, ValueError) as error: self.window.notify(str(error))
        dialog.deleteLater()

    def close(self):
        self.closed = True; self.timer.stop(); self.restart_timer.stop()
        if self.session:
            self.session.unlink(missing_ok=True); self.session.with_suffix('.restart.json').unlink(missing_ok=True)
