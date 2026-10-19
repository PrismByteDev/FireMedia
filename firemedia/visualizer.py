"""Native FFT visualization, with instant-attack bars and ballistic peak caps."""
from collections import deque
from dataclasses import dataclass
import math
import random
import time
import threading
import subprocess
from .runtime import find_tool, subprocess_options
from .visualspec import DEFAULT, visual_spec, sample, color4, gradient_color
from types import SimpleNamespace, MappingProxyType
import base64
from functools import lru_cache
import numpy as np
from PyQt6.QtCore import QObject, QTimer, Qt, QRectF, QLineF, QPointF, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QLinearGradient, QPen, QBrush, QGradient, QPixmap, QImage, QPainterPath, QRadialGradient
from PyQt6.QtWidgets import QWidget

@dataclass
class Bar:
    height: float = 0
    velocity: float = 0
    cap: float = 0
    cap_velocity: float = 0
    collisions: int = 0
    impact: float = 0
    collision_age: float = 100
    launch_ceiling: float = math.inf


def advance_bar(bar, target, dt, tension=140, physics=True, gravity=1800, spring=.45, bounce=True, peak=False, enabled=True, launch_height=120):
    """Instant attack, optional smooth release, and independent ballistic caps."""
    target = max(0, target)
    if dt <= 0:
        return bar
    steps = max(1, math.ceil(dt / (1/120)))
    step = dt / steps
    for _ in range(steps):
        old_height = bar.height
        if target >= bar.height or not physics:
            # Never interpolate upward: every new peak is visible immediately.
            bar.height = target
        else:
            # Exponential release cannot rebound upward or undershoot the target.
            bar.height = target + (bar.height-target) * math.exp(-tension*.045*step)
        bar.velocity = (bar.height-old_height)/step
        if not enabled:continue
        if peak:bar.cap_velocity=min(0,bar.cap_velocity)
        bar.cap_velocity -= gravity * step
        bar.cap += bar.cap_velocity * step
        floor = bar.height + 5
        if bar.cap <= floor:
            impact = max(0, bar.velocity - bar.cap_velocity)
            bar.cap = floor
            if impact > 24:
                bar.collisions+=1;bar.impact=impact
                bar.launch_ceiling=floor+launch_height
                limit=math.sqrt(2*gravity*launch_height) if gravity else launch_height*2
                bar.cap_velocity = 0 if peak or (not bounce and bar.velocity<=0) else min(1600,limit,max(0, bar.velocity) + impact * spring)
            else:
                bar.cap_velocity = max(0, bar.velocity)
        if bar.cap>bar.launch_ceiling and bar.cap>floor:
            bar.cap=max(floor,bar.launch_ceiling);bar.cap_velocity=min(0,bar.cap_velocity)
        bar.cap = max(5, bar.cap)
    return bar


@lru_cache(maxsize=32)
def frequency_edges(size, count):
    return np.geomspace(1, size-1, count+1).astype(int)[:-1]


def frequency_levels(fft, count):
    """Vectorized peak pooling, including repeated low-frequency bin edges."""
    peaks = np.maximum.reduceat(fft, frequency_edges(len(fft), count))
    return np.clip((20*np.log10(np.maximum(peaks, 1e-6))+72)/66, 0, 1).tolist()


class AudioAnalysis(QObject):
    """Decode ahead off the UI thread; sample FFT frames using the media clock.

    Queue capacity is about one second. A full queue backpressures FFmpeg's
    stdout pipe rather than letting a fast decode consume an entire file.
    """
    spectrum = pyqtSignal(object)
    warning = pyqtSignal(str)
    RATE = 22050
    WINDOW = 1024
    HOP = 512
    MAX_FRAMES = 48

    def __init__(self, parent=None):
        super().__init__(parent)
        self.source = ''
        self.gains = [0]*6
        self.enabled = True
        self.ffmpeg = find_tool('ffmpeg')
        self.bar_count = 64
        self.frames = deque()
        self.condition = threading.Condition()
        self.cancel = threading.Event()
        self.process = None
        self.worker = None
        self.last_levels = [0.0]*64
        self.last_waveform = np.zeros(self.WINDOW, dtype=np.float32)
        self.last_timestamp = None
        self.clock_position = 0
        self.clock_time = time.monotonic()
        self.clock_running = False
        self.started_at = time.monotonic()
        self.last_progress = self.started_at

    def set_clock(self, position, running):
        self.clock_position = position
        self.clock_time = time.monotonic()
        self.clock_running = running

    def position(self):
        return self.clock_position + (time.monotonic()-self.clock_time if self.clock_running else 0)

    def start(self, source, position=0, gains=None):
        self.stop()
        self.source = source
        if gains is not None:
            self.gains = list(gains)
        if not self.enabled or not source:
            return
        if not self.ffmpeg:
            self.warning.emit('Install FFmpeg to enable audio-reactive visualization.')
            return
        cancel = self.cancel = threading.Event()
        self.started_at = self.last_progress = time.monotonic()
        args = [self.ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error',
                '-ss', str(max(0,position)), '-i', source, '-vn', '-sn']
        if any(self.gains):
            centers = [60,170,350,1000,3500,10000]
            args += ['-af', ','.join(f'equalizer=f={f}:t=o:w=1:g={float(g):.2f}' for f,g in zip(centers,self.gains))]
        args += ['-ac','1','-ar',str(self.RATE),'-f','f32le','pipe:1']
        self.worker = threading.Thread(target=self.decode, args=(args, position, cancel), daemon=True)
        self.worker.start()

    def decode(self, args, start, cancel):
        process = None
        try:
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **subprocess_options())
            with self.condition:
                if cancel.is_set():
                    return
                self.process = process
            samples = np.zeros(self.WINDOW, dtype=np.float32)
            window = np.hanning(self.WINDOW)
            normalization = window.sum()/2
            total = 0
            while not cancel.is_set():
                with self.condition:
                    self.condition.wait_for(lambda: cancel.is_set() or len(self.frames)<self.MAX_FRAMES)
                if cancel.is_set():
                    break
                data = process.stdout.read(self.HOP*4)
                if not data:
                    break
                values = np.frombuffer(data[:len(data)//4*4], dtype='<f4')
                if not len(values):
                    continue
                samples = np.roll(samples, -len(values))
                samples[-len(values):] = values
                total += len(values)
                fft = np.abs(np.fft.rfft(samples*window))/normalization
                levels = frequency_levels(fft, self.bar_count)
                # A centered FFT window describes this position, not arrival time.
                timestamp = start + max(0,(total-self.WINDOW/2)/self.RATE)
                with self.condition:
                    if not cancel.is_set():
                        self.frames.append((timestamp, levels, np.clip(np.nan_to_num(samples), -1, 1)))
        except (OSError, ValueError):
            if not cancel.is_set():
                self.warning.emit('Audio analysis unavailable; playback continues.')
        finally:
            if process:
                if process.poll() is None:
                    process.kill()
                process.wait()
                process.stdout.close()
            with self.condition:
                if self.cancel is cancel:
                    self.process = None

    def sample(self, position=None):
        position = self.position() if position is None else position
        with self.condition:
            # Drop superseded frames instead of replaying a delayed backlog.
            while self.frames and self.frames[0][0] <= position:
                self.last_timestamp, self.last_levels, self.last_waveform = self.frames.popleft()
                self.last_progress = time.monotonic()
            self.condition.notify_all()
            levels = self.last_levels
        return levels

    def waveform(self):
        # sample() advances both views together; reading PCM never consumes frames.
        with self.condition:
            return self.last_waveform

    def needs_recovery(self, position, duration=0):
        """Recover startup failures/stalled analysis without toggling playback."""
        if not self.enabled or self.cancel.is_set() or not self.source:return False
        if duration and position>=duration-.3:return False
        now=time.monotonic()
        if now-max(self.started_at,self.last_progress)<2.5:return False
        with self.condition:
            # Silence is valid data. Only restart when timestamps stop advancing.
            return not self.frames or self.frames[0][0]>position+.5

    def stop(self):
        self.cancel.set()
        with self.condition:
            process = self.process
            self.process = None
            self.frames.clear()
            self.last_timestamp = None
            self.last_levels = [0.0]*self.bar_count
            self.last_waveform = np.zeros(self.WINDOW, dtype=np.float32)
            self.condition.notify_all()
        # Never wait for a decoder to shut down on the UI thread.
        if process and process.poll() is None:
            try: process.kill()
            except ProcessLookupError: pass

@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    ax: float
    ay: float
    jx: float
    jy: float
    mx: float
    my: float
    lifetime: float
    start_alpha: float
    mid_time: float
    mid_alpha: float
    end_alpha: float
    color: object
    end_color: object
    size: float
    age: float = 0
    channel: int = 0

    @property
    def alpha(self):
        t=min(1,self.age/self.lifetime)
        if self.mid_time>0:
            mid=min(self.lifetime,self.mid_time)
            if self.age<mid:return self.start_alpha+(self.mid_alpha-self.start_alpha)*self.age/mid
            t=(self.age-mid)/max(.001,self.lifetime-mid)
            return self.mid_alpha+(self.end_alpha-self.mid_alpha)*t
        return self.start_alpha+(self.end_alpha-self.start_alpha)*t


class Visualizer(QWidget):
    PARTICLE_LIMITS = {'Low': 100, 'Medium': 400, 'High': 3200, 'Uncapped': None}

    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName('visualizer');self.setMinimumSize(320,180)
        self.bar_count=64;self.bars=[Bar() for _ in range(64)];self.levels=[0.0]*64
        self.low_detail=False;self.physics=True;self.tension=140;self.intensity=70
        self.preset='Default';self.color='Rainbow';self.particles=[];self.fog=[];self.cover=QImage()
        self.particle_limit_mode='Medium';self.particle_limit=400
        self.paused=True;self.has_media=False;self.subtitle='';self.subtitle_style='Glow'
        self.subtitle_size=38;self.subtitle_font='Sans Serif';self.demo=False;self.level_provider=None;self.waveform_provider=None;self.waveform=[]
        self.plugins=None;self.clock=time.monotonic();self.phase=0;self.dt=0
        self._suspended=False;self.geometry_revision=0
        self._images={};self._image_cache={};self._colors={}
        self.configure(DEFAULT)
        self.timer=QTimer(self);self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(16);self.timer.timeout.connect(self.tick);self.timer.start()

    def configure(self,spec):
        self.spec=visual_spec(spec);self._images={};self._image_cache={};self._colors={}
        self.channels=self.spec['channels']
        self.particles=[p for p in self.particles if self.channels[p.channel]['particles_enabled']]
        if not self.spec['fog_enabled']:self.fog.clear()
        self._gradients={key:[(pos,color4(color).getRgbF()) for pos,color in self.spec[key]] for key in ('horizontal','vertical','line_gradient','particle_gradient','background_gradient','wave_gradient')}
        self._channel_gradients=[[(pos,color4(c).getRgbF()) for pos,c in channel['particle_gradient']] for channel in self.channels]
        self._collision_tint=color4(self.spec['collision_color'])
        self._decal_specs={key:self.spec[key] for key in ('bar_decal','line_decal','particle_decal','background_image')}
        self._decal_specs.update({('particle_decal',i):c['particle_decal'] for i,c in enumerate(self.channels)})
        for key,image in self._decal_specs.items():
            if image:
                source=QImage.fromData(base64.b64decode(image['data']))
                l,t,r,b=image['crop'];w,h=source.width(),source.height()
                left=min(w-1,round(l*w));top=min(h-1,round(t*h))
                right=max(left+1,min(w,round((1-r)*w)));bottom=max(top+1,min(h,round((1-b)*h)))
                source=source.copy(left,top,right-left,bottom-top)
                cols,rows,cell=image['columns'],image['rows'],image['cell']
                cw,ch=source.width()/cols,source.height()/rows
                left=min(source.width()-1,round(cell%cols*cw));top=min(source.height()-1,round(cell//cols*ch))
                right=max(left+1,min(source.width(),round((cell%cols+1)*cw)));bottom=max(top+1,min(source.height(),round((cell//cols+1)*ch)))
                source=source.copy(left,top,right-left,bottom-top)
                self._images[key]=source
        self.update()

    def set_levels(self,levels):self.levels=levels
    def set_particle_limit(self,mode):
        if not isinstance(mode,str) or mode not in self.PARTICLE_LIMITS:mode='Medium'
        self.particle_limit_mode=mode;self.particle_limit=self.PARTICLE_LIMITS[mode]
        if self.particle_limit is not None:del self.particles[self.particle_limit:]
        self.update()
    @property
    def effective_bar_count(self):return min(self.bar_count,24) if self.low_detail else self.bar_count
    def set_bar_count(self,count):
        self.bar_count=max(8,min(256,int(count)));self.bars=[Bar() for _ in range(self.bar_count)];self.update()
    def set_quality(self,low):
        self.low_detail=low;self.timer.setInterval(33 if low else 16)
        if low:self.particles.clear();self.fog.clear()
        self.update()
    def suspend(self,enabled):
        changed=bool(enabled)!=self._suspended
        self._suspended=bool(enabled)
        if enabled:
            self.timer.stop();self.particles.clear();self.fog.clear()
            if changed:
                self.geometry_revision+=1
                if self.plugins:self.plugins.invalidate_frame()
        elif not self.timer.isActive():self.clock=time.monotonic();self.timer.start()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if not event.oldSize().isValid() or event.oldSize()==event.size():return
        # Effects use screen coordinates. Discard geometry from the old viewport,
        # including asynchronous mod results that may still be in flight.
        self.geometry_revision+=1;self.particles.clear();self.fog.clear()
        self.bars=[Bar() for _ in range(self.bar_count)];self._image_cache.clear()
        if self.plugins:self.plugins.invalidate_frame()
        self.clock=time.monotonic()

    def frame_snapshot(self):
        n=self.effective_bar_count;slot=(self.width()-30)/n;baseline=self.height()-15
        bars=tuple(MappingProxyType({'index':i,'x':15+(i+.5)*slot,'y':baseline-b.height,
            'height':b.height,'cap_y':baseline-b.cap,'velocity':b.velocity,'cap_velocity':b.cap_velocity,
            'collision_age':b.collision_age}) for i,b in enumerate(self.bars[:n]))
        return SimpleNamespace(width=self.width(),height=self.height(),baseline=baseline,dt=self.dt,
            time=self.phase,levels=tuple(self.levels),bars=bars,paused=self.paused,low_detail=self.low_detail)

    def horizontal_color(self,position,key='horizontal',channel=0):
        if key=='particle_gradient':
            source=self.channels[channel];speed=source['particle_gradient_speed'];offset=source['particle_gradient_offset'];size=source['particle_gradient_size'];stops=self._channel_gradients[channel]
        elif key=='line_gradient':
            speed=self.spec['line_gradient_speed'];offset=self.spec['line_gradient_offset'];size=self.spec['line_gradient_size'];stops=self._gradients[key]
        else:speed=self.spec['speed'];offset=self.spec['offset'];size=self.spec['size'];stops=self._gradients[key]
        t=(position*size+self.phase*speed/360+offset/360)%1
        if t<=stops[0][0]:return QColor.fromRgbF(*stops[0][1])
        for (a,ca),(b,cb) in zip(stops,stops[1:]):
            if t<=b:
                mix=(t-a)/(b-a);return QColor.fromRgbF(*[x+(y-x)*mix for x,y in zip(ca,cb)])
        return QColor.fromRgbF(*stops[-1][1])

    def summon_particle(self,x,y,**options):
        channel=options.pop('channel',1)
        if isinstance(channel,bool) or not isinstance(channel,int) or not 1<=channel<=4:raise ValueError('Particle channel must be 1–4')
        index=channel-1;s=self.channels[index]
        if self.low_detail or self._suspended or self.window().isMinimized() or not s['particles_enabled']:return False
        if self.particle_limit is not None and len(self.particles)>=self.particle_limit:return False
        def get(key,alias=None):
            value=float(sample(options.get(alias or key,s[key])))
            if not math.isfinite(value):raise ValueError('Particle values must be finite')
            return value
        x,y=float(x),float(y)
        if not math.isfinite(x+y):raise ValueError('Particle position must be finite')
        key='particle_gradient' if s['particle_gradient_override'] else 'horizontal'
        color=color4(options['color']) if 'color' in options else self.horizontal_color(max(0,min(1,x/max(1,self.width()))),key,index)
        end=color4(options['end_color']) if 'end_color' in options else color4(s['particle_end_color']) if s['particle_end_override'] else color
        lifetime=max(.02,min(30,get('fade_time','lifetime')))
        p=Particle(x,y,get('start_vx','vx'),get('start_vy','vy'),get('accel_vx','ax'),get('accel_vy','ay'),
            get('cbaccel_vx'),get('cbaccel_vy'),get('expaccel_vx'),get('expaccel_vy'),lifetime,
            1-get('start_transparency')/100,get('mid_time') if s['mid_enabled'] else 0,1-get('mid_transparency')/100,
            1-get('end_transparency')/100,color,end,max(1,min(128,get('particle_size','size'))))
        if not all(math.isfinite(v) for v in p.__dict__.values() if isinstance(v,(float,int))):raise ValueError('Particle values must be finite')
        p.mx=max(0,min(10,p.mx));p.my=max(0,min(10,p.my))
        p.channel=index;self.particles.append(p);return True

    def emit_particles(self,amount,x,y,channel=0):
        amount=max(0,amount)
        if self.particle_limit is not None:amount=min(self.particle_limit-len(self.particles),amount)
        count=int(amount)+(random.random()<amount-int(amount))
        for _ in range(count):self.summon_particle(x,y,channel=channel+1)

    def tick(self):
        if self._suspended or self.window().isMinimized():return
        now=time.monotonic();self.dt=dt=min(.06,max(0,now-self.clock));self.clock=now
        if not self.paused:
            if self.level_provider is not None:self.levels=self.level_provider()
            if self.waveform_provider is not None:self.waveform=self.waveform_provider()
        self.phase+=dt;n=self.effective_bar_count;h=max(1,self.height()-35);s=self.spec
        baseline=self.height()-15;slot=(self.width()-30)/n
        for i in range(n):
            start=i*len(self.levels)//n;end=max(start+1,(i+1)*len(self.levels)//n)
            level=max(self.levels[start:end],default=0) if not self.paused else 0
            if self.demo:level=(.12+.5*(math.sin(i*.55+self.phase*2)+1)/2)*math.sin(math.pi*(i+.5)/n)
            bar=self.bars[i];previous=bar.collisions;bar.collision_age+=dt
            advance_bar(bar,level*h*.82,dt,self.tension,self.physics,s['gravity'],s['spring'],s['bounce'],s['peak'],s['line_enabled'],s['launch_height'])
            x=15+(i+.5)*slot;y=baseline-bar.cap
            if bar.collisions!=previous:
                bar.collision_age=0
                if not self.paused or self.demo:
                    if self.plugins:self.plugins.emit_event('onBarCollision',index=i,x=x,y=y,impact=bar.impact,height=bar.height)
                    if not self.low_detail:
                        for ci,ch in enumerate(self.channels):
                            if ch['particles_enabled']:self.emit_particles(sample(ch['collision_emission']),x,y,ci)
                        if s['fog_enabled']:self.spawn_fog(x)
            if not self.low_detail and level>.12:
                for ci,ch in enumerate(self.channels):
                    if ch['particles_enabled']:self.emit_particles(dt*sample(ch['emission_rate']),x,y,ci)
        for p in self.particles:
            p.age+=dt;p.ax=(p.ax+p.jx*dt)*p.mx**dt;p.ay=(p.ay+p.jy*dt)*p.my**dt
            p.ax=max(-100000,min(100000,p.ax));p.ay=max(-100000,min(100000,p.ay))
            p.vx+=p.ax*dt;p.vy+=p.ay*dt;p.x+=p.vx*dt;p.y-=p.vy*dt
        self.particles=[p for p in self.particles if p.age<p.lifetime and abs(p.x)<100000 and abs(p.y)<100000]
        for puff in self.fog:puff['age']+=dt;puff['x']+=puff['vx']*dt;puff['y']-=puff['rise']*dt
        self.fog=[p for p in self.fog if p['age']<p['life']]
        if self.plugins:self.plugins.update_frame(self.frame_snapshot())
        self.update()

    def collision_opacity(self,bar,prefix):
        normal=self.spec[prefix+'_transparency'];hit=self.spec[prefix+'_collision_transparency'];duration=self.spec[prefix+'_collision_fade']
        t=max(0,1-bar.collision_age/duration) if duration else 0
        return max(0,min(1,1-(normal+(hit-normal)*t)/100)),t

    def draw_decal(self,painter,key,rect,tint=None):
        if key not in self._images:return
        spec=self._decal_specs[key];image=self._images[key]
        painter.save();painter.setClipRect(rect)
        cw,ch=rect.width()/spec['repeat_x'],rect.height()/spec['repeat_y']
        # Scale once per target size; bound the texture cache as bar heights change.
        cachekey=(key,max(1,round(cw)),max(1,round(ch)))
        if cachekey not in self._image_cache:
            mode={'fit':Qt.AspectRatioMode.KeepAspectRatio,'scale':Qt.AspectRatioMode.KeepAspectRatioByExpanding,'stretch':Qt.AspectRatioMode.IgnoreAspectRatio}[spec['mode']]
            self._image_cache[cachekey]=image.scaled(cachekey[1],cachekey[2],mode,Qt.TransformationMode.SmoothTransformation)
            if len(self._image_cache)>256:self._image_cache.pop(next(iter(self._image_cache)))
        scaled=self._image_cache[cachekey]
        if tint is not None:
            scaled=scaled.copy();overlay=QPainter(scaled);overlay.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
            overlay.fillRect(scaled.rect(),tint);overlay.end()
        for x in range(spec['repeat_x']):
            for y in range(spec['repeat_y']):
                cell=QRectF(rect.x()+x*cw,rect.y()+y*ch,cw,ch)
                painter.save();painter.setClipRect(cell,Qt.ClipOperation.IntersectClip)
                painter.drawImage(QPointF(cell.center().x()-scaled.width()/2,cell.center().y()-scaled.height()/2),scaled);painter.restore()
        painter.restore()

    def set_cover(self,image):
        self.cover=QImage(image);self._cover_cache=None;self.update()

    def draw_cover(self,painter):
        if self.cover.isNull():return
        key=(self.width(),self.height(),self.spec['cover_mode'])
        if getattr(self,'_cover_cache',None) is None or self._cover_cache[0]!=key:
            mode={'fit':Qt.AspectRatioMode.KeepAspectRatio,'scale':Qt.AspectRatioMode.KeepAspectRatioByExpanding,'stretch':Qt.AspectRatioMode.IgnoreAspectRatio}[key[2]]
            self._cover_cache=(key,self.cover.scaled(self.size(),mode,Qt.TransformationMode.SmoothTransformation))
        image=self._cover_cache[1];painter.drawImage(QPointF((self.width()-image.width())/2,(self.height()-image.height())/2),image)

    def spawn_fog(self,x):
        if self.low_detail or not self.spec['fog_enabled']:return
        amount=sample(self.spec['fog_emission']);count=int(amount)+(random.random()<amount-int(amount))
        for _ in range(min(count,max(0,96-len(self.fog)))):
            self.fog.append({'x':x+random.uniform(-12,12),'y':self.height()-5,'vx':random.uniform(-12,12),'rise':sample(self.spec['fog_rise']),
                'radius':sample(self.spec['fog_radius']),'life':sample(self.spec['fog_lifetime']),'age':0})

    def draw_fog(self,painter):
        base=color4(self.spec['fog_color']);painter.save();painter.setPen(Qt.PenStyle.NoPen)
        for puff in self.fog:
            t=puff['age']/puff['life'];radius=puff['radius']*(.6+.7*t);color=QColor(base);color.setAlphaF(base.alphaF()*math.sin(math.pi*t)*.55)
            g=QRadialGradient(puff['x'],puff['y'],radius);g.setColorAt(0,color);edge=QColor(color);edge.setAlpha(0);g.setColorAt(1,edge)
            painter.setBrush(g);painter.drawEllipse(QRectF(puff['x']-radius,puff['y']-radius,radius*2,radius*2))
        painter.restore()

    def draw_wave(self,painter):
        """An oscilloscope trace of decoded PCM, underneath bars; never a filled wave."""
        s=self.spec;w,h=self.width(),self.height()
        count=max(2,round(AudioAnalysis.RATE*s['wave_window']/1000))
        start=max(0,(len(self.waveform)-count)//2);values=self.waveform[start:start+count]
        if len(values)<2:values=(0,0)
        amplitude=h*s['wave_height']/100;center=h*s['wave_position']/100
        path=QPainterPath()
        for i,value in enumerate(values):
            x=i/(len(values)-1)*w;y=center-max(-1,min(1,float(value)))*amplitude
            if i==0:path.moveTo(x,y)
            else:path.lineTo(x,y)
        painter.save();painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(Qt.BrushStyle.NoBrush);painter.setOpacity(1-s['wave_transparency']/100)
        if s['wave_mode']=='solid':brush=QBrush(color4(s['wave_color']))
        else:
            length=w/s['wave_size'];shift=(self.phase*s['wave_speed']/360+s['wave_offset']/360)*length
            g=QLinearGradient(-shift,0,length-shift,0);g.setSpread(QGradient.Spread.RepeatSpread)
            for pos,c in s['wave_gradient']:g.setColorAt(pos,color4(c))
            brush=QBrush(g)
        painter.setPen(QPen(brush,s['wave_line_width']));painter.drawPath(path);painter.restore()

    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),QColor('#000000'));painter.setPen(Qt.PenStyle.NoPen)
        w,h=self.width(),self.height();baseline=h-15;n=self.effective_bar_count;slot=(w-30)/n;s=self.spec
        painter.setOpacity(1-s['background_transparency']/100)
        if s['background_mode']=='color':painter.fillRect(self.rect(),color4(s['background_color']))
        elif s['background_mode']=='gradient':
            angle=math.radians(s['background_angle']+self.phase*s['background_speed']);dx=math.cos(angle)*w/(2*s['background_size']);dy=math.sin(angle)*h/(2*s['background_size'])
            bg=QLinearGradient(w/2-dx,h/2-dy,w/2+dx,h/2+dy);bg.setSpread(QGradient.Spread.RepeatSpread)
            for pos,color in s['background_gradient']:bg.setColorAt(pos,color4(color))
            painter.fillRect(self.rect(),bg)
        elif s['background_mode']=='image':self.draw_decal(painter,'background_image',QRectF(self.rect()))
        elif s['background_mode']=='cover':self.draw_cover(painter)
        painter.setOpacity(1)
        custom=bool(self.plugins and self.plugins.selected in dict(self.plugins.choices()))
        if not self.low_detail:
            painter.setPen(QPen(QColor(140,150,180,16),1));painter.drawLines([QLineF(15+i*slot/2,0,15+i*slot/2,baseline) for i in range(n*2)]);painter.setPen(Qt.PenStyle.NoPen)
        if s['wave_enabled']:self.draw_wave(painter)
        if not custom:
            for i,bar in enumerate(self.bars[:n]):
                width=max(.5,slot*s['bar_width']/100-s['bar_padding']);x=15+i*slot+(slot-width)/2
                color=self.horizontal_color(i/max(1,n-1));opacity,flash=self.collision_opacity(bar,'bar')
                if s['collision_tint'] and flash:
                    tint=self._collision_tint;mix=flash*tint.alphaF()
                    color=QColor.fromRgbF(*[a+(b-a)*mix for a,b in zip(color.getRgbF()[:3],tint.getRgbF()[:3])],color.alphaF())
                gradient=QLinearGradient(0,0,0,1);gradient.setCoordinateMode(QGradient.CoordinateMode.ObjectBoundingMode)
                for pos,v in self._gradients['vertical']:
                    gradient.setColorAt(pos,QColor.fromRgbF(color.redF()*v[0],color.greenF()*v[1],color.blueF()*v[2],color.alphaF()*v[3]))
                rect=QRectF(x,baseline-bar.height,width,max(.5,bar.height))
                if s['bars_visible']:
                    painter.setOpacity(opacity);painter.setBrush(QBrush(gradient));painter.drawRect(rect);self.draw_decal(painter,'bar_decal',rect)
                if s['line_enabled'] and s['line_visible']:
                    painter.setOpacity(self.collision_opacity(bar,'line')[0])
                    linecolor=self.horizontal_color(i/max(1,n-1),'line_gradient') if s['line_gradient_override'] else color.lighter(135)
                    lw=width*s['line_width']/100;rect=QRectF(x+(width-lw)/2,baseline-bar.cap-s['line_height'],lw,s['line_height'])
                    painter.fillRect(rect,linecolor);self.draw_decal(painter,'line_decal',rect)
        painter.setOpacity(1)
        if self.plugins:self.plugins.draw_frame(painter,self.frame_snapshot())
        if not self.low_detail and s['fog_enabled']:self.draw_fog(painter)
        if not self.low_detail:
            for particle in self.particles:
                t=min(1,particle.age/particle.lifetime);a=particle.color;b=particle.end_color
                color=QColor.fromRgbF(*[x+(y-x)*t for x,y in zip(a.getRgbF()[:3],b.getRgbF()[:3])],max(0,min(1,particle.alpha*(a.alphaF()+(b.alphaF()-a.alphaF())*t))))
                channel=self.channels[particle.channel];decal=('particle_decal',particle.channel)
                if decal in self._images:
                    tint=None
                    if channel['particle_gradient_override']:tint=QColor(color);tint.setAlpha(255)
                    elif channel['particle_end_override']:tint=QColor(particle.end_color);tint.setAlphaF(t)
                    painter.setOpacity(color.alphaF());size=particle.size;self.draw_decal(painter,decal,QRectF(particle.x-size/2,particle.y-size/2,size,size),tint);painter.setOpacity(1)
                else:
                    painter.setPen(QPen(color,1));size=max(1,particle.size*.35)
                    painter.drawLine(QPointF(particle.x-size,particle.y),QPointF(particle.x+size,particle.y));painter.drawLine(QPointF(particle.x,particle.y-size),QPointF(particle.x,particle.y+size))
            painter.setPen(Qt.PenStyle.NoPen)
        if not self.has_media and not self.demo:
            painter.setPen(QColor('#bcbcc4'));font=painter.font();font.setPointSize(14);painter.setFont(font)
            painter.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'Drop media or a playlist\nCtrl+O to open files')
        painter.end()
