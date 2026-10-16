"""Render libmpv frames into Qt's framebuffer; never create a player window."""
import ctypes as C
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QSurfaceFormat
from PyQt6.QtOpenGLWidgets import QOpenGLWidget

class RenderParam(C.Structure):
    _fields_=[('type',C.c_int),('data',C.c_void_p)]

ProcAddress=C.CFUNCTYPE(C.c_void_p,C.c_void_p,C.c_char_p)
UpdateCallback=C.CFUNCTYPE(None,C.c_void_p)

class GLInit(C.Structure):
    _fields_=[('get_proc_address',ProcAddress),('context',C.c_void_p)]

class Framebuffer(C.Structure):
    _fields_=[('fbo',C.c_int),('width',C.c_int),('height',C.c_int),('format',C.c_int)]

class VideoSurface(QOpenGLWidget):
    frame_available=pyqtSignal()
    frame_presented=pyqtSignal()
    ready=pyqtSignal()
    failed=pyqtSignal(str)
    double_clicked=pyqtSignal()

    def __init__(self,parent=None):
        super().__init__(parent)
        format=QSurfaceFormat();format.setVersion(3,2)
        format.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        self.setFormat(format)
        self.player=None
        self.render_context=C.c_void_p()
        self.closing=False
        self.holding=False
        self.frames_rendered=0
        self.frame_available.connect(self.update,Qt.ConnectionType.QueuedConnection)
        self.setMinimumSize(1,1)

    @property
    def is_ready(self): return bool(self.render_context)

    def bind(self,player):
        self.player=player
        lib=player.lib
        lib.mpv_render_context_create.argtypes=[C.POINTER(C.c_void_p),C.c_void_p,C.POINTER(RenderParam)]
        lib.mpv_render_context_create.restype=C.c_int
        lib.mpv_render_context_render.argtypes=[C.c_void_p,C.POINTER(RenderParam)]
        lib.mpv_render_context_render.restype=C.c_int
        lib.mpv_render_context_set_update_callback.argtypes=[C.c_void_p,UpdateCallback,C.c_void_p]
        lib.mpv_render_context_free.argtypes=[C.c_void_p]
        self._proc=ProcAddress(self.proc_address)
        self._update=UpdateCallback(self.on_frame)
        self._no_update=UpdateCallback()

    def proc_address(self,unused,name):
        pointer=self.context().getProcAddress(name)
        return int(pointer) if pointer else 0

    def on_frame(self,unused):
        # This callback runs on mpv's thread; only queue a Qt update here.
        if not self.closing: self.frame_available.emit()

    def initializeGL(self):
        if not self.player or self.closing: return
        self.context().aboutToBeDestroyed.connect(self.cleanup)
        api=C.create_string_buffer(b'opengl')
        init=GLInit(self._proc,None)
        params=(RenderParam*3)(RenderParam(1,C.cast(api,C.c_void_p)),
                              RenderParam(2,C.cast(C.pointer(init),C.c_void_p)),RenderParam())
        result=self.player.lib.mpv_render_context_create(C.byref(self.render_context),self.player.handle,params)
        if result<0:
            self.failed.emit('Video renderer: '+self.player.lib.mpv_error_string(result).decode())
        else:
            self.player.lib.mpv_render_context_set_update_callback(self.render_context,self._update,None)
            self.ready.emit()

    def paintGL(self):
        if not self.is_ready or self.closing: return
        scale=self.devicePixelRatioF()
        fbo=Framebuffer(self.defaultFramebufferObject(),round(self.width()*scale),round(self.height()*scale),0)
        flip=C.c_int(1);block=C.c_int(0);skip=C.c_int(int(self.holding))
        params=(RenderParam*5)(RenderParam(3,C.cast(C.pointer(fbo),C.c_void_p)),
            RenderParam(4,C.cast(C.pointer(flip),C.c_void_p)),
            RenderParam(12,C.cast(C.pointer(block),C.c_void_p)),RenderParam(13,C.cast(C.pointer(skip),C.c_void_p)),RenderParam())
        result=self.player.lib.mpv_render_context_render(self.render_context,params)
        if result>=0 and not self.holding:
            self.frames_rendered+=1;self.frame_presented.emit()

    def mouseDoubleClickEvent(self,event): self.double_clicked.emit()

    def cleanup(self):
        if not self.is_ready: return
        self.makeCurrent()
        self.player.lib.mpv_render_context_set_update_callback(self.render_context,self._no_update,None)
        self.player.lib.mpv_render_context_free(self.render_context)
        self.render_context=C.c_void_p()
        self.doneCurrent()

    def shutdown(self):
        self.closing=True
        self.cleanup()
