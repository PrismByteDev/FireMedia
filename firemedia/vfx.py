"""Stage picture edits locally; release the held image after apply and rendering."""
from PyQt6.QtCore import QObject,pyqtSignal

class VfxSession(QObject):
    finished=pyqtSignal()
    failed=pyqtSignal(str)
    def __init__(self,player,video=None,parent=None):
        super().__init__(parent);self.player=player;self.video=video
        self.draft={k:player.number(k) for k in ('brightness','contrast','saturation','gamma')}
        self.pending=set();self.errors=[];self.applying=False;self.frames_needed=0
        player.async_completed.connect(self.reply)
        if video:video.frame_presented.connect(self.presented)
    def apply(self):
        if self.applying:return
        self.applying=True;self.errors=[];self.pending=set()
        for name,value in self.draft.items():
            token=self.player.command_async('set',name,str(value))
            if token:self.pending.add(token)
            else:self.errors.append('Could not apply '+name)
        if not self.pending:self.complete_commands()
    def reply(self,token,error):
        if token not in self.pending:return
        self.pending.remove(token)
        if error:self.errors.append(error)
        if not self.pending:self.complete_commands()
    def complete_commands(self):
        if self.errors:
            self.applying=False;self.failed.emit('; '.join(self.errors));return
        if self.video and self.video.is_ready:
            self.frames_needed=2;self.video.holding=False;self.video.update()
        else:self.applying=False;self.finished.emit()
    def presented(self):
        if not self.frames_needed:return
        self.frames_needed-=1
        if self.frames_needed:self.video.update()
        else:self.applying=False;self.finished.emit()
    def close(self):
        self.player.async_completed.disconnect(self.reply)
        if self.video:
            self.video.frame_presented.disconnect(self.presented)
            self.video.holding=False;self.video.update()
