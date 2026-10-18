"""Playback sleep inhibition. Audio inhibits suspend; video also inhibits idle."""
import ctypes
import sys
import secrets
from PyQt6.QtCore import QObject, QVariant, QMetaType


class WakeLock(QObject):
    def __init__(self, parent=None):
        super().__init__(parent); self.flags = 0; self.generation = 0; self.locks = []; self.pending = []
        self.error = ''

    def update(self, playing, video=False):
        flags = (4 | (8 if video else 0)) if playing else 0
        if flags == self.flags: return
        self.release(); self.flags = flags
        if not flags: return
        if sys.platform == 'win32':
            state = 0x80000000 | 0x1 | (0x2 if video else 0)
            if not ctypes.windll.kernel32.SetThreadExecutionState(state): self.error = 'Windows did not grant the playback wake lock.'
        elif sys.platform.startswith('linux'):
            self._request('org.freedesktop.portal.Desktop', '/org/freedesktop/portal/desktop',
                          'org.freedesktop.portal.Inhibit', 'Inhibit', ['', self._uint(flags), {'reason': 'FireMedia playback'}], 'portal')

    @staticmethod
    def _uint(number):
        value = QVariant(number); value.convert(QMetaType(QMetaType.Type.UInt.value)); return value

    def _request(self, service, path, interface, method, arguments, kind):
        from PyQt6.QtDBus import QDBusConnection, QDBusMessage, QDBusPendingCallWatcher, QDBusPendingReply
        bus=QDBusConnection.sessionBus()
        predicted=None
        if kind=='portal':
            token='firemedia_'+secrets.token_hex(12);arguments[-1]['handle_token']=token
            sender=bus.baseService().lstrip(':').replace('.','_')
            predicted=(service,path,interface,f'/org/freedesktop/portal/desktop/request/{sender}/{token}',kind)
            self.locks.append(predicted)
        message = QDBusMessage.createMethodCall(service, path, interface, method); message.setArguments(arguments)
        watcher = QDBusPendingCallWatcher(bus.asyncCall(message, 2000), self)
        generation = self.generation; self.pending.append(watcher)
        def finished(call):
            reply = QDBusPendingReply(call).reply(); values = reply.arguments()
            if predicted in self.locks:self.locks.remove(predicted)
            if reply.type() != QDBusMessage.MessageType.ErrorMessage and values:
                token = values[0].path() if hasattr(values[0], 'path') else values[0]
                lock = (service, path, interface, token, kind)
                if generation == self.generation and self.flags: self.locks.append(lock)
                else: self._release_one(lock)
            elif generation == self.generation and self.flags and kind == 'portal':
                self._request('org.freedesktop.PowerManagement.Inhibit', '/org/freedesktop/PowerManagement/Inhibit',
                              'org.freedesktop.PowerManagement.Inhibit', 'Inhibit', ['FireMedia', 'Media playback'], 'cookie')
                if self.flags & 8:
                    self._request('org.freedesktop.ScreenSaver', '/ScreenSaver', 'org.freedesktop.ScreenSaver',
                                  'Inhibit', ['FireMedia', 'Video playback'], 'cookie')
            elif generation == self.generation: self.error = 'The desktop did not grant a playback wake lock.'
            if call in self.pending: self.pending.remove(call)
            call.deleteLater()
        watcher.finished.connect(finished)

    def _release_one(self, lock):
        from PyQt6.QtDBus import QDBusConnection, QDBusMessage
        service, path, interface, token, kind = lock
        if kind == 'portal': path, interface, method, arguments = str(token), 'org.freedesktop.portal.Request', 'Close', []
        else: method, arguments = 'UnInhibit', [self._uint(int(token))]
        message = QDBusMessage.createMethodCall(service, path, interface, method); message.setArguments(arguments)
        QDBusConnection.sessionBus().asyncCall(message, 2000)

    def release(self):
        self.generation += 1
        if self.flags and sys.platform == 'win32': ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        for lock in self.locks: self._release_one(lock)
        self.locks.clear(); self.flags = 0
