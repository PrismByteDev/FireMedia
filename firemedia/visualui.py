"""Native preset editor and plugin library; no web UI or raw JSON editing."""
from copy import deepcopy
from pathlib import Path
from PyQt6.QtCore import Qt, pyqtSignal, QRectF
from PyQt6.QtGui import QPainter, QLinearGradient, QPixmap
from PyQt6.QtWidgets import (QWidget,QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QPushButton,
    QComboBox,QCheckBox,QDoubleSpinBox,QSpinBox,QLabel,QLineEdit,QColorDialog,QFileDialog,
    QInputDialog,QTabWidget,QScrollArea,QDialogButtonBox,QTableWidget,QHeaderView,QListWidget,
    QMessageBox,QPlainTextEdit)
from .visualspec import (FIELDS,PALETTES,BUILTIN_VISUALS,color4,hex_color,gradient,embed_image,
    image_spec,visual_spec,export_visual,import_visual)
from .formats import unique_name,valid_name


class ColorEdit(QWidget):
    changed=pyqtSignal()
    def __init__(self,value,parent=None):
        super().__init__(parent);layout=QHBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.text=QLineEdit(hex_color(value));self.text.setPlaceholderText('#RRGGBBAA or hsv(H,S,V,A)')
        self.pick=QPushButton('Pick…');self.pick.setMaximumWidth(80)
        layout.addWidget(self.text,1);layout.addWidget(self.pick)
        self.pick.clicked.connect(self.choose);self.text.textChanged.connect(self.changed)
        self.text.setToolTip('RGB plus alpha: #RRGGBBAA, or hsv(H°,S%,V%,A%). Picker supports RGBA channels.')
    def choose(self):
        try:initial=color4(self.text.text())
        except ValueError:initial=color4('#FFFFFF')
        color=QColorDialog.getColor(initial,self,'Color · RGB + alpha',QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if color.isValid():self.text.setText(hex_color(color))
    def value(self):return hex_color(self.text.text())
    def set_value(self,value):self.text.setText(hex_color(value))


class GradientPreview(QWidget):
    def __init__(self,parent):super().__init__(parent);self.stops=gradient(PALETTES['Rainbow']);self.setFixedHeight(24)
    def paintEvent(self,event):
        p=QPainter(self);g=QLinearGradient(0,0,self.width(),0)
        for pos,color in self.stops:g.setColorAt(pos,color4(color))
        p.fillRect(self.rect(),g)


class GradientEdit(QWidget):
    changed=pyqtSignal()
    def __init__(self,value,parent=None):
        super().__init__(parent);self.updating=False;layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        row=QHBoxLayout();self.palette=QComboBox();self.palette.addItems([*PALETTES,'Custom'])
        row.addWidget(self.palette,1);add=QPushButton('+ stop');remove=QPushButton('− stop');row.addWidget(add);row.addWidget(remove);layout.addLayout(row)
        self.preview=GradientPreview(self);layout.addWidget(self.preview)
        self.table=QTableWidget(0,2);self.table.setHorizontalHeaderLabels(['Position (%)','Color · RGB + alpha']);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(140);self.table.setMaximumHeight(210);layout.addWidget(self.table)
        self.palette.currentTextChanged.connect(self.choose_palette);add.clicked.connect(self.add_stop);remove.clicked.connect(self.remove_stop)
        self.set_value(value)
    def choose_palette(self,name):
        if not self.updating and name in PALETTES:self.set_value(PALETTES[name]);self.changed.emit()
    def add_row(self,pos,color):
        row=self.table.rowCount();self.table.insertRow(row)
        position=QDoubleSpinBox();position.setRange(0,100);position.setDecimals(2);position.setValue(pos*100)
        edit=ColorEdit(color);self.table.setCellWidget(row,0,position);self.table.setCellWidget(row,1,edit)
        position.valueChanged.connect(self.edit);edit.changed.connect(self.edit)
    def edit(self,*args):
        if self.updating:return
        self.palette.blockSignals(True);self.palette.setCurrentText('Custom');self.palette.blockSignals(False)
        try:self.preview.stops=self.value();self.preview.update()
        except ValueError:pass
        self.changed.emit()
    def add_stop(self):
        if self.table.rowCount()>=16:return
        try:
            stops=self.value();gaps=[(b[0]-a[0],(a[0]+b[0])/2) for a,b in zip(stops,stops[1:])];pos=max(gaps)[1]
        except ValueError:pos=.5
        self.add_row(pos,'#FFFFFFFF');self.edit()
    def remove_stop(self):
        if self.table.rowCount()>2:self.table.removeRow(max(0,self.table.currentRow()));self.edit()
    def value(self):return gradient([[self.table.cellWidget(i,0).value()/100,self.table.cellWidget(i,1).value()] for i in range(self.table.rowCount())])
    def set_value(self,value):
        self.updating=True;value=gradient(value);self.table.setRowCount(0)
        for pos,color in value:self.add_row(pos,color)
        name=next((name for name,stops in PALETTES.items() if gradient(stops)==value),'Custom');self.palette.setCurrentText(name)
        self.preview.stops=value;self.preview.update();self.updating=False


class SoftEdit(QWidget):
    changed=pyqtSignal()
    def __init__(self,value,lo,hi,parent=None):
        super().__init__(parent);layout=QHBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.minimum=QDoubleSpinBox();self.maximum=QDoubleSpinBox();self.ranged=QCheckBox('Range')
        for spin in (self.minimum,self.maximum):spin.setRange(lo,hi);spin.setDecimals(3);layout.addWidget(spin)
        layout.addWidget(self.ranged);self.set_value(value)
        self.minimum.valueChanged.connect(self.changed);self.maximum.valueChanged.connect(self.changed)
        self.ranged.toggled.connect(self.toggle)
    def toggle(self,value):self.maximum.setVisible(value);self.changed.emit()
    def value(self):return [self.minimum.value(),self.maximum.value()] if self.ranged.isChecked() else self.minimum.value()
    def set_value(self,value):
        ranged=isinstance(value,list);self.minimum.setValue(value[0] if ranged else value);self.maximum.setValue(value[-1] if ranged else value)
        self.ranged.setChecked(ranged);self.maximum.setVisible(ranged)


class ImageEdit(QWidget):
    changed=pyqtSignal()
    def __init__(self,value,parent=None):
        super().__init__(parent);self.spec=deepcopy(value);layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.preview=QLabel();self.preview.setFixedHeight(58);layout.addWidget(self.preview)
        row=QHBoxLayout();load=QPushButton('Choose image…');self.edit=QPushButton('Crop / slice / mode…');clear=QPushButton('Clear')
        row.addWidget(load);row.addWidget(self.edit);row.addWidget(clear);layout.addLayout(row)
        load.clicked.connect(self.load);self.edit.clicked.connect(self.customize);clear.clicked.connect(lambda:self.set_value(None,True));self.set_value(value)
    def value(self):return deepcopy(self.spec)
    def set_value(self,value,emit=False):
        self.spec=deepcopy(value);self.edit.setEnabled(value is not None)
        if value:
            import base64
            pix=QPixmap();pix.loadFromData(base64.b64decode(value['data']));self.preview.setPixmap(pix.scaled(240,58,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
            self.preview.setToolTip('Image pixels are embedded in this preset.')
        else:self.preview.clear();self.preview.setText('No image')
        if emit:self.changed.emit()
    def load(self):
        path,_=QFileDialog.getOpenFileName(self,'Choose image to embed','','Images (*.png *.jpg *.jpeg *.webp *.bmp)')
        if path:
            try:self.set_value(embed_image(path),True)
            except (ValueError,OSError) as error:QMessageBox.warning(self,'Image',str(error))
    def customize(self):
        dialog=QDialog(self);dialog.setWindowTitle('Image · crop, slice, repeat');layout=QVBoxLayout(dialog);form=QFormLayout();layout.addLayout(form)
        form.addRow(QLabel('Crop trims the image, then slicing selects one grid cell.\nRepeat tiles that slice. Fit contains; Scale fills; Stretch distorts.'))
        crops=[]
        for label,value in zip(('Crop left (%)','Crop top (%)','Crop right (%)','Crop bottom (%)'),self.spec['crop']):
            spin=QDoubleSpinBox();spin.setRange(0,99);spin.setValue(value*100);form.addRow(label,spin);crops.append(spin)
        controls={}
        for key,label,maximum in [('columns','Slice columns',16),('rows','Slice rows',16),('cell','Slice index (starts at 0)',255),('repeat_x','Repeat X',8),('repeat_y','Repeat Y',8)]:
            spin=QSpinBox();spin.setRange(0 if key=='cell' else 1,maximum);spin.setValue(self.spec[key]);form.addRow(label,spin);controls[key]=spin
        mode=QComboBox();mode.addItems(['fit','scale','stretch']);mode.setCurrentText(self.spec['mode']);form.addRow('Image mode',mode)
        error=QLabel();error.setWordWrap(True);layout.addWidget(error)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);layout.addWidget(buttons);buttons.rejected.connect(dialog.reject)
        def apply():
            spec=deepcopy(self.spec);spec.update({k:w.value() for k,w in controls.items()});spec['crop']=[w.value()/100 for w in crops];spec['mode']=mode.currentText()
            try:self.set_value(image_spec(spec),True);dialog.accept()
            except ValueError as e:error.setText(str(e))
        buttons.accepted.connect(apply)
        try:dialog.exec()
        finally:dialog.deleteLater()


class SettingCheckBox(QCheckBox):
    """Let the entire form field toggle the setting, not just its indicator."""
    def hitButton(self,pos):return self.rect().contains(pos)


class VisualSettings(QDialog):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.loading=False;self.widgets={};self.channels=deepcopy(window.visual.spec['channels']);self.channel_index=0;self.setWindowTitle('Visualizer · presets and customization');self.resize(880,760)
        layout=QVBoxLayout(self);top=QHBoxLayout();self.presets=QComboBox();self.presets.setAccessibleName('Visualizer preset');top.addWidget(QLabel('Preset'));top.addWidget(self.presets,1)
        for label,fn in [('Save as…',self.save_as),('Update',self.save),('Rename…',self.rename),('Remove',self.remove),('Import…',self.import_file),('Export…',self.export_file)]:
            button=QPushButton(label);button.clicked.connect(fn);top.addWidget(button)
        layout.addLayout(top)
        row=QHBoxLayout();self.renderer=QComboBox();self.renderer.addItem('Built-in bars','')
        for id,name in window.plugins.choices():self.renderer.addItem(name,id)
        self.renderer.setCurrentIndex(max(0,self.renderer.findData(window.plugins.selected)));self.renderer.currentIndexChanged.connect(self.select_renderer)
        window.plugins.changed.connect(self.refresh_renderers)
        row.addWidget(QLabel('Renderer'));row.addWidget(self.renderer,1)
        plugin_button=QPushButton('Plugins…');plugin_button.clicked.connect(self.open_plugins);row.addWidget(plugin_button);layout.addLayout(row)
        row=QHBoxLayout();count=QSpinBox();count.setRange(8,256);count.setValue(window.visual.bar_count);count.setAccessibleName('Visualizer bar count');count.valueChanged.connect(window.set_visual_bar_count)
        row.addWidget(QLabel('Bar count'));row.addWidget(count);smooth=QCheckBox('Smooth falling bars');smooth.setChecked(window.visual.physics);smooth.toggled.connect(lambda v:(setattr(window.visual,'physics',v),window.schedule_save()));row.addWidget(smooth)
        fall=QSpinBox();fall.setRange(30,280);fall.setValue(window.visual.tension);fall.valueChanged.connect(lambda v:(setattr(window.visual,'tension',v),window.schedule_save()));row.addWidget(QLabel('Fall speed'));row.addWidget(fall);row.addStretch();layout.addLayout(row)
        info=QLabel('Changes preview live. Transparency: 0 = opaque, 100 = invisible. Up to 4 particle channels (400 total), plus separate fog. LDM: 24 bars, no particles/fog.');info.setWordWrap(True);layout.addWidget(info)
        tabs=QTabWidget();layout.addWidget(tabs,1)
        for section,fields in FIELDS.items():
            scroll=QScrollArea();scroll.setWidgetResizable(True);page=QWidget();form=QFormLayout(page);form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow);scroll.setWidget(page);tabs.addTab(scroll,section)
            if section=='Particles':
                self.channel_select=QComboBox();self.channel_select.addItems(['Channel 1','Channel 2','Channel 3','Channel 4']);form.addRow('Particle channel',self.channel_select);self.channel_select.currentIndexChanged.connect(self.switch_channel)
            for key,label,kind,default,lo,hi in fields:
                value=window.visual.spec[key]
                if kind=='bool':widget=SettingCheckBox('Enabled');widget.setChecked(value);signal=widget.toggled
                elif kind=='number':widget=QDoubleSpinBox();widget.setRange(lo,hi);widget.setDecimals(3);widget.setValue(value);signal=widget.valueChanged
                elif kind=='choice':widget=QComboBox();widget.addItems(lo);widget.setCurrentText(value);signal=widget.currentTextChanged
                else:
                    widget={'gradient':lambda:GradientEdit(value),'color':lambda:ColorEdit(value),'soft':lambda:SoftEdit(value,lo,hi),'image':lambda:ImageEdit(value)}[kind]();signal=widget.changed
                widget.setAccessibleName(label);form.addRow(label,widget);self.widgets[key]=(kind,widget);signal.connect(self.apply)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        close=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);close.rejected.connect(self.reject);layout.addWidget(close)
        self.refresh_presets(window.visual.preset);self.presets.currentTextChanged.connect(self.choose);self.activate_fields()
    def open_plugins(self):
        self.window.show_plugins();self.refresh_renderers()
    def refresh_renderers(self):
        selected=self.window.plugins.selected
        self.renderer.blockSignals(True);self.renderer.clear();self.renderer.addItem('Built-in bars','')
        for id,name in self.window.plugins.choices():self.renderer.addItem(name,id)
        self.renderer.setCurrentIndex(max(0,self.renderer.findData(selected)));self.renderer.blockSignals(False)
    def select_renderer(self):self.window.plugins.selected=self.renderer.currentData() or '';self.window.visual.update();self.window.schedule_save()
    def refresh_presets(self,name):
        self.presets.blockSignals(True);self.presets.clear();self.presets.addItems([*BUILTIN_VISUALS,*sorted(self.window.visual_presets)]);self.presets.setCurrentText(name);self.presets.blockSignals(False)
    def value(self):
        values={}
        for key,(kind,widget) in self.widgets.items():
            values[key]=widget.isChecked() if kind=='bool' else widget.currentText() if kind=='choice' else widget.value()
        self.channels[self.channel_index]={key:deepcopy(values[key]) for key,*_ in FIELDS['Particles']}
        values['channels']=deepcopy(self.channels);values.update(self.channels[0])
        return visual_spec(values)
    def apply(self,*args):
        if self.loading:return
        try:
            spec=self.value();self.window.visual.configure(spec);self.window.schedule_save();self.status.setText('Fog is enabled but hidden by Low Detail Mode. Turn LDM off in Settings to see it.' if spec['fog_enabled'] and self.window.visual.low_detail else 'Previewing changes · Save as or Update to keep them in a named preset.');self.activate_fields()
        except ValueError as error:self.status.setText(str(error))
    def switch_channel(self,index):
        if self.loading:return
        try:self.value()
        except ValueError as error:
            self.status.setText(str(error));self.channel_select.blockSignals(True);self.channel_select.setCurrentIndex(self.channel_index);self.channel_select.blockSignals(False);return
        self.channel_index=index;self.loading=True
        for key,*_ in FIELDS['Particles']:
            kind,widget=self.widgets[key];value=self.channels[index][key]
            if kind=='bool':widget.setChecked(value)
            elif kind=='number':widget.setValue(value)
            else:widget.set_value(value)
        self.loading=False;self.apply()
    def activate_fields(self):
        s=self.window.visual.spec;channel=s['channels'][self.channel_index]
        dependencies=[('line_gradient','line_gradient_override'),('line_gradient_speed','line_gradient_override'),('line_gradient_offset','line_gradient_override'),('line_gradient_size','line_gradient_override'),('collision_color','collision_tint')]
        for target,flag in dependencies:
            widget=self.widgets[target][1];widget.setEnabled(s[flag]);widget.parentWidget().layout().setRowVisible(widget,s[flag])
        for target,flag in [('particle_gradient','particle_gradient_override'),('particle_gradient_speed','particle_gradient_override'),('particle_gradient_offset','particle_gradient_override'),('particle_gradient_size','particle_gradient_override'),('particle_end_color','particle_end_override'),('mid_time','mid_enabled'),('mid_transparency','mid_enabled')]:
            widget=self.widgets[target][1];widget.setEnabled(channel[flag]);widget.parentWidget().layout().setRowVisible(widget,channel[flag])
        mode=s['background_mode']
        for key,allowed in [('background_color','color'),('background_gradient','gradient'),('background_angle','gradient'),('background_speed','gradient'),('background_size','gradient'),('background_image','image'),('cover_mode','cover')]:
            widget=self.widgets[key][1];widget.setEnabled(mode==allowed);widget.parentWidget().layout().setRowVisible(widget,mode==allowed)
        opacity=self.widgets['background_transparency'][1];opacity.parentWidget().layout().setRowVisible(opacity,mode!='off')
        for key in ('wave_gradient','wave_speed','wave_offset','wave_size'):
            widget=self.widgets[key][1];widget.parentWidget().layout().setRowVisible(widget,s['wave_mode']=='gradient')
        widget=self.widgets['wave_color'][1];widget.parentWidget().layout().setRowVisible(widget,s['wave_mode']=='solid')
        for key in ('fog_color','fog_emission','fog_lifetime','fog_radius','fog_rise'):
            widget=self.widgets[key][1];widget.parentWidget().layout().setRowVisible(widget,s['fog_enabled'])
    def choose(self,name):
        spec=BUILTIN_VISUALS.get(name,self.window.visual_presets.get(name))
        if spec is None:return
        spec=visual_spec(spec);self.channels=deepcopy(spec['channels']);self.channel_index=0
        self.loading=True;self.channel_select.setCurrentIndex(0)
        for key,(kind,widget) in self.widgets.items():
            if kind=='bool':widget.setChecked(spec[key])
            elif kind=='number':widget.setValue(spec[key])
            elif kind=='choice':widget.setCurrentText(spec[key])
            else:widget.set_value(spec[key])
        self.loading=False;self.window.visual.preset=name;self.apply()
    def save_as(self):
        name,ok=QInputDialog.getText(self,'Save visualizer preset','Name:')
        if not ok:return
        try:
            name=valid_name(name)
            if name in BUILTIN_VISUALS or name in self.window.visual_presets:raise ValueError('Choose a new preset name')
            self.window.visual_presets[name]=self.value();self.window.visual.preset=name;self.refresh_presets(name);self.window.schedule_save();self.status.setText('Preset saved.')
        except ValueError as error:self.status.setText(str(error))
    def save(self):
        name=self.presets.currentText()
        if name in BUILTIN_VISUALS:self.status.setText('Use Save as to customize a built-in preset.');return
        try:self.window.visual_presets[name]=self.value();self.window.schedule_save();self.status.setText('Preset updated.')
        except ValueError as error:self.status.setText(str(error))
    def rename(self):
        old=self.presets.currentText()
        if old in BUILTIN_VISUALS:self.status.setText('Built-in presets keep their names.');return
        name,ok=QInputDialog.getText(self,'Rename preset','Name:',text=old)
        if not ok:return
        try:
            name=valid_name(name)
            if name==old:return
            if name in BUILTIN_VISUALS or name in self.window.visual_presets:raise ValueError('Name already exists')
            self.window.visual_presets[name]=self.window.visual_presets.pop(old);self.window.visual.preset=name;self.refresh_presets(name);self.window.schedule_save()
        except ValueError as error:self.status.setText(str(error))
    def remove(self):
        name=self.presets.currentText()
        if name in BUILTIN_VISUALS:self.status.setText('Built-in presets cannot be removed.');return
        self.window.visual_presets.pop(name,None);self.refresh_presets('Default');self.choose('Default')
    def export_file(self):
        path,_=QFileDialog.getSaveFileName(self,'Export visualizer preset',self.presets.currentText()+'.firemv','FireMedia visualizer presets (*.firemv)')
        if path:
            try:export_visual(path if path.lower().endswith('.firemv') else path+'.firemv',self.presets.currentText(),self.value());self.status.setText('Preset and images exported.')
            except (OSError,ValueError) as error:self.status.setText(str(error))
    def import_file(self):
        path,_=QFileDialog.getOpenFileName(self,'Import visualizer preset','','FireMedia visualizer presets (*.firemv)')
        if path:
            try:
                name,spec=import_visual(path);name=unique_name(name,{*BUILTIN_VISUALS,*self.window.visual_presets});self.window.visual_presets[name]=spec;self.refresh_presets(name);self.choose(name)
            except (OSError,ValueError) as error:self.status.setText(str(error))


class PluginDialog(QDialog):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.manager=window.plugins;self.setWindowTitle('FireMedia · plugins');self.resize(640,480)
        layout=QVBoxLayout(self);info=QLabel('Mods run in a restricted Linux process: no host files, networking, or subprocesses.\nOnly packaged assets and the drawing/event API are available. No sandbox means no execution.');info.setWordWrap(True);layout.addWidget(info)
        self.list=QListWidget();layout.addWidget(self.list);row=QHBoxLayout()
        for name,fn in [('Install .firemp…',self.install),('Enable',self.enable),('Disable',self.disable),('Remove',self.remove)]:
            button=QPushButton(name);button.clicked.connect(fn);row.addWidget(button)
        layout.addLayout(row);self.log=QPlainTextEdit();self.log.setReadOnly(True);self.log.setMaximumHeight(140);layout.addWidget(self.log)
        close=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);close.rejected.connect(self.reject);layout.addWidget(close)
        self.manager.changed.connect(self.refresh);self.refresh()
    def refresh(self):
        selected=self.list.currentItem().data(Qt.ItemDataRole.UserRole) if self.list.currentItem() else None;self.list.clear()
        from PyQt6.QtWidgets import QListWidgetItem
        for id,plugin in self.manager.plugins.items():
            item=QListWidgetItem(f"{plugin.manifest['name']} · {plugin.manifest['version']} · {'Enabled' if plugin.active else 'Disabled'}");item.setData(Qt.ItemDataRole.UserRole,id);item.setToolTip(plugin.error or id);self.list.addItem(item)
            if id==selected:self.list.setCurrentItem(item)
        self.log.setPlainText('\n'.join(self.manager.messages));self.window.schedule_save()
    def id(self):return self.list.currentItem().data(Qt.ItemDataRole.UserRole) if self.list.currentItem() else None
    def install(self):
        path,_=QFileDialog.getOpenFileName(self,'Install trusted plugin','','FireMedia plugins (*.firemp)')
        if path:
            try:self.manager.install(path)
            except (OSError,ValueError,SyntaxError) as error:QMessageBox.warning(self,'Plugin',str(error))
    def enable(self):
        if self.id():self.manager.enable(self.id())
    def disable(self):
        if self.id():self.manager.disable(self.id())
    def remove(self):
        if self.id():self.manager.remove(self.id())
