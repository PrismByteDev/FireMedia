"""Transparent native scrubbers with a fixed full-range volume gradient."""
from PyQt6.QtCore import Qt,QRectF
from PyQt6.QtGui import QPainter,QColor,QLinearGradient,QPalette
from PyQt6.QtWidgets import QSlider,QStyle,QStyleOptionSlider

class SeekSlider(QSlider):
    _jumping=False
    def geometry_parts(self):
        option=QStyleOptionSlider();self.initStyleOption(option)
        groove=self.style().subControlRect(QStyle.ComplexControl.CC_Slider,option,QStyle.SubControl.SC_SliderGroove,self)
        handle=self.style().subControlRect(QStyle.ComplexControl.CC_Slider,option,QStyle.SubControl.SC_SliderHandle,self)
        return option,groove,handle
    def position_value(self,event):
        option,groove,handle=self.geometry_parts();span=max(1,groove.width()-handle.width())
        offset=round(event.position().x()-groove.x()-handle.width()/2)
        return QStyle.sliderValueFromPosition(self.minimum(),self.maximum(),max(0,min(span,offset)),span,option.upsideDown)
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            if not self.geometry_parts()[2].contains(event.position().toPoint()):
                self._jumping=True;self.setFocus();self.setSliderDown(True);self.setSliderPosition(self.position_value(event));event.accept();return
        super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if self._jumping:self.setSliderPosition(self.position_value(event));event.accept()
        else:super().mouseMoveEvent(event)
    def mouseReleaseEvent(self,event):
        if self._jumping and event.button()==Qt.MouseButton.LeftButton:
            self.setSliderPosition(self.position_value(event));self._jumping=False;self.setSliderDown(False);event.accept()
        else:super().mouseReleaseEvent(event)
    def paintEvent(self,event):
        option,groove,handle=self.geometry_parts();p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        start=groove.left()+handle.width()/2;end=groove.right()-handle.width()/2+1
        position=QStyle.sliderPositionFromValue(self.minimum(),self.maximum(),self.value(),max(1,round(end-start)),option.upsideDown)
        x=start+position;rect=QRectF(start,self.height()/2-2,max(1,end-start),4)
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(self.palette().color(QPalette.ColorRole.Mid));p.drawRoundedRect(rect,2,2)
        fill=QRectF(x,rect.y(),end-x,4) if option.upsideDown else QRectF(start,rect.y(),x-start,4)
        p.save();p.setClipRect(fill);p.setBrush(self.fill_brush(start,end));p.drawRoundedRect(rect,2,2);p.restore()
        p.setBrush(self.palette().color(QPalette.ColorRole.Text));p.drawEllipse(QRectF(x-6.5,self.height()/2-6.5,13,13));p.end()
    def fill_brush(self,start,end):return self.palette().color(QPalette.ColorRole.Text)

class VolumeSlider(SeekSlider):
    def fill_brush(self,start,end):
        gradient=QLinearGradient(start,0,end,0)
        for position,color in [(0,'#000000'),(1/3,'#00FF00'),(2/3,'#FFFF00'),(1,'#FF0000')]:gradient.setColorAt(position,QColor(color))
        return gradient
