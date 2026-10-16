"""Validated portable FireMedia preset and playlist files (JSON, never code)."""
from copy import deepcopy
from pathlib import Path
import json
import math
import re
from urllib.parse import urlparse,unquote
from .playlists import Track,save_state
from .sources import source_scheme, file_uri_path

DEFAULT_SUBTITLE={'font':'Sans Serif','size':38,'delay':0.0,'particles':False,
    'color':'#FFFFFF','gradient':False,'gradient_color':'#C67AFF',
    'stroke_color':'#000000','stroke_width':2.0}
BUILTIN_PRESETS={
    'Glow':dict(DEFAULT_SUBTITLE,color='#FFE4BF',gradient=True,stroke_color='#59246B'),
    'Cinema':dict(DEFAULT_SUBTITLE,font='Serif',color='#FFF0CF'),
    'Clean':dict(DEFAULT_SUBTITLE)}

def subtitle_spec(value):
    if not isinstance(value,dict):raise ValueError('Invalid subtitle preset')
    result=deepcopy(DEFAULT_SUBTITLE)
    for key in result:
        if key not in value:continue
        item=value[key]
        if key in ('particles','gradient'):
            if not isinstance(item,bool):raise ValueError(f'{key} must be a boolean')
        elif key=='font':
            if not isinstance(item,str) or not item.strip() or len(item)>128:raise ValueError('Invalid font')
        elif key in ('color','gradient_color','stroke_color'):
            if not isinstance(item,str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}',item):raise ValueError('Use RGB hex colors')
        else:
            if isinstance(item,bool) or not isinstance(item,(int,float)) or not math.isfinite(item):raise ValueError(f'Invalid {key}')
            lo,hi={'size':(16,144),'delay':(-60,60),'stroke_width':(0,12)}[key]
            if not lo<=item<=hi:raise ValueError(f'{key} outside supported range')
        result[key]=item
    result['size']=round(result['size'])
    return result

def read_document(path,kind):
    path=Path(path)
    if path.stat().st_size>8*1024*1024:raise ValueError('File is too large')
    data=json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data,dict) or data.get('format')!=kind or data.get('version')!=1:
        raise ValueError('Unsupported FireMedia file format or version')
    return data

def valid_name(name):
    if not isinstance(name,str) or not name.strip() or len(name)>128:raise ValueError('Invalid name')
    return name.strip()

def unique_name(name,existing):
    original=valid_name(name);name=original;number=2
    while name in existing:
        name=f'{original} ({number})';number+=1
    return name

def export_subtitle(path,name,spec):
    save_state(path,{'format':'FireMediaSubtitlePreset','version':1,'name':valid_name(name),'preset':subtitle_spec(spec)})

def import_subtitle(path):
    data=read_document(path,'FireMediaSubtitlePreset')
    return valid_name(data.get('name')),subtitle_spec(data.get('preset'))

def export_app_playlist(path,name,tracks):
    save_state(path,{'format':'FireMediaPlaylist','version':1,'name':valid_name(name),
                     'tracks':[{'source':t.source,'title':t.title} for t in tracks]})

def import_app_playlist(path):
    data=read_document(path,'FireMediaPlaylist');name=valid_name(data.get('name'))
    entries=data.get('tracks')
    if not isinstance(entries,list) or len(entries)>10000:raise ValueError('Invalid track list')
    tracks=[]
    for entry in entries:
        if not isinstance(entry,dict):raise ValueError('Invalid track')
        source=entry.get('source');title=entry.get('title','');duration=entry.get('duration',-1)
        if not isinstance(source,str) or not source or not isinstance(title,str):raise ValueError('Invalid track source or title')
        scheme=source_scheme(source)
        if scheme not in ('','file','http','https'):raise ValueError('Unsupported media URI')
        if not scheme:source=str((Path(path).resolve().parent/source).resolve())
        if isinstance(duration,bool) or not isinstance(duration,(int,float)) or not math.isfinite(duration):raise ValueError('Invalid duration')
        tracks.append(Track.from_source(source,title,duration))
    return name,tracks

def matching_srt(source):
    if source_scheme(source) not in ('','file'):return None
    parsed=urlparse(source)
    path=Path(file_uri_path(source) if parsed.scheme=='file' else source)
    exact=path.with_suffix('.srt')
    if exact.is_file():return exact
    try: subtitles=[p for p in path.parent.iterdir() if p.suffix.lower()=='.srt' and p.is_file()]
    except OSError:return None
    matches=[p for p in subtitles if p.stem.casefold()==path.stem.casefold()]
    return matches[0] if matches else subtitles[0] if len(subtitles)==1 else None
