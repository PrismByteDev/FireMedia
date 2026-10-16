"""Portable visualizer presets: validated settings, RGBA colors, embedded images."""
from copy import deepcopy
import base64
import json
import math
import random
import re
from pathlib import Path
from PyQt6.QtCore import QBuffer, QIODevice, Qt
from PyQt6.QtGui import QColor, QImage, QImageReader
from .playlists import save_state


def color4(value):
    """CSS-order hex (#RRGGBBAA), RGBA bytes, or hsv(H,S%,V%[,A%])."""
    if isinstance(value,(list,tuple)) and len(value) in (3,4):
        values=[number(x,0,255) for x in value]
        return QColor(*[round(x) for x in values])
    if not isinstance(value,str):raise ValueError('Use a hex, RGBA, or HSV color')
    value=value.strip()
    if re.fullmatch(r'#[\da-fA-F]{6}([\da-fA-F]{2})?',value):
        parts=[int(value[i:i+2],16) for i in range(1,len(value),2)]
        return QColor(*parts)
    match=re.fullmatch(r'hsv\(\s*([\d.]+)\s*,\s*([\d.]+)%?\s*,\s*([\d.]+)%?(?:\s*,\s*([\d.]+)%?)?\s*\)',value,re.I)
    if match:
        h,s,v,a=match.groups();return QColor.fromHsvF(number(float(h),0,360)%360/360,number(float(s),0,100)/100,number(float(v),0,100)/100,number(float(a or 100),0,100)/100)
    raise ValueError('Use #RRGGBB, #RRGGBBAA, RGBA bytes, or hsv(H,S,V,A)')


def hex_color(value):
    c=color4(value) if not isinstance(value,QColor) else value
    return f'#{c.red():02X}{c.green():02X}{c.blue():02X}{c.alpha():02X}'


def number(value,lo,hi):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not lo<=value<=hi:
        raise ValueError(f'Expected a finite number between {lo} and {hi}')
    return value


def soft(value,lo,hi):
    if isinstance(value,(list,tuple)):
        if len(value)!=2:raise ValueError('A range needs two numbers')
        a,b=[number(x,lo,hi) for x in value]
        if a>b:raise ValueError('Range minimum exceeds maximum')
        return [a,b]
    return number(value,lo,hi)


def sample(value):return random.uniform(*value) if isinstance(value,(list,tuple)) else value

PALETTES={
 'Rainbow':[[0/6,'#FF0000FF'],[1/6,'#FFFF00FF'],[2/6,'#00FF00FF'],[3/6,'#00FFFFFF'],[4/6,'#0000FFFF'],[5/6,'#FF00FFFF'],[6/6,'#FF0000FF']],
 'Frost':[[0,'#EAFBFF'],[.15,'#7FECFF'],[.35,'#428CFF'],[.5,'#C4D5FF'],[.65,'#428CFF'],[.85,'#7FECFF'],[1,'#EAFBFF']],
 'Amethyst':[[0,'#EFC8FF'],[.175,'#B966FF'],[.35,'#6531C7'],[.5,'#EE80CB'],[.65,'#6531C7'],[.825,'#B966FF'],[1,'#EFC8FF']],
 'Ember':[[0,'#FFE498'],[.15,'#FFB12A'],[.325,'#FF571F'],[.5,'#A81135'],[.675,'#FF571F'],[.85,'#FFB12A'],[1,'#FFE498']],
 'White':[[0,'#FFFFFF'],[1,'#FFFFFF']]}


def gradient(value):
    if not isinstance(value,list) or not 2<=len(value)<=16:raise ValueError('Gradients need 2–16 stops')
    result=[]
    for stop in value:
        if not isinstance(stop,(list,tuple)) or len(stop)!=2:raise ValueError('Invalid gradient stop')
        result.append([number(stop[0],0,1),hex_color(stop[1])])
    result.sort(key=lambda s:s[0])
    if len(set(s[0] for s in result))!=len(result):raise ValueError('Gradient positions must be different')
    return result


def gradient_color(stops,position):
    position=max(0,min(1,position))
    if position<=stops[0][0]:return color4(stops[0][1])
    for (a,ca),(b,cb) in zip(stops,stops[1:]):
        if position<=b:
            ca,cb=color4(ca),color4(cb);t=(position-a)/(b-a)
            return QColor.fromRgbF(*[x+(y-x)*t for x,y in zip(ca.getRgbF(),cb.getRgbF())])
    return color4(stops[-1][1])

# key, label, type, default, minimum, maximum. Units are shown in the editor.
FIELDS={
 'Background':[
 ('background_mode','Background','choice','color',['off','color','gradient','image','cover'],None),
 ('cover_mode','Song cover image mode','choice','scale',['fit','scale','stretch'],None),
 ('background_color','Background color (RGBA)','color','#050507FF',0,1),
 ('background_gradient','Background gradient','gradient',PALETTES['Frost'],0,1),
 ('background_angle','Gradient angle (°)','number',90,-360,360),
 ('background_speed','Gradient rotation (°/s)','number',0,-360,360),
 ('background_size','Gradient size (×)','number',1,.1,16),
 ('background_transparency','Background transparency (%)','number',0,0,100),
 ('background_image','Background image','image',None,0,1)],
 'Gradient settings':[
 ('horizontal','Horizontal gradient','gradient',PALETTES['Rainbow'],0,1),
 ('speed','Horizontal speed (°/s)','number',36,-720,720),
 ('size','Horizontal gradient size (×)','number',1,.1,16),
 ('offset','Horizontal offset (°)','number',0,-3600,3600),
 ('vertical','Vertical gradient · multiplied','gradient',[[0,'#FFFFFFFF'],[1,'#80808080']],0,1)],
 'Wave':[
 ('wave_enabled','Wave enabled','bool',False,0,1),
 ('wave_mode','Wave color mode','choice','solid',['solid','gradient'],None),
 ('wave_color','Wave color (RGBA)','color','#FFFFFF33',0,1),
 ('wave_gradient','Wave gradient','gradient',PALETTES['Frost'],0,1),
 ('wave_speed','Gradient speed (°/s)','number',36,-720,720),
 ('wave_offset','Gradient offset (°)','number',0,-3600,3600),
 ('wave_size','Gradient size (×)','number',1,.1,16),
 ('wave_height','Wave height (% of screen)','number',12,0,60),
 ('wave_window','Audio window (ms)','number',20,1,46),
 ('wave_position','Vertical position (%)','number',50,0,100),
 ('wave_line_width','Trace width (px)','number',1.5,.5,8),
 ('wave_transparency','Wave transparency (%)','number',0,0,100)],
 'Fog':[
 ('fog_enabled','Collision fog enabled','bool',False,0,1),
 ('fog_color','Fog color (RGBA)','color','#E6EDFF70',0,1),
 ('fog_emission','Fog puffs per collision','soft',[1,2],0,10),
 ('fog_lifetime','Fog lifetime (s)','soft',[3,6],.2,20),
 ('fog_radius','Fog radius (px)','soft',[50,110],5,250),
 ('fog_rise','Fog rise (px/s)','soft',[3,10],0,100)],
 'Bar settings':[
 ('bars_visible','Bars visible','bool',True,0,1),
 ('bar_width','Bar width (% of slot)','number',100,1,200),
 ('bar_padding','Bar padding (px)','number',2,0,100),
 ('bar_transparency','Bar transparency (%)','number',0,0,100),
 ('bar_collision_transparency','Collision transparency (%)','number',0,0,100),
 ('bar_collision_fade','Collision fade time (s)','number',.25,0,10),
 ('collision_tint','Enable collision tint','bool',False,0,1),
 ('collision_color','Collision tint (RGBA)','color','#FFFFFF90',0,1),
 ('bar_decal','Bar decal','image',None,0,1)],
 'Barline settings':[
 ('line_enabled','Barline enabled','bool',True,0,1),
 ('line_width','Barline width (% of bar)','number',100,1,300),
 ('line_height','Barline height (px)','number',3,.5,80),
 ('line_decal','Barline decal','image',None,0,1),
 ('line_visible','Barline visible','bool',True,0,1),
 ('line_transparency','Barline transparency (%)','number',0,0,100),
 ('line_collision_transparency','Collision transparency (%)','number',0,0,100),
 ('line_collision_fade','Collision fade time (s)','number',.25,0,10)],
 'Physics':[
 ('spring','Barline spring (restitution)','number',.45,0,2),
 ('gravity','Barline gravity (px/s²)','number',1800,0,10000),
 ('launch_height','Barline launch height (px)','number',120,0,1000),
 ('bounce','Barline bounce','bool',True,0,1),
 ('peak','Barline represents peak · no launch','bool',False,0,1),
 ('line_gradient_override','Barline gradient override','bool',False,0,1),
 ('line_gradient_speed','Barline gradient speed (°/s)','number',36,-720,720),
 ('line_gradient_offset','Barline gradient offset (°)','number',0,-3600,3600),
 ('line_gradient_size','Barline gradient size (×)','number',1,.1,16),
 ('line_gradient','Barline horizontal gradient','gradient',PALETTES['Rainbow'],0,1)],
 'Particles':[
 ('particles_enabled','Particles enabled','bool',True,0,1),
 ('particle_decal','Particle image','image',None,0,1),
 ('particle_size','Particle image size (px)','soft',[4,10],1,128),
 ('emission_rate','Emission rate (per bar / s)','soft',3.5,0,400),
 ('collision_emission','Collision emission (per impact)','soft',[0,2],0,100),
 ('start_transparency','Start transparency (%)','soft',0,0,100),
 ('mid_enabled','Enable mid transparency','bool',False,0,1),
 ('mid_time','Mid transparency time (s)','soft',.6,0,30),
 ('mid_transparency','Mid transparency (%)','soft',15,0,100),
 ('end_transparency','End transparency (%)','soft',100,0,100),
 ('fade_time','Fade time (s)','soft',[1,1.8],.02,30),
 ('start_vx','Starting VX (px/s)','soft',[-30,30],-3000,3000),
 ('start_vy','Starting VY (px/s; + is up)','soft',[70,180],-3000,3000),
 ('accel_vx','Acceleration VX (px/s²)','soft',0,-10000,10000),
 ('accel_vy','Acceleration VY (px/s²)','soft',-95,-10000,10000),
 ('cbaccel_vx','Acceleration change X (/s)','soft',0,-10000,10000),
 ('cbaccel_vy','Acceleration change Y (/s)','soft',0,-10000,10000),
 ('expaccel_vx','Acceleration multiplier X (/s)','soft',1,0,10),
 ('expaccel_vy','Acceleration multiplier Y (/s)','soft',1,0,10),
 ('particle_gradient_override','Particle start gradient override','bool',False,0,1),
 ('particle_gradient_speed','Particle gradient speed (°/s)','number',36,-720,720),
 ('particle_gradient_offset','Particle gradient offset (°)','number',0,-3600,3600),
 ('particle_gradient_size','Particle gradient size (×)','number',1,.1,16),
 ('particle_gradient','Particle horizontal gradient','gradient',PALETTES['Rainbow'],0,1),
 ('particle_end_override','Fade particle color override','bool',False,0,1),
 ('particle_end_color','Particle end color (RGBA)','color','#FFA54AFF',0,1)]}
DEFAULT={key:deepcopy(default) for fields in FIELDS.values() for key,label,kind,default,lo,hi in fields}
BUILTIN_VISUALS={'Default':deepcopy(DEFAULT)}
for name in ('Classic','Frost','Amethyst','Ember','Starry'):
    spec=deepcopy(DEFAULT)
    if name=='Classic':spec.update(horizontal=[[0,'#21FF40'],[1,'#21FF40']],speed=0,vertical=PALETTES['White'],line_gradient_override=True,line_gradient=[[0,'#FF3030'],[1,'#FF3030']],peak=True,gravity=180,particles_enabled=False)
    elif name=='Starry':spec.update(horizontal=[[0,'#163984'],[.25,'#408EFF'],[.5,'#7FC6FF'],[.75,'#408EFF'],[1,'#163984']],collision_tint=True,collision_color='#FFFFFF99',bar_collision_fade=.6,particle_gradient_override=True,particle_gradient=[[0,'#A8CEFF'],[.5,'#FFFFFF'],[1,'#A8CEFF']],emission_rate=1.5,collision_emission=[1,4])
    else:spec.update(horizontal=PALETTES[name])
    if name in ('Frost','Amethyst','Ember','Starry'):spec['speed']=-36
    if name=='Amethyst':spec.update(collision_tint=True,collision_color='#FFFFFF99',bar_collision_fade=.6)
    if name=='Ember':spec.update(particle_gradient_override=True,particle_gradient=[[0,'#FFC04A'],[.5,'#FF7020'],[1,'#FFC04A']],particle_end_override=True,particle_end_color='#FF390000')
    BUILTIN_VISUALS[name]=deepcopy(spec)


def embed_image(path):
    path=Path(path)
    if path.stat().st_size>16*1024*1024:raise ValueError('Choose an image under 16 MB')
    reader=QImageReader(str(path));size=reader.size()
    if not size.isValid() or size.width()*size.height()>16_000_000:raise ValueError('Choose an image under 16 megapixels')
    image=reader.read()
    if image.isNull():raise ValueError('Could not read image')
    image=image.scaled(2048,2048,Qt.AspectRatioMode.KeepAspectRatio) if max(image.width(),image.height())>2048 else image
    buffer=QBuffer();buffer.open(QIODevice.OpenModeFlag.WriteOnly);image.save(buffer,'PNG')
    if buffer.size()>4*1024*1024:raise ValueError('Image is too large after embedding')
    return {'data':base64.b64encode(bytes(buffer.data())).decode(),'crop':[0,0,0,0],'columns':1,'rows':1,'cell':0,'repeat_x':1,'repeat_y':1,'mode':'fit'}


def image_spec(value):
    if value is None:return None
    if not isinstance(value,dict):raise ValueError('Invalid image settings')
    data=value.get('data','')
    if not isinstance(data,str) or len(data)>6*1024*1024:raise ValueError('Invalid embedded image')
    try:raw=base64.b64decode(data,validate=True)
    except ValueError:raise ValueError('Invalid embedded image data')
    # PNG IHDR dimensions checked before invoking the decoder.
    if len(raw)<24 or raw[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('Embedded images must be PNG')
    w,h=int.from_bytes(raw[16:20],'big'),int.from_bytes(raw[20:24],'big')
    if not 0<w<=2048 or not 0<h<=2048:raise ValueError('Embedded image dimensions exceed 2048')
    if QImage.fromData(raw).isNull():raise ValueError('Invalid PNG')
    result={'data':data,'crop':value.get('crop',[0,0,0,0]),'mode':value.get('mode','fit')}
    crop=result['crop']
    if not isinstance(crop,list) or len(crop)!=4:raise ValueError('Crop needs left, top, right, bottom')
    result['crop']=[number(x,0,.99) for x in crop]
    if crop[0]+crop[2]>=1 or crop[1]+crop[3]>=1:raise ValueError('Cropping must leave part of the image')
    if result['mode'] not in ('fit','scale','stretch'):raise ValueError('Unknown image mode')
    for key,maximum in [('columns',16),('rows',16),('cell',255),('repeat_x',8),('repeat_y',8)]:
        n=value.get(key,0 if key=='cell' else 1)
        if not isinstance(n,int) or isinstance(n,bool):raise ValueError('Image slicing requires integers')
        result[key]=number(n,0 if key=='cell' else 1,maximum)
    if result['cell']>=result['columns']*result['rows']:raise ValueError('Slice index exceeds the grid')
    return result


def visual_spec(value):
    if not isinstance(value,dict):raise ValueError('Invalid visualizer preset')
    result=deepcopy(DEFAULT)
    for fields in FIELDS.values():
        for key,label,kind,default,lo,hi in fields:
            v=value.get(key,default)
            if kind=='bool':
                if not isinstance(v,bool):raise ValueError(f'{label} must be a boolean')
            elif kind=='number':v=number(v,lo,hi)
            elif kind=='choice':
                if v not in lo:raise ValueError(f'Invalid {label}')
            elif kind=='soft':v=soft(v,lo,hi)
            elif kind=='gradient':v=gradient(v)
            elif kind=='color':v=hex_color(v)
            elif kind=='image':v=image_spec(v)
            result[key]=deepcopy(v)
    fields=FIELDS['Particles']
    channels=value.get('channels')
    if channels is not None and (not isinstance(channels,list) or not 1<=len(channels)<=4):raise ValueError('Use one to four particle channels')
    result['channels']=[]
    for index in range(4):
        source=channels[index] if channels is not None and index<len(channels) else {key:result[key] for key,*_ in fields} if index==0 else {'particles_enabled':False}
        if not isinstance(source,dict):raise ValueError('Invalid particle channel')
        channel={}
        for key,label,kind,default,lo,hi in fields:
            v=source.get(key,default)
            if kind=='bool':
                if not isinstance(v,bool):raise ValueError(f'{label} must be a boolean')
            elif kind=='number':v=number(v,lo,hi)
            elif kind=='soft':v=soft(v,lo,hi)
            elif kind=='gradient':v=gradient(v)
            elif kind=='color':v=hex_color(v)
            elif kind=='image':v=image_spec(v)
            channel[key]=deepcopy(v)
        result['channels'].append(channel)
    # Flat particle fields remain a backward-compatible alias for channel 1.
    result.update(result['channels'][0])
    return result


def export_visual(path,name,spec):
    if not isinstance(name,str) or not name.strip() or len(name)>128:raise ValueError('Invalid preset name')
    save_state(path,{'format':'FireMediaVisualizerPreset','version':1,'name':name.strip(),'preset':visual_spec(spec)})


def import_visual(path):
    path=Path(path)
    if path.stat().st_size>64*1024*1024:raise ValueError('Preset is too large')
    try:data=json.loads(path.read_text(encoding='utf-8-sig'))
    except (ValueError,RecursionError) as error:raise ValueError('Invalid visualizer preset JSON') from error
    if not isinstance(data,dict) or data.get('format')!='FireMediaVisualizerPreset' or data.get('version')!=1:raise ValueError('Unsupported visualizer preset')
    name=data.get('name')
    if not isinstance(name,str) or not name.strip() or len(name)>128:raise ValueError('Invalid preset name')
    return name.strip(),visual_spec(data.get('preset'))
