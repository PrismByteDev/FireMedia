"""Native UI themes, validated portable .firemt data, and themed surfaces."""
from copy import deepcopy
import base64,json,math,re,time
from pathlib import Path
from PyQt6.QtCore import Qt,QTimer,QRectF,QPointF
from PyQt6.QtGui import QColor,QPainter,QLinearGradient,QImage,QPalette,QFont
from PyQt6.QtWidgets import QWidget
from .visualspec import color4,hex_color,gradient,image_spec,PALETTES,number
from .playlists import save_state
from .visibility import is_presented

COLORS={'window':'#0B0B0EFF','panel':'#17171CFF','control':'#292830FF','text':'#EDEDF0FF','muted':'#AAA5B3FF','accent':'#B98AEAFF','border':'#504957FF','selection':'#453152FF'}
DEFAULT_THEME={'mode':'simple','appearance':'dark','hue':275,'grayscale':False,'colors':COLORS,
    'font':'Sans Serif','font_size':13,'surface_mode':'color','gradient':PALETTES['Amethyst'],
    'angle':0,'speed':0,'offset':0,'size':1,'transparency':0,'image':None,'groups':{}}


SURFACE_GROUPS=('window','panel','control','selection')
SURFACE_KEYS=('surface_mode','gradient','angle','speed','offset','size','transparency','image')

def group_surface(spec,role):
    result={key:deepcopy(spec[key]) for key in SURFACE_KEYS}
    if role not in ('window','panel'):result.update(surface_mode='color',image=None,transparency=0)
    result.update(deepcopy(spec.get('groups',{}).get(role,{})))
    return result

def simple_theme(hue=275,appearance='dark',grayscale=False):
    result=deepcopy(DEFAULT_THEME);result.update(hue=hue,appearance=appearance,grayscale=grayscale)
    dark=appearance=='dark';sat=0 if grayscale else .28
    def hsv(v,s=sat):return hex_color(QColor.fromHsvF(hue/360,s,v))
    result['colors']={'window':hsv(.07 if dark else .96),'panel':hsv(.11 if dark else .91),
        'control':hsv(.18 if dark else .99),'text':'#EDEDF0FF' if dark else '#16121CFF',
        'muted':'#AFAAB8FF' if dark else '#56515EFF','accent':hsv(.9 if dark else .55,0 if grayscale else .6),
        'border':hsv(.32 if dark else .68),'selection':hsv(.3 if dark else .78,.05 if grayscale else .42)}
    return result

THEME_PALETTES={'Default':deepcopy(DEFAULT_THEME),'Ocean':simple_theme(205),'Ember':simple_theme(20),
    'Forest':simple_theme(135),'Light':simple_theme(215,'light'),'Monochrome':simple_theme(0,'dark',True)}


def theme_spec(value):
    if not isinstance(value,dict):raise ValueError('Invalid UI theme')
    s=deepcopy(DEFAULT_THEME)
    for key in s:
        if key in value:s[key]=deepcopy(value[key])
    if s['mode'] not in ('simple','palette','advanced') or s['appearance'] not in ('dark','light'):raise ValueError('Invalid theme mode')
    s['hue']=round(number(s['hue'],0,359))
    if not isinstance(s['grayscale'],bool):raise ValueError('Invalid shade setting')
    if not isinstance(s['colors'],dict):raise ValueError('Invalid theme palette')
    s['colors']={key:hex_color(s['colors'].get(key,default)) for key,default in COLORS.items()}
    if not isinstance(s['font'],str) or not 0<len(s['font'])<=128 or re.search(r'[;{}\n\r"\\]',s['font']):raise ValueError('Invalid theme font')
    s['font_size']=round(number(s['font_size'],10,28))
    if s['surface_mode'] not in ('color','gradient','image'):raise ValueError('Invalid theme surface')
    s['gradient']=gradient(s['gradient']);s['image']=image_spec(s['image'])
    for key,lo,hi in [('angle',-360,360),('speed',-360,360),('offset',-3600,3600),('size',.1,16),('transparency',0,100)]:number(s[key],lo,hi)
    groups=s['groups']
    if not isinstance(groups,dict) or any(key not in SURFACE_GROUPS for key in groups):raise ValueError('Invalid theme groups')
    s['groups']={}
    for role,settings in groups.items():
        if not isinstance(settings,dict):raise ValueError('Invalid group settings')
        # Reuse the same validation for every surface; unknown keys never reach QSS.
        candidate={key:deepcopy(s[key]) for key in DEFAULT_THEME if key!='groups'}
        candidate.update({key:deepcopy(settings[key]) for key in SURFACE_KEYS if key in settings})
        checked=theme_spec(candidate)
        if role in ('control','selection') and checked['surface_mode']=='image':raise ValueError('Images are supported for Window and Panel groups')
        s['groups'][role]={key:checked[key] for key in SURFACE_KEYS}
    return s


def export_theme(path,name,spec):
    if not isinstance(name,str) or not name.strip() or len(name)>128:raise ValueError('Invalid theme name')
    save_state(path,{'format':'FireMediaTheme','version':1,'name':name.strip(),'theme':theme_spec(spec)})


def import_theme(path):
    path=Path(path)
    if path.stat().st_size>16*1024*1024:raise ValueError('Theme exceeds 16 MB')
    try:value=json.loads(path.read_text(encoding='utf-8-sig'))
    except (ValueError,RecursionError) as error:raise ValueError('Invalid theme JSON') from error
    if not isinstance(value,dict) or value.get('format')!='FireMediaTheme' or value.get('version')!=1:raise ValueError('Unsupported theme file')
    name=value.get('name')
    if not isinstance(name,str) or not name.strip() or len(name)>128:raise ValueError('Invalid theme name')
    return name.strip(),theme_spec(value.get('theme'))


def group_brush(spec,role):
    s=group_surface(spec,role);base=color4(spec['colors'][role])
    if s['surface_mode']=='gradient':
        # Widget styles accept QGradient brushes, including repeated gradients.
        angle=math.radians(s['angle']);length=1/s['size'];shift=s['offset']/360*length
        dx,dy=math.cos(angle),math.sin(angle)
        stops=[]
        for pos,color in s['gradient']:
            c=color4(color);c.setAlphaF(c.alphaF()*(1-s['transparency']/100))
            # Blend over the group's base color, just like ThemeSurface does.
            a=c.alphaF();mixed=QColor.fromRgbF(*(c.getRgbF()[i]*a+base.getRgbF()[i]*(1-a) for i in range(3)))
            stops.append('stop:%g rgba(%d,%d,%d,%d)'%((pos,)+mixed.getRgb()))
        return 'qlineargradient(spread:repeat,x1:%g,y1:%g,x2:%g,y2:%g,%s)'%(-dx*shift,-dy*shift,dx*(length-shift),dy*(length-shift),','.join(stops))
    return 'rgba(%d,%d,%d,%d)'%base.getRgb()


def theme_css(spec):
    def c(key):return 'rgba(%d,%d,%d,%d)'%color4(spec['colors'][key]).getRgb()
    brushes={role:group_brush(spec,role) for role in SURFACE_GROUPS}
    def surface(role):return brushes[role]
    check=Path(__file__).with_name('assets')/('check-dark.svg' if color4(spec['colors']['accent']).lightnessF()>.55 else 'check-light.svg')
    return f'''
QWidget {{ background: transparent; color: {c('text')}; font-family: "{spec['font']}"; font-size: {spec['font_size']}px; }}
QMainWindow {{ background: {c('window')}; }}
QDialog, QMenu {{ background: {surface('panel')}; }}
QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget, QStackedWidget, QTabWidget::pane {{ background: {surface('panel')}; color: {c('text')}; }}
QScrollArea {{ border: none; }}
QTabWidget::pane {{ border: 1px solid {c('border')}; }}
QTabBar::tab {{ background: {surface('control')}; color: {c('text')}; border: 1px solid {c('border')}; padding: 7px 10px; }}
QTabBar::tab:selected {{ background: {surface('selection')}; border-bottom-color: {c('accent')}; }}
QTabBar::tab:hover {{ border-color: {c('accent')}; }}
QToolButton {{ border: none; border-radius: 5px; padding: 7px; background: transparent; }}
QToolButton:hover, QToolButton:checked, QMenu::item:selected {{ background: {surface('selection')}; }}
QPushButton {{ background: {surface('control')}; border: 1px solid {c('border')}; border-radius: 4px; padding: 7px 13px; }}
QPushButton:hover {{ border-color: {c('accent')}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {c('muted')}; }}
QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit {{ background: {surface('control')}; border: 1px solid {c('border')}; border-radius: 4px; padding: 6px; }}
QComboBox QAbstractItemView {{ background: {surface('control')}; selection-background-color: {surface('selection')}; }}
QListWidget {{ border: none; background: transparent; outline: none; padding: 4px 12px; }}
QListWidget::item {{ padding: 8px 12px; border-bottom: 1px solid {c('border')}; }}
QListWidget::item:selected {{ background: {surface('selection')}; }}
QListWidget::item:hover {{ background: {surface('control')}; }}
QMenu {{ border: 1px solid {c('border')}; padding: 5px; }}
QMenu::item {{ padding: 8px 28px 8px 12px; }}
QMenu::separator {{ height: 1px; background: {c('border')}; margin: 4px; }}
QLabel {{ background: transparent; }}
QLabel#timeLabel {{ color: {c('muted')}; font-size: 11px; }}
QLabel#fullTitle {{ padding: 6px 12px; font-size: 18px; background: {c('panel')}; }}
QSlider {{ background: transparent; }}
QSlider::groove:horizontal {{ background: {c('border')}; height: 4px; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {c('accent')}; }}
QSlider::handle:horizontal {{ background: {c('text')}; width: 13px; margin: -5px 0; border-radius: 6px; }}
QSlider::groove:vertical {{ background: {c('border')}; width: 4px; }}
QSlider::handle:vertical {{ background: {c('text')}; height: 9px; margin: 0 -6px; }}
QSplitter::handle:vertical {{ background: {c('border')}; height: 5px; }}
QCheckBox, QRadioButton {{ spacing: 8px; min-height: 22px; color: {c('text')}; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 18px; height: 18px; background: {surface('control')}; border: 1px solid {c('border')}; border-radius: 3px; }}
QCheckBox::indicator:checked {{ background: {c('accent')}; image: url("{check.as_posix()}"); border-color: {c('accent')}; }}
QRadioButton::indicator {{ border-radius: 9px; }}
QRadioButton::indicator:checked {{ background: {c('accent')}; border: 4px solid {c('border')}; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {c('accent')}; }}
QAbstractItemView, QTableWidget, QTreeView, QTextEdit {{ background: {surface('control')}; color: {c('text')}; alternate-background-color: {surface('panel')}; gridline-color: {c('border')}; selection-background-color: {surface('selection')}; selection-color: {c('text')}; border: 1px solid {c('border')}; }}
QHeaderView, QHeaderView::section, QTableCornerButton::section {{ background: {surface('panel')}; color: {c('text')}; border: 1px solid {c('border')}; padding: 4px; }}
QScrollBar:vertical {{ background: {surface('panel')}; width: 13px; margin: 0; }}
QScrollBar:horizontal {{ background: {surface('panel')}; height: 13px; margin: 0; }}
QScrollBar::handle {{ background: {c('border')}; border-radius: 4px; min-height: 20px; min-width: 20px; }}
QScrollBar::handle:hover {{ background: {c('accent')}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QGroupBox {{ border: 1px solid {c('border')}; margin-top: 12px; padding: 8px; }}
QGroupBox::title {{ color: {c('text')}; subcontrol-origin: margin; padding: 0 5px; }}
QToolTip {{ background: {surface('control')}; color: {c('text')}; border: 1px solid {c('border')}; }}
QWidget:disabled {{ color: {c('muted')}; }}
QStatusBar {{ background: {surface('control')}; color: {c('text')}; }}
'''


def set_theme_palette(widget,spec):
    palette=QPalette(widget.palette());colors=spec['colors']
    for role,key in [(QPalette.ColorRole.Window,'window'),(QPalette.ColorRole.Base,'control'),(QPalette.ColorRole.Button,'control'),
                     (QPalette.ColorRole.Text,'text'),(QPalette.ColorRole.WindowText,'text'),(QPalette.ColorRole.ButtonText,'text'),
                     (QPalette.ColorRole.AlternateBase,'panel'),(QPalette.ColorRole.ToolTipBase,'control'),(QPalette.ColorRole.ToolTipText,'text'),
                     (QPalette.ColorRole.Light,'border'),(QPalette.ColorRole.Dark,'border'),(QPalette.ColorRole.Shadow,'window'),
                     (QPalette.ColorRole.Link,'accent'),(QPalette.ColorRole.PlaceholderText,'muted'),(QPalette.ColorRole.Mid,'border'),(QPalette.ColorRole.Highlight,'selection'),(QPalette.ColorRole.HighlightedText,'text')]:palette.setColor(role,color4(colors[key]))
    for role in (QPalette.ColorRole.Text,QPalette.ColorRole.WindowText,QPalette.ColorRole.ButtonText):palette.setColor(QPalette.ColorGroup.Disabled,role,color4(colors['muted']))
    widget.setPalette(palette);widget.setFont(QFont(spec['font'],round(spec['font_size']*.75)))


class ThemeSurface(QWidget):
    def __init__(self,role='panel',parent=None):
        super().__init__(parent);self.role=role;self.spec=deepcopy(DEFAULT_THEME);self.image=QImage();self.started=time.monotonic()
        self.timer=QTimer(self);self.timer.setInterval(33);self.timer.timeout.connect(self.update)
    def configure_theme(self,spec):
        self.spec={**spec,**group_surface(spec,self.role)};spec=self.spec;self.image=QImage()
        if spec['image']:
            v=spec['image'];self.image=QImage.fromData(base64.b64decode(v['data']));l,t,r,b=v['crop'];w,h=self.image.width(),self.image.height()
            left=min(w-1,round(l*w));top=min(h-1,round(t*h));right=max(left+1,round((1-r)*w));bottom=max(top+1,round((1-b)*h))
            self.image=self.image.copy(left,top,right-left,bottom-top);cols,rows,cell=v['columns'],v['rows'],v['cell'];w,h=self.image.width(),self.image.height()
            self.image=self.image.copy(min(w-1,int(cell%cols*w/cols)),min(h-1,int(cell//cols*h/rows)),max(1,w//cols),max(1,h//rows))
        self.refresh_animation()
        self.update()
    def refresh_animation(self):
        active=self.spec['surface_mode']=='gradient' and self.spec['speed'] and is_presented(self)
        if active and not self.timer.isActive():self.timer.start()
        elif not active:self.timer.stop()
    def showEvent(self,event):
        super().showEvent(event);self.refresh_animation()
    def hideEvent(self,event):
        super().hideEvent(event);self.refresh_animation()
    def paintEvent(self,event):
        p=QPainter(self);s=self.spec;p.fillRect(self.rect(),color4(s['colors'][self.role]));p.setOpacity(1-s['transparency']/100)
        if s['surface_mode']=='gradient':
            angle=math.radians(s['angle']);length=max(1,(abs(math.cos(angle))*self.width()+abs(math.sin(angle))*self.height())/s['size'])
            shift=((time.monotonic()-self.started)*s['speed']+s['offset'])/360*length
            dx,dy=math.cos(angle)*length,math.sin(angle)*length
            g=QLinearGradient(-math.cos(angle)*shift,-math.sin(angle)*shift,dx-math.cos(angle)*shift,dy-math.sin(angle)*shift);g.setSpread(QLinearGradient.Spread.RepeatSpread)
            for pos,c in s['gradient']:g.setColorAt(pos,color4(c))
            p.fillRect(self.rect(),g)
        elif s['surface_mode']=='image' and not self.image.isNull():
            v=s['image'];cw,ch=self.width()/v['repeat_x'],self.height()/v['repeat_y']
            mode={'fit':Qt.AspectRatioMode.KeepAspectRatio,'scale':Qt.AspectRatioMode.KeepAspectRatioByExpanding,'stretch':Qt.AspectRatioMode.IgnoreAspectRatio}[v['mode']]
            image=self.image.scaled(max(1,round(cw)),max(1,round(ch)),mode,Qt.TransformationMode.SmoothTransformation)
            for x in range(v['repeat_x']):
                for y in range(v['repeat_y']):
                    p.save();p.setClipRect(QRectF(x*cw,y*ch,cw,ch));p.drawImage(QPointF((x+.5)*cw-image.width()/2,(y+.5)*ch-image.height()/2),image);p.restore()
        p.end()
