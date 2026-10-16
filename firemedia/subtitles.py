"""Transparent, native text overlay with font, gradient, stroke, and sparks."""
import random
import time
from PyQt6.QtCore import Qt,QRectF,QTimer,QPointF
from PyQt6.QtGui import QColor,QFont,QFontMetricsF,QPainter,QPainterPath,QPen,QLinearGradient
from PyQt6.QtWidgets import QWidget
from .formats import DEFAULT_SUBTITLE
from .visibility import is_presented

class SubtitleOverlay(QWidget):
    def __init__(self,parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setStyleSheet('background: transparent;')
        self.spec=dict(DEFAULT_SUBTITLE);self.text='';self.low_detail=False
        self.sparks=[];self.bounds=QRectF();self.clock=time.monotonic()
        self.timer=QTimer(self);self.timer.setInterval(33);self.timer.timeout.connect(self.animate)
    def configure(self,spec):self.spec=dict(spec);self.refresh_animation();self.update()
    def set_text(self,text):
        if text!=self.text:
            self.text=text;self.sparks.clear();self.refresh_animation();self.update()
    def refresh_animation(self):
        active=bool(self.text and self.spec['particles'] and not self.low_detail and is_presented(self))
        if active and not self.timer.isActive():self.clock=time.monotonic();self.timer.start()
        elif not active:self.timer.stop();self.sparks.clear()
    def resizeEvent(self,event):
        super().resizeEvent(event);self.sparks.clear();self.bounds=QRectF()
    def showEvent(self,event):
        super().showEvent(event);self.refresh_animation()
    def hideEvent(self,event):
        super().hideEvent(event);self.refresh_animation()
    def animate(self):
        now=time.monotonic();dt=min(.1,now-self.clock);self.clock=now
        if self.low_detail or not self.text or not is_presented(self):self.refresh_animation();return
        for p in self.sparks:p[1]-=p[2]*dt;p[3]-=dt
        self.sparks=[p for p in self.sparks if p[3]>0]
        if len(self.sparks)<70 and not self.bounds.isEmpty():
            self.sparks.append([random.uniform(self.bounds.left(),self.bounds.right()),self.bounds.bottom(),random.uniform(15,45),random.uniform(.4,1.2)])
        self.update()
    def paintEvent(self,event):
        if not self.text:return
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font=QFont(self.spec['font']);font.setPixelSize(max(12,round(self.spec['size']*self.width()/1280)));font.setBold(True)
        metrics=QFontMetricsF(font);lines=[]
        for paragraph in self.text.splitlines():
            line=''
            for word in paragraph.split():
                candidate=(line+' '+word).strip()
                if line and metrics.horizontalAdvance(candidate)>self.width()*.9:lines.append(line);line=word
                else:line=candidate
            lines.append(line)
        path=QPainterPath();height=metrics.height();baseline=self.height()*.9-(len(lines)-1)*height
        for i,line in enumerate(lines):path.addText(QPointF((self.width()-metrics.horizontalAdvance(line))/2,baseline+i*height),font,line)
        self.bounds=path.boundingRect()
        if self.spec['stroke_width']:
            painter.strokePath(path,QPen(QColor(self.spec['stroke_color']),self.spec['stroke_width']*2,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
        if self.spec['gradient']:
            gradient=QLinearGradient(0,self.bounds.top(),0,self.bounds.bottom());gradient.setColorAt(0,QColor(self.spec['color']));gradient.setColorAt(1,QColor(self.spec['gradient_color']));painter.setBrush(gradient)
        else:painter.setBrush(QColor(self.spec['color']))
        painter.fillPath(path,painter.brush())
        if self.spec['particles'] and not self.low_detail:
            for x,y,speed,life in self.sparks:
                color=QColor(self.spec['gradient_color']);color.setAlphaF(min(1,life));painter.setPen(QPen(color,1));painter.drawLine(QPointF(x-2,y),QPointF(x+2,y));painter.drawLine(QPointF(x,y-2),QPointF(x,y+2))
