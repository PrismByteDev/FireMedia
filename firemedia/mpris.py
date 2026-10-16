"""MPRIS2 through Qt D-Bus: desktop controls work without keyboard focus."""
import json
import math
import os
import uuid
from PyQt6.QtCore import QObject, QMetaType, QVariant, QUrl, pyqtClassInfo, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtDBus import QDBusAbstractAdaptor, QDBusConnection, QDBusMessage, QDBusObjectPath

ROOT='org.mpris.MediaPlayer2'
PLAYER=ROOT+'.Player'
PATH='/org/mpris/MediaPlayer2'
NO_TRACK=PATH+'/TrackList/NoTrack'


def int64(value):
    result=QVariant(int(value))
    result.convert(QMetaType(QMetaType.Type.LongLong.value))
    return result


@pyqtClassInfo('D-Bus Interface',ROOT)
class RootAdaptor(QDBusAbstractAdaptor):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner=owner

    @pyqtSlot()
    def Raise(self):
        w=self.owner.window
        if w.isMinimized(): w.showNormal()
        w.show();w.raise_();w.activateWindow()

    @pyqtSlot()
    def Quit(self): self.owner.window.close()

    CanQuit=pyqtProperty(bool,lambda self:True)
    CanRaise=pyqtProperty(bool,lambda self:True)
    HasTrackList=pyqtProperty(bool,lambda self:False)
    Identity=pyqtProperty(str,lambda self:'FireMedia')
    DesktopEntry=pyqtProperty(str,lambda self:'firemedia')
    SupportedUriSchemes=pyqtProperty('QStringList',lambda self:['file','http','https'])
    SupportedMimeTypes=pyqtProperty('QStringList',lambda self:[
        'audio/mpeg','audio/flac','audio/ogg','audio/x-wav','audio/mp4',
        'video/mp4','video/x-matroska','video/webm','audio/x-mpegurl','application/vnd.apple.mpegurl'])
    CanSetFullscreen=pyqtProperty(bool,lambda self:True)

    @pyqtProperty(bool)
    def Fullscreen(self): return self.owner.window.isFullScreen()
    @Fullscreen.setter
    def Fullscreen(self,value):
        if bool(value)!=self.Fullscreen: self.owner.window.toggle_fullscreen()


@pyqtClassInfo('D-Bus Interface',PLAYER)
class PlayerAdaptor(QDBusAbstractAdaptor):
    Seeked=pyqtSignal('qlonglong')

    def __init__(self, owner):
        super().__init__(owner)
        self.owner=owner

    @property
    def window(self): return self.owner.window

    @pyqtSlot()
    def Play(self):
        w=self.window
        if w.current:
            if w.player.get('idle-active')=='yes':
                w.player.load(w.current.source)
            else: w.player.set('pause',False)
        elif w.queue: w.play_index(0)
        self.owner.refresh()

    @pyqtSlot()
    def Pause(self):
        if self.window.current: self.window.player.set('pause',True)
        self.owner.refresh()

    @pyqtSlot()
    def PlayPause(self):
        if self.PlaybackStatus=='Playing': self.Pause()
        else: self.Play()

    @pyqtSlot()
    def Stop(self):
        self.window.player.command('stop')
        self.window.analysis.stop()

    def change_track(self, callback):
        paused=self.PlaybackStatus!='Playing'
        callback()
        if paused: self.window.player.set('pause',True)
        self.owner.refresh()

    @pyqtSlot()
    def Next(self):
        if self.CanGoNext: self.change_track(self.window.next)

    @pyqtSlot()
    def Previous(self):
        if self.CanGoPrevious: self.change_track(self.window.previous)

    def seek_to(self, seconds):
        self.window.player.command('seek',seconds,'absolute')
        self.window.restart_analysis(seconds)
        self.Seeked.emit(round(seconds*1_000_000))

    @pyqtSlot('qlonglong')
    def Seek(self, offset):
        if not self.CanSeek: return
        target=max(0,self.window.player.number('time-pos')+offset/1_000_000)
        duration=self.window.player.number('duration')
        if duration and target>duration: self.Next()
        else: self.seek_to(target)

    @pyqtSlot(QDBusObjectPath,'qlonglong')
    def SetPosition(self, track_id, position):
        if not self.CanSeek or track_id.path()!=self.owner.track_id() or position<0: return
        seconds=position/1_000_000
        duration=self.window.player.number('duration')
        if duration and seconds>duration: return
        self.seek_to(seconds)

    @pyqtSlot(str)
    def OpenUri(self, uri):
        url=QUrl(uri)
        if url.scheme() not in ('file','http','https'): return
        source=url.toLocalFile() if url.isLocalFile() else uri
        self.window.add_sources([source],replace=True)

    @pyqtProperty(str)
    def PlaybackStatus(self):
        player=self.window.player
        if not player.loaded or player.get('idle-active')=='yes': return 'Stopped'
        return 'Paused' if player.get('pause')=='yes' else 'Playing'

    @pyqtProperty(str)
    def LoopStatus(self): return 'None' if self.window.loop_mode=='Off' else self.window.loop_mode
    @LoopStatus.setter
    def LoopStatus(self,value):
        if value in ('None','Playlist','Track'):
            self.window.set_loop('Off' if value=='None' else value)
            self.owner.refresh()

    @pyqtProperty(bool)
    def Shuffle(self): return self.window.shuffle_mode!='Off'
    @Shuffle.setter
    def Shuffle(self,value):
        self.window.set_shuffle('On' if value else 'Off')
        self.owner.refresh()

    @pyqtProperty(float)
    def Volume(self): return self.window.volume.value()/100
    @Volume.setter
    def Volume(self,value):
        if math.isfinite(value): self.window.volume.setValue(round(max(0,min(1.5,value))*100))

    @pyqtProperty('qlonglong')
    def Position(self): return max(0,round(self.window.player.number('time-pos')*1_000_000))

    @pyqtProperty('QVariantMap')
    def Metadata(self):
        w=self.window
        if not w.current: return {'mpris:trackid':QDBusObjectPath(NO_TRACK)}
        source=w.current.source
        url=source if QUrl(source).scheme() else QUrl.fromLocalFile(source).toString()
        result={'mpris:trackid':QDBusObjectPath(self.owner.track_id()),'xesam:title':w.current.title,'xesam:url':url}
        duration=w.player.number('duration')
        if duration>0: result['mpris:length']=int64(round(duration*1_000_000))
        try:
            metadata=json.loads(w.player.get('metadata','{}'))
            if metadata.get('artist'):
                artists=QVariant([str(metadata['artist'])]);artists.convert(QMetaType(QMetaType.Type.QStringList.value))
                result['xesam:artist']=artists
            if metadata.get('album'): result['xesam:album']=str(metadata['album'])
        except (ValueError,TypeError): pass
        return result

    Rate=pyqtProperty(float,lambda self:1.0,lambda self,value:None)
    MinimumRate=pyqtProperty(float,lambda self:1.0)
    MaximumRate=pyqtProperty(float,lambda self:1.0)
    CanControl=pyqtProperty(bool,lambda self:True)
    CanPlay=pyqtProperty(bool,lambda self:bool(self.window.current or self.window.queue))
    CanPause=pyqtProperty(bool,lambda self:bool(self.window.current))
    CanSeek=pyqtProperty(bool,lambda self:self.window.player.loaded and self.window.player.get('seekable')=='yes')

    @pyqtProperty(bool)
    def CanGoNext(self):
        w=self.window
        return bool(w.queue) and (w.shuffle_mode!='Off' or w.loop_mode=='Playlist' or w.current_index()<len(w.queue)-1)

    @pyqtProperty(bool)
    def CanGoPrevious(self):
        w=self.window
        return bool(w.queue) and (w.current_index()>0 or w.loop_mode=='Playlist' or w.player.number('time-pos')>3)


class Mpris(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window=window
        self.connection_name='firemedia-mpris-'+uuid.uuid4().hex
        self.bus=QDBusConnection.connectToBus(QDBusConnection.BusType.SessionBus,self.connection_name)
        self.service_name=ROOT+'.FireMedia'
        self.available=False
        self.previous={}
        self.last_track=None
        self.last_position=0
        self.root=RootAdaptor(self)
        self.player=PlayerAdaptor(self)
        if not self.bus.isConnected(): return
        if not self.bus.registerService(self.service_name):
            self.service_name+=f'.instance{os.getpid()}_{uuid.uuid4().hex[:8]}'
            if not self.bus.registerService(self.service_name): return
        if not self.bus.registerObject(PATH,self,QDBusConnection.RegisterOption.ExportAdaptors):
            self.bus.unregisterService(self.service_name)
            return
        self.available=True
        window.player.changed.connect(self.refresh)
        window.volume.valueChanged.connect(self.refresh)
        self.refresh()

    def track_id(self):
        if not self.window.current: return NO_TRACK
        return PATH+'/track_'+format(id(self.window.current),'x')

    def refresh(self,*unused):
        if not self.available: return
        keys=['PlaybackStatus','LoopStatus','Shuffle','Volume','Metadata','CanGoNext','CanGoPrevious',
              'CanPlay','CanPause','CanSeek','CanControl']
        values={key:getattr(self.player,key) for key in keys}
        changed={key:value for key,value in values.items() if self.previous.get(key)!=value}
        if changed:
            invalidated=QVariant([]);invalidated.convert(QMetaType(QMetaType.Type.QStringList.value))
            message=QDBusMessage.createSignal(PATH,'org.freedesktop.DBus.Properties','PropertiesChanged')
            message.setArguments([PLAYER,changed,invalidated]);self.bus.send(message)
        track=self.track_id();position=self.player.Position
        if track==self.last_track and abs(position-self.last_position)>1_500_000:
            self.player.Seeked.emit(position)
        self.previous=values;self.last_track=track;self.last_position=position

    def close(self):
        if self.available:
            self.available=False
            self.window.player.changed.disconnect(self.refresh)
            self.window.volume.valueChanged.disconnect(self.refresh)
            self.bus.unregisterObject(PATH)
            self.bus.unregisterService(self.service_name)
        QDBusConnection.disconnectFromBus(self.connection_name)
