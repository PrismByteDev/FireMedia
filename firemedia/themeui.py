"""Theme customization lives inside the common Settings submenu."""
from copy import deepcopy
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QComboBox,QCheckBox,QSpinBox,
    QDoubleSpinBox,QPushButton,QLabel,QStackedWidget,QWidget,QScrollArea,QFontComboBox,QDialogButtonBox,
    QFileDialog,QInputDialog)
from PyQt6.QtGui import QFont
from .visualui import ColorEdit,GradientEdit,ImageEdit
from .themes import theme_spec,simple_theme,THEME_PALETTES,COLORS,export_theme,import_theme,group_surface,SURFACE_GROUPS,SURFACE_KEYS
from .formats import valid_name,unique_name


class ThemeDialog(QDialog):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.loading=True;self.setWindowTitle('Settings · Themes');self.resize(780,690)
        layout=QVBoxLayout(self);row=QHBoxLayout();self.mode=QComboBox();self.mode.addItems(['Simple','Color palette','Advanced']);row.addWidget(QLabel('Customization'));row.addWidget(self.mode,1)
        for label,fn in [('Import .firemt…',self.import_file),('Export .firemt…',self.export_file)]:b=QPushButton(label);b.clicked.connect(fn);row.addWidget(b)
        layout.addLayout(row);self.pages=QStackedWidget();layout.addWidget(self.pages,1)
        simple=QWidget();form=QFormLayout(simple);self.pages.addWidget(simple)
        self.appearance=QComboBox();self.appearance.addItems(['dark','light']);form.addRow('Appearance',self.appearance)
        self.hue=QSpinBox();self.hue.setRange(0,359);form.addRow('Hue (°)',self.hue);self.gray=QCheckBox('Use a neutral gray shade');form.addRow(self.gray)
        form.addRow(QLabel('Choose a hue, or a neutral shade, and light/dark appearance.'))
        for signal in (self.appearance.currentTextChanged,self.hue.valueChanged,self.gray.toggled):signal.connect(self.simple_changed)
        palette=QWidget();form=QFormLayout(palette);self.pages.addWidget(palette)
        self.palette=QComboBox();self.palette.addItems(THEME_PALETTES);form.addRow('Palette',self.palette);self.palette.currentTextChanged.connect(self.choose_palette)
        self.colors={}
        for key,value in COLORS.items():
            edit=ColorEdit(window.theme['colors'][key]);form.addRow(key.title(),edit);edit.changed.connect(self.apply);self.colors[key]=edit
        scroll=QScrollArea();scroll.setWidgetResizable(True);advanced=QWidget();self.advanced_form=QFormLayout(advanced);scroll.setWidget(advanced);self.pages.addWidget(scroll)
        f=self.advanced_form;self.font=QFontComboBox();f.addRow('Application font',self.font);self.font_size=QSpinBox();self.font_size.setRange(10,28);f.addRow('Font size (px)',self.font_size)
        self.group_key='panel';self.group=QComboBox();self.group.addItems([key.title() for key in COLORS]);self.group.setCurrentText('Panel');f.addRow('UI group',self.group)
        self.group_color=ColorEdit(window.theme['colors']['panel']);f.addRow('Group color (RGBA)',self.group_color)
        self.surface=QComboBox();self.surface.addItems(['color','gradient','image']);f.addRow('Group appearance',self.surface)
        self.gradient=GradientEdit(window.theme['gradient']);f.addRow('Surface gradient',self.gradient)
        self.numbers={}
        for key,label,lo,hi in [('angle','Gradient angle (°)',-360,360),('speed','Gradient speed (°/s)',-360,360),('offset','Gradient offset (°)',-3600,3600),('size','Gradient size (×)',.1,16),('transparency','Surface transparency (%)',0,100)]:
            spin=QDoubleSpinBox();spin.setRange(lo,hi);spin.setDecimals(2);f.addRow(label,spin);spin.valueChanged.connect(self.apply);self.numbers[key]=spin
        self.image=ImageEdit(window.theme['image']);f.addRow('Surface image',self.image)
        for signal in (self.font.currentFontChanged,self.font_size.valueChanged,self.surface.currentTextChanged,self.gradient.changed,self.image.changed,self.group_color.changed):signal.connect(self.apply)
        self.group.currentTextChanged.connect(self.switch_group)
        row=QHBoxLayout();self.saved=QComboBox();row.addWidget(QLabel('Saved themes'));row.addWidget(self.saved,1)
        for label,fn in [('Save as…',self.save_as),('Load',self.load_saved),('Remove',self.remove)]:b=QPushButton(label);b.clicked.connect(fn);row.addWidget(b)
        layout.addLayout(row);self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        close=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);close.rejected.connect(self.reject);layout.addWidget(close)
        self.mode.currentIndexChanged.connect(self.mode_changed);self.populate(window.theme);self.refresh_saved();self.loading=False
    def populate(self,s):
        old=self.loading;self.loading=True
        self.mode.setCurrentIndex({'simple':0,'palette':1,'advanced':2}[s['mode']]);self.pages.setCurrentIndex(self.mode.currentIndex())
        self.appearance.setCurrentText(s['appearance']);self.hue.setValue(s['hue']);self.gray.setChecked(s['grayscale'])
        for key,edit in self.colors.items():edit.set_value(s['colors'][key])
        self.font.setCurrentFont(QFont(s['font']));self.font_size.setValue(s['font_size']);self.groups=deepcopy(s.get('groups',{}));self.load_group(s)
        self.loading=old;self.visibility()
    def load_group(self,s):
        old=self.loading;self.loading=True
        self.group_color.set_value(s['colors'][self.group_key]);surface=group_surface(s,self.group_key)
        self.surface.clear();self.surface.addItems(['color','gradient','image'] if self.group_key in ('window','panel') else ['color','gradient'])
        self.surface.setCurrentText(surface['surface_mode']);self.gradient.set_value(surface['gradient']);self.image.set_value(surface['image'])
        for key,spin in self.numbers.items():spin.setValue(surface[key])
        self.loading=old;self.visibility()
    def switch_group(self,name):
        if self.loading:return
        self.group_key=name.lower();self.load_group(self.window.theme)
    def visibility(self):
        mode=self.surface.currentText();surface=self.group_key in SURFACE_GROUPS
        self.advanced_form.setRowVisible(self.surface,surface)
        for widget in [self.gradient,*[self.numbers[k] for k in ('angle','speed','offset','size')]]:self.advanced_form.setRowVisible(widget,surface and mode=='gradient')
        self.advanced_form.setRowVisible(self.image,surface and mode=='image');self.advanced_form.setRowVisible(self.numbers['transparency'],surface and mode!='color')
    def mode_changed(self,index):
        self.pages.setCurrentIndex(index)
        if self.loading:return
        s=deepcopy(self.window.theme);s['mode']=['simple','palette','advanced'][index];self.window.apply_theme(s);self.load_group(s);self.apply()
    def simple_changed(self,*args):
        if self.loading or self.mode.currentIndex()!=0:return
        s=simple_theme(self.hue.value(),self.appearance.currentText(),self.gray.isChecked());self.populate(s);self.window.apply_theme(s)
    def choose_palette(self,name):
        if self.loading:return
        s=deepcopy(THEME_PALETTES[name]);s['mode']='palette';self.populate(s);self.window.apply_theme(s)
    def value(self):
        s=deepcopy(self.window.theme);s['mode']=['simple','palette','advanced'][self.mode.currentIndex()]
        s['colors']={key:edit.value() for key,edit in self.colors.items()}
        s.update(font=self.font.currentFont().family(),font_size=self.font_size.value())
        if s['mode']=='advanced':
            s['colors'][self.group_key]=self.group_color.value()
            if self.group_key in SURFACE_GROUPS:
                group=dict(surface_mode=self.surface.currentText(),gradient=self.gradient.value(),image=self.image.value())
                group.update({key:spin.value() for key,spin in self.numbers.items()})
                self.groups[self.group_key]=group;s['groups']=deepcopy(self.groups)
        return theme_spec(s)
    def apply(self,*args):
        if self.loading:return
        try:
            spec=self.value();self.window.apply_theme(spec)
            self.loading=True
            try:
                for key,edit in self.colors.items():edit.set_value(spec['colors'][key])
            finally:self.loading=False
            self.visibility();self.status.setText('Theme applied. Changes are saved for next launch.')
        except ValueError as error:self.status.setText(str(error))
    def refresh_saved(self):self.saved.clear();self.saved.addItems(sorted(self.window.theme_presets))
    def save_as(self):
        name,ok=QInputDialog.getText(self,'Save theme','Name:')
        if ok:
            try:name=valid_name(name);self.window.theme_presets[name]=self.value();self.refresh_saved();self.saved.setCurrentText(name);self.window.schedule_save()
            except ValueError as error:self.status.setText(str(error))
    def load_saved(self):
        if self.saved.currentText() in self.window.theme_presets:
            s=self.window.theme_presets[self.saved.currentText()];self.populate(s);self.window.apply_theme(s)
    def remove(self):self.window.theme_presets.pop(self.saved.currentText(),None);self.refresh_saved();self.window.schedule_save()
    def import_file(self):
        path,_=QFileDialog.getOpenFileName(self,'Import UI theme','','FireMedia themes (*.firemt)')
        if path:
            try:
                name,s=import_theme(path);name=unique_name(name,self.window.theme_presets);self.window.theme_presets[name]=s;self.refresh_saved();self.saved.setCurrentText(name);self.populate(s);self.window.apply_theme(s)
            except (OSError,ValueError) as error:self.status.setText(str(error))
    def export_file(self):
        path,_=QFileDialog.getSaveFileName(self,'Export UI theme',(self.saved.currentText() or 'My theme')+'.firemt','FireMedia themes (*.firemt)')
        if path:
            try:export_theme(path if path.lower().endswith('.firemt') else path+'.firemt',self.saved.currentText() or 'My theme',self.value());self.status.setText('Theme exported with its embedded image.')
            except (OSError,ValueError) as error:self.status.setText(str(error))
