"""Restricted Python mods: asynchronous JSON IPC, validated native drawing."""
from dataclasses import dataclass, field
from collections import deque
import hashlib
import base64
import math
import sys
import json
from pathlib import Path, PurePosixPath
import re
import time
from types import MappingProxyType, SimpleNamespace
from zipfile import ZipFile, BadZipFile
from PyQt6.QtCore import QObject, pyqtSignal, QRectF, QPointF, Qt, QProcess, QProcessEnvironment, QTimer, QBuffer, QByteArray, QIODevice
from PyQt6.QtGui import QPen, QFont, QImage, QImageReader
from .visualspec import color4

EVENTS={'onLoad','onUnload','update','draw','onBarCollision','onSubtitleLoad','onSubtitleMessage','onTrackLoad','onPlaybackState'}


def read_package(path):
    """Read without extracting; reject ambiguous or oversized packages."""
    path=Path(path)
    if path.stat().st_size>16*1024*1024:raise ValueError('Plugin package exceeds 16 MB')
    try:
        with ZipFile(path) as archive:
            infos=archive.infolist()
            if len(infos)>128 or sum(i.file_size for i in infos)>32*1024*1024:raise ValueError('Plugin package expands beyond its limit')
            files={}
            for item in infos:
                name=item.filename
                if '\\' in name or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts or name in files:
                    raise ValueError('Invalid or duplicate package path')
                if item.is_dir():continue
                files[name]=archive.read(item)
    except (BadZipFile,RuntimeError,NotImplementedError) as error:raise ValueError('Could not read the .firemp ZIP script package') from error
    try:manifest=json.loads(files['manifest.json'])
    except (KeyError,ValueError,UnicodeError,RecursionError) as error:raise ValueError('Missing or invalid manifest.json') from error
    if not isinstance(manifest,dict) or manifest.get('format')!='FireMediaPlugin' or type(manifest.get('api')) is not int or manifest.get('api')!=1:raise ValueError('Unsupported plugin format or API')
    if not isinstance(manifest.get('id'),str) or not re.fullmatch(r'[a-z][a-z0-9_.-]{1,63}',manifest['id']):raise ValueError('Invalid plugin ID')
    for key in ('name','version'):
        if not isinstance(manifest.get(key),str) or not 0<len(manifest[key])<=128:raise ValueError(f'Invalid plugin {key}')
    entry=manifest.get('entry','plugin.py')
    if not isinstance(entry,str) or entry not in files or not entry.endswith('.py'):raise ValueError('Missing Python entry script')
    if len(files[entry])>256*1024:raise ValueError('Entry script exceeds 256 KB')
    compile(files[entry],f'{path.name}/{entry}','exec')
    return manifest,files


@dataclass
class LoadedPlugin:
    manifest: dict
    files: dict
    active: bool=False
    error: str=''
    digest: str=''
    process: object=None
    timer: object=None
    buffer: bytes=b''
    pending: object=field(default_factory=deque)
    frame: object=None
    busy: bool=False
    sent_frame: bool=False
    geometry_revision: int=0
    ready: bool=False
    visualizers: dict=field(default_factory=dict)
    commands: list=field(default_factory=list)
    images: dict=field(default_factory=dict)


class Drawing:
    """Pixel-based QPainter facade; origin top-left. Valid only during draw."""
    def __init__(self,painter,frame):self._painter=painter;self.frame=frame;self._valid=True
    def _check(self):
        if not self._valid:raise RuntimeError('Drawing context is only valid inside draw')
    def rect(self,x,y,width,height,color='#FFFFFF',radius=0):
        self._check();p=self._painter;p.setPen(Qt.PenStyle.NoPen);p.setBrush(color4(color))
        p.drawRoundedRect(QRectF(x,y,width,height),radius,radius)
    def ellipse(self,x,y,width,height,color='#FFFFFF'):
        self._check();p=self._painter;p.setPen(Qt.PenStyle.NoPen);p.setBrush(color4(color));p.drawEllipse(QRectF(x,y,width,height))
    def line(self,x1,y1,x2,y2,color='#FFFFFF',width=1):
        self._check();self._painter.setPen(QPen(color4(color),width));self._painter.drawLine(QPointF(x1,y1),QPointF(x2,y2))
    def text(self,x,y,text,color='#FFFFFF',size=16):
        self._check();p=self._painter;p.setPen(color4(color));font=QFont();font.setPixelSize(round(size));p.setFont(font);p.drawText(QPointF(x,y),str(text))
    def image(self,image,x,y,width,height):
        self._check();self._painter.drawImage(QRectF(x,y,width,height),image)


class PluginManager(QObject):
    changed=pyqtSignal()
    warning=pyqtSignal(str)
    def __init__(self,visual,directory,parent=None):
        super().__init__(parent);self.visual=visual;self.directory=Path(directory);self.plugins={};self.messages=deque(maxlen=100);self.selected=''
    def record(self,id,message):self.messages.append(f'{id}: {message[:2048]}')
    def install(self,path):
        manifest,files=read_package(path);id=manifest['id']
        if id in self.plugins:raise ValueError('Remove the installed plugin before installing another version')
        self.directory.mkdir(parents=True,exist_ok=True);target=self.directory/(id+'.firemp');target.write_bytes(Path(path).read_bytes())
        self.plugins[id]=LoadedPlugin(manifest,files,digest=self.fingerprint(id));self.changed.emit();return id
    def discover(self):
        if not self.directory.is_dir():return
        for path in sorted(self.directory.glob('*.firemp')):
            try:
                manifest,files=read_package(path)
                if path.stem!=manifest['id']:raise ValueError('Package filename and ID do not match')
                self.plugins[manifest['id']]=LoadedPlugin(manifest,files,digest=hashlib.sha256(path.read_bytes()).hexdigest())
            except (OSError,ValueError,SyntaxError) as error:self.record(path.name,str(error))
    def fingerprint(self,id):return hashlib.sha256((self.directory/(id+'.firemp')).read_bytes()).hexdigest()
    def enable(self,id):
        p=self.plugins[id]
        if p.active:return
        if sum(plugin.active for plugin in self.plugins.values())>=8:
            self._fail(p,'At most eight mods can run at once.');return
        if not sys.platform.startswith('linux'):
            self._fail(p,'Restricted mods currently require Linux; unrestricted execution is disabled.');return
        try:
            digest=self.fingerprint(id)
            if digest!=p.digest:
                manifest,files=read_package(self.directory/(id+'.firemp'))
                if manifest['id']!=id:raise ValueError('Changed package ID does not match')
                p.manifest=manifest;p.files=files;p.digest=digest
        except (OSError,ValueError,SyntaxError) as error:self._fail(p,str(error));return
        p.error='';p.active=True;p.ready=False;p.busy=True;p.buffer=b'';p.commands=[];p.pending.clear();p.visualizers={};p.images={}
        process=p.process=QProcess(self);environment=QProcessEnvironment()
        environment.insert('PATH','/usr/bin:/bin');environment.insert('LANG','C.UTF-8')
        process.setProcessEnvironment(environment);process.setWorkingDirectory('/')
        process.setProgram(sys.executable if not getattr(sys,'frozen',False) else '/usr/bin/python3')
        process.setArguments(['-I','-S',str(Path(__file__).with_name('mod_worker.py'))])
        timer=p.timer=QTimer(self);timer.setSingleShot(True);timer.timeout.connect(lambda:self._fail(p,'Mod response timed out; worker stopped.'))
        process.readyReadStandardOutput.connect(lambda:self._read(p))
        process.readyReadStandardError.connect(lambda:self._stderr(p))
        process.errorOccurred.connect(lambda error:self._fail(p,'Could not start restricted worker.') if p.active else None)
        process.finished.connect(lambda *args:self._fail(p,'Restricted worker exited.') if p.active else None)
        process.started.connect(lambda:self._initialize(p));process.start();timer.start(2500);self.changed.emit()
    def _initialize(self,p):
        if not p.active or p.process is None:return
        data={'entry':p.manifest.get('entry','plugin.py'),'files':{k:base64.b64encode(v).decode() for k,v in p.files.items()}}
        p.process.write(json.dumps(data,separators=(',',':')).encode()+b'\n')
    def _stderr(self,p):
        if not p.active:return
        data=bytes(p.process.readAllStandardError())
        if len(data)>65536:self._fail(p,'Mod diagnostic output exceeds its limit.')
    def _read(self,p):
        if not p.active:return
        p.buffer+=bytes(p.process.readAllStandardOutput())
        if len(p.buffer)>1024*1024:self._fail(p,'Mod output exceeds 1 MB.');return
        while b'\n' in p.buffer and p.active:
            line,p.buffer=p.buffer.split(b'\n',1)
            try:
                message=json.loads(line)
                if not isinstance(message,dict):raise ValueError('Invalid worker response')
                if 'error' in message:raise ValueError(str(message['error'])[:1024])
                commands=message.get('commands',[]);logs=message.get('logs',[]);particles=message.get('particles',[]);renderers=message.get('visualizers',[])
                if not isinstance(commands,list) or len(commands)>1024 or not isinstance(logs,list) or len(logs)>32 or not isinstance(particles,list) or len(particles)>400 or not isinstance(renderers,list) or len(renderers)>32:raise ValueError('Worker response exceeds API limits')
                choices={}
                for pair in renderers:
                    if not isinstance(pair,list) or len(pair)!=2 or not isinstance(pair[0],str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}',pair[0]) or not isinstance(pair[1],str) or len(pair[1])>128:raise ValueError('Invalid renderer')
                    choices[pair[0]]=pair[1]
                changed=not p.ready or p.visualizers!=choices
                p.ready=True;p.visualizers=choices
                if self.selected.startswith(p.manifest['id']+':') and self.selected.partition(':')[2] not in choices:self.selected=''
                for command in commands:self._validate_command(command)
                current_geometry=p.geometry_revision==self.visual.geometry_revision and not self.visual._suspended and not self.visual.window().isMinimized()
                if p.sent_frame and current_geometry:p.commands=commands
                for log in logs:
                    if not isinstance(log,str):raise ValueError('Invalid log')
                    self.record(p.manifest['id'],log[:2048])
                for particle in particles:
                    if not isinstance(particle,list) or len(particle)!=3 or not isinstance(particle[2],dict) or len(particle[2])>24:raise ValueError('Invalid particle request')
                    self._finite(particle[0]);self._finite(particle[1])
                    allowed={'color','end_color','vx','vy','ax','ay','cbaccel_vx','cbaccel_vy','expaccel_vx','expaccel_vy','lifetime','size','start_transparency','mid_transparency','end_transparency','mid_time','channel'}
                    if set(particle[2])-allowed:raise ValueError('Unsupported particle option')
                    if current_geometry:self.visual.summon_particle(*particle[:2],**particle[2])
                p.busy=False;p.timer.stop()
                if changed:self.changed.emit()
                self.visual.update();self._flush(p)
            except (ValueError,TypeError,KeyError,OverflowError) as error:self._fail(p,str(error))
    def _finite(self,value,lo=-100000,hi=100000):
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not lo<=value<=hi:raise ValueError('Invalid drawing number')
    def _validate_command(self,c):
        counts={'rect':7,'ellipse':6,'line':7,'text':6,'image':6}
        if not isinstance(c,list) or not c or c[0] not in counts or len(c)!=counts[c[0]]:raise ValueError('Invalid drawing command')
        if c[0] in ('rect','ellipse','line'):
            for x in c[1:5]:self._finite(x)
            color4(c[5])
            if c[0] in ('rect','line'):self._finite(c[6],0,1000 if c[0]=='rect' else 50)
        elif c[0]=='text':
            self._finite(c[1]);self._finite(c[2]);color4(c[4]);self._finite(c[5],1,144)
            if not isinstance(c[3],str) or len(c[3])>1024:raise ValueError('Invalid text')
        elif c[0]=='image':
            if not isinstance(c[1],str) or len(c[1])>256:raise ValueError('Invalid image reference')
            for x in c[2:]:self._finite(x)
    def _flush(self,p):
        if self.visual._suspended or self.visual.window().isMinimized():p.frame=None
        if not p.active or not p.ready or p.busy or (not p.pending and p.frame is None):return
        events=list(p.pending);p.pending.clear();frame=p.frame;p.frame=None
        selected=self.selected.partition(':')[2] if self.selected.startswith(p.manifest['id']+':') else ''
        packet=json.dumps({'events':events,'frame':frame,'selected':selected},allow_nan=False,separators=(',',':')).encode()+b'\n'
        if len(packet)>1024*1024:self._fail(p,'Event packet exceeds 1 MB');return
        p.busy=True;p.process.write(packet);p.timer.start(200)
        p.sent_frame=frame is not None
        p.geometry_revision=self.visual.geometry_revision
    def disable(self,id):
        p=self.plugins[id];idle=p.ready and not p.busy;p.active=False;p.ready=False
        if p.timer:p.timer.stop();p.timer.deleteLater();p.timer=None
        if p.process:
            if idle:
                p.process.write(b'{"events":[["onUnload",{}]],"frame":null}\n');p.process.waitForReadyRead(30)
            p.process.kill();p.process.waitForFinished(100);p.process.deleteLater();p.process=None
        p.commands=[];p.pending.clear()
        if self.selected.startswith(id+':'):self.selected=''
        self.changed.emit()
    def remove(self,id):
        self.disable(id);(self.directory/(id+'.firemp')).unlink(missing_ok=True);del self.plugins[id];self.changed.emit()
    def _fail(self,p,error):
        p.error=str(error);self.record(p.manifest['id'],p.error);self.disable(p.manifest['id'])
        self.warning.emit(f"Plugin {p.manifest['name']} disabled: {p.error}")
    def emit_event(self,name,**values):
        for p in tuple(self.plugins.values()):
            if p.active:
                if len(p.pending)>=256:self._fail(p,'Mod event queue overflow');continue
                p.pending.append((name,values));QTimer.singleShot(0,lambda plugin=p:self._flush(plugin))
    def choices(self):return [(id+':'+key,label) for id,p in self.plugins.items() if p.active and p.ready for key,label in p.visualizers.items()]
    def invalidate_frame(self):
        for p in self.plugins.values():
            p.commands=[];p.frame=None
            p.pending=deque((name,value) for name,value in p.pending if name!='onBarCollision')
    def update_frame(self,frame):
        if self.visual._suspended or self.visual.window().isMinimized():return
        data=vars(frame).copy();data['bars']=[dict(b) for b in frame.bars];data['levels']=list(frame.levels)
        for p in tuple(self.plugins.values()):
            if p.active:p.frame=data;self._flush(p)
    def draw_frame(self,painter,frame):
        started=time.monotonic()
        for p in tuple(self.plugins.values()):
            if not p.active:continue
            painter.save();context=Drawing(painter,frame)
            try:
                for c in p.commands:
                    if time.monotonic()-started>.012:raise ValueError('Drawing budget exceeded')
                    if c[0]=='image':
                        name=c[1]
                        if name not in p.images:
                            raw=p.files.get(name,b'')
                            if len(raw)>4*1024*1024:raise ValueError('Image exceeds 4 MB')
                            fmt=b'png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else b'jpeg' if raw.startswith(b'\xff\xd8\xff') else b'webp' if raw.startswith(b'RIFF') and raw[8:12]==b'WEBP' else b'bmp' if raw.startswith(b'BM') else None
                            if fmt is None:raise ValueError('Mod images must be raster PNG, JPEG, WebP, or BMP; SVG/external references are blocked.')
                            buffer=QBuffer();buffer.setData(QByteArray(raw));buffer.open(QIODevice.OpenModeFlag.ReadOnly);reader=QImageReader(buffer,fmt);size=reader.size()
                            if not size.isValid() or size.width()*size.height()>4_194_304:raise ValueError('Image exceeds 4 megapixels')
                            image=reader.read()
                            if image.isNull():raise ValueError('Invalid packaged image')
                            p.images[name]=image
                        context.image(p.images[name],*c[2:])
                    else:getattr(context,c[0])(*c[1:])
            except (ValueError,TypeError,OverflowError) as error:self._fail(p,str(error))
            finally:context._valid=False;painter.restore()
        return bool(self.selected)
    def enabled_state(self):return {id:p.digest for id,p in self.plugins.items() if p.active and p.ready}
    def close(self):
        for id in tuple(self.plugins):self.disable(id)
