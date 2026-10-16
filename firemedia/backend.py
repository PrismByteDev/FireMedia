"""Small libmpv binding. Playback stays in libmpv; Qt owns the interface."""
import ctypes as C
import locale
from .runtime import load_mpv
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

class MpvError(RuntimeError):
    pass

class Player(QObject):
    changed = pyqtSignal()
    ended = pyqtSignal()
    error = pyqtSignal(str)
    async_completed = pyqtSignal(int,str)

    def __init__(self, window_id=0, parent=None, silent=False, render_api=False):
        super().__init__(parent)
        try:
            self.lib = load_mpv()
        except OSError as error:
            raise MpvError(str(error)) from error
        library = self.lib._name
        self.lib.mpv_create.restype = C.c_void_p
        self.lib.mpv_set_option_string.argtypes = [C.c_void_p, C.c_char_p, C.c_char_p]
        self.lib.mpv_initialize.argtypes = [C.c_void_p]
        self.lib.mpv_command_async.argtypes = [C.c_void_p, C.c_uint64, C.POINTER(C.c_char_p)]
        self.async_sequence=0
        self.lib.mpv_command.argtypes = [C.c_void_p, C.POINTER(C.c_char_p)]
        self.lib.mpv_get_property_string.argtypes = [C.c_void_p, C.c_char_p]
        self.lib.mpv_get_property_string.restype = C.c_void_p
        self.lib.mpv_set_property_string.argtypes = [C.c_void_p, C.c_char_p, C.c_char_p]
        self.lib.mpv_free.argtypes = [C.c_void_p]
        self.lib.mpv_terminate_destroy.argtypes = [C.c_void_p]
        self.lib.mpv_error_string.argtypes = [C.c_int]
        self.lib.mpv_error_string.restype = C.c_char_p
        class Event(C.Structure):
            _fields_ = [('event_id', C.c_int), ('error', C.c_int), ('reply_userdata', C.c_uint64), ('data', C.c_void_p)]
        class End(C.Structure):
            _fields_ = [('reason', C.c_int), ('error', C.c_int), ('playlist_entry_id', C.c_int64),
                        ('playlist_insert_id', C.c_int64), ('playlist_insert_num_entries', C.c_int)]
        self.Event, self.End = Event, End
        self.lib.mpv_wait_event.argtypes = [C.c_void_p, C.c_double]
        self.lib.mpv_wait_event.restype = C.POINTER(Event)
        # QApplication can adopt the desktop locale. libmpv requires the exact
        # C numeric locale (even en_US with a decimal point is rejected).
        # Keep it for the player's lifetime; leave other locale categories alone.
        locale.setlocale(locale.LC_NUMERIC, 'C')
        self.handle = self.lib.mpv_create()
        if not self.handle:
            raise MpvError(f'libmpv could not create a player context ({library}, numeric locale C). It may be unable to allocate resources.')
        options = {'terminal':'no', 'input-default-bindings':'no', 'input-vo-keyboard':'no',
                   'osc':'no', 'audio-display':'no', 'idle':'yes', 'keep-open':'no', 'hwdec':'auto', 'volume':'100',
                   'sub-font':'Sans', 'sub-font-size':'38', 'sub-border-size':'2',
                   'sub-auto':'no', 'sub-shadow-offset':'2', 'sub-ass-override':'force', 'ytdl':'no'}
        if silent:
            options.update(ao='null', vo='null')
        elif render_api:
            options['vo']='libmpv'
        elif window_id:
            options['wid'] = str(window_id)
        for key, value in options.items():
            result=self.lib.mpv_set_option_string(self.handle, key.encode(), value.encode())
            if result<0:
                message=self.lib.mpv_error_string(result).decode('utf-8','replace')
                self.close()
                raise MpvError(f'Could not set media option {key}: {message}')
        result = self.lib.mpv_initialize(self.handle)
        if result < 0:
            message = self.lib.mpv_error_string(result).decode('utf-8', 'replace')
            self.close()
            raise MpvError(f'Could not initialize libmpv: {message} (error {result})')
        self.loaded = False
        self.load_generation=0
        self.timer = QTimer(self)
        self.timer.setInterval(70)
        self.timer.timeout.connect(self.poll)
        self.timer.start()

    def command(self, *args):
        if not self.handle:
            return False
        encoded = [str(arg).encode('utf-8') for arg in args]
        vector = (C.c_char_p * (len(encoded) + 1))(*encoded, None)
        result = self.lib.mpv_command(self.handle, vector)
        if result < 0:
            self.error.emit(self.lib.mpv_error_string(result).decode())
        return result >= 0

    def command_async(self,*args):
        self.async_sequence+=1
        encoded=[str(arg).encode('utf-8') for arg in args]
        vector=(C.c_char_p*(len(encoded)+1))(*encoded,None)
        result=self.lib.mpv_command_async(self.handle,self.async_sequence,vector)
        return self.async_sequence if result>=0 else 0

    def get(self, name, default=''):
        if not self.handle:
            return default
        pointer = self.lib.mpv_get_property_string(self.handle, name.encode())
        if not pointer:
            return default
        try:
            return C.string_at(pointer).decode('utf-8', 'replace')
        finally:
            self.lib.mpv_free(pointer)

    def number(self, name, default=0):
        try:
            return float(self.get(name))
        except ValueError:
            return default

    def set(self, name, value):
        if isinstance(value, bool):
            value = 'yes' if value else 'no'
        if self.handle:
            return self.lib.mpv_set_property_string(self.handle, name.encode(), str(value).encode()) >= 0
        return False

    def load(self, source):
        self.load_generation+=1
        self.loaded = False
        self.command('loadfile', source, 'replace')
        self.set('pause', False)

    def poll(self):
        for _ in range(80):
            event = self.lib.mpv_wait_event(self.handle, 0).contents
            if event.event_id == 0:
                break
            if event.event_id == 5:
                message=self.lib.mpv_error_string(event.error).decode('utf-8','replace') if event.error<0 else ''
                self.async_completed.emit(event.reply_userdata,message)
            if event.event_id == 8:  # MPV_EVENT_FILE_LOADED
                self.loaded = True
            elif event.event_id == 7 and event.data:  # MPV_EVENT_END_FILE
                end = C.cast(event.data, C.POINTER(self.End)).contents
                self.loaded = False
                if end.reason == 0:
                    self.ended.emit()
                elif end.reason == 4:
                    self.error.emit(self.lib.mpv_error_string(end.error).decode('utf-8', 'replace'))
        self.changed.emit()

    def equalizer(self, gains):
        centers = [60, 170, 350, 1000, 3500, 10000]
        graph = ','.join(f'equalizer=f={f}:t=o:w=1:g={float(g):.2f}' for f,g in zip(centers,gains))
        # A single replaceable chain avoids stacking filters on every slider move.
        self.command('af', 'set', f'lavfi=[{graph}]' if any(gains) else '')

    def close(self):
        if hasattr(self, 'timer'):
            self.timer.stop()
        if self.handle:
            self.lib.mpv_terminate_destroy(self.handle)
            self.handle = None
