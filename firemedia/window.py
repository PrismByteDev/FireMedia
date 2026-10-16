"""Native player surface, bottom effects menu, and collapsible playlist drawer."""
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlparse
import random
import time
from functools import lru_cache
from PyQt6.QtCore import Qt, QTimer, QEvent, QStandardPaths, QSize, pyqtSignal, QPropertyAnimation
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QPainter, QPixmap, QColor, QPolygonF, QShortcut, QCursor, QImage, QFont
from PyQt6.QtCore import QPointF, QItemSelectionModel
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedLayout, QSlider, QLabel, QToolButton, QMenu, QFileDialog, QDialog,
    QFormLayout, QComboBox, QCheckBox, QPushButton, QDialogButtonBox, QListWidget, QStyle, QStyleOptionSlider,
    QListWidgetItem, QAbstractItemView, QSplitter, QInputDialog, QMessageBox, QLineEdit, QFontDialog, QSpinBox, QGraphicsOpacityEffect, QDoubleSpinBox, QColorDialog)
from .backend import Player, MpvError
from .order import PlaybackOrder
from .desktop import Mpris
from .video import VideoSurface
from .subtitles import SubtitleOverlay
from .vfx import VfxSession
from .formats import (BUILTIN_PRESETS,subtitle_spec,unique_name,valid_name,matching_srt,
    export_subtitle,import_subtitle,export_app_playlist,import_app_playlist)
from .playlists import Track, expand_sources, load_state, save_state, write_playlist
from .visualizer import Visualizer, AudioAnalysis
from .visualspec import BUILTIN_VISUALS, visual_spec, color4
from .plugins import PluginManager
from .visualui import VisualSettings, PluginDialog
from .sliders import SeekSlider,VolumeSlider
from .covers import CoverLibrary,cover_directory
from .themes import DEFAULT_THEME,theme_spec,theme_css,set_theme_palette,ThemeSurface
from .themeui import ThemeDialog
from .visibility import is_presented

STYLE = '''
QMainWindow, QWidget { background: #0b0b0e; color: #ededf0; font-family: "Sans Serif"; font-size: 13px; }
QWidget#transport, QWidget#effectsBar { background: #17171c; }
QWidget#playlistPanel { background: #08080a; }
QToolButton { border: none; border-radius: 5px; padding: 7px; background: transparent; }
QToolButton:hover, QToolButton:checked { background: #36343f; }
QPushButton { background: #292830; border: 1px solid #49464f; border-radius: 4px; padding: 7px 13px; }
QPushButton:hover { background: #3b3545; }
QPushButton:disabled, QToolButton:disabled { color: #706b78; }
QSlider::groove:horizontal { background: #55545d; height: 4px; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #e5e1ed; height: 4px; border-radius: 2px; }
QSlider::handle:horizontal { background: #fff; width: 13px; margin: -5px 0; border-radius: 6px; }
QSlider#volume::sub-page:horizontal { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #58b55d,stop:.6 #cfef49,stop:1 #ff753e); }
QSlider::groove:vertical { background: #4d4955; width: 4px; }
QSlider::handle:vertical { background: #eadcf8; height: 9px; margin: 0 -6px; border-radius: 3px; }
QLabel { background: transparent; }
QLabel#timeLabel { color: #a9a4b2; font-size: 11px; }
QLabel#fullTitle { padding: 6px 12px; font-size: 18px; background: #17171c; }
QListWidget { border: none; background: #08080a; outline: none; padding: 4px 12px; }
QListWidget::item { padding: 13px 12px; border-bottom: 1px solid #1f1e25; }
QListWidget::item:selected { background: #292332; color: #e7c5ff; }
QListWidget::item:hover { background: #201d26; }
QMenu { background: #202027; border: 1px solid #4b4655; padding: 5px; }
QMenu::item { padding: 8px 28px 8px 12px; }
QMenu::item:selected { background: #473550; }
QMenu::separator { height: 1px; background: #49414e; margin: 4px; }
QDialog { background: #1b191f; }
QComboBox, QLineEdit { background: #27242d; border: 1px solid #504957; border-radius: 4px; padding: 7px; }
QComboBox QAbstractItemView { background: #29242f; selection-background-color: #574461; }
QSplitter::handle:vertical { background: #28242e; height: 5px; }
QCheckBox { spacing: 10px; }
QStatusBar { background: #26212b; color: #eed6fa; }
'''

@lru_cache(maxsize=32)
def icon(name,color="#f2eff5"):
    image = QPixmap(32,32); image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image); p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(color4(color)); p.setPen(Qt.PenStyle.NoPen)
    def triangle(points):
        p.drawPolygon(QPolygonF([QPointF(x,y) for x,y in points]))
    if name in ('play','next','previous'):
        if name == 'previous':
            triangle([(24,7),(8,16),(24,25)]); p.drawRect(5,7,3,18)
        else:
            triangle([(8,6),(25,16),(8,26)])
            if name=='next': p.drawRect(26,6,3,20)
    elif name=='pause':
        p.drawRoundedRect(8,6,5,20,1,1);p.drawRoundedRect(19,6,5,20,1,1)
    elif name in ('up','down','save','load'):
        triangle([(5,23),(16,8),(27,23)] if name in ('up','load') else [(5,9),(16,24),(27,9)])
        if name in ('save','load'): p.drawRect(4,27,24,3)
    elif name=='playlist':
        for y in (7,15,23):
            p.drawRect(3,y,4,4);p.drawRect(11,y,18,4)
    elif name=='settings':
        p.setPen(color4(color));font=p.font();font.setPointSize(23);p.setFont(font);p.drawText(image.rect(),Qt.AlignmentFlag.AlignCenter,'⚙')
    elif name=='plus':
        p.drawRect(14,5,4,22);p.drawRect(5,14,22,4)
    elif name=='volume':
        triangle([(6,12),(12,12),(20,5),(20,27),(12,20),(6,20)])
        p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(color4(color));p.drawArc(15,7,14,18,-70*16,140*16)
    elif name=='remove':
        p.drawRect(7,14,18,4)
    p.end()
    return QIcon(image)


def button(name, tooltip, callback, text=None):
    b = QToolButton();b.setObjectName(name);b.setToolTip(tooltip);b.setAccessibleName(tooltip)
    if text is None:
        b.setIcon(icon(name));b.setIconSize(QSize(28,28))
    else:
        b.setText(text)
    b.clicked.connect(callback)
    return b

class VfxDialog(QDialog):
    applying=False
    def reject(self):
        if not self.applying:super().reject()
    def closeEvent(self,event):
        if self.applying:event.ignore()
        else:super().closeEvent(event)

class Surface(QWidget):
    double_clicked = pyqtSignal()
    def mouseDoubleClickEvent(self, event):
        self.double_clicked.emit()

class PlaylistList(QListWidget):
    reordered = pyqtSignal()
    external_drop = pyqtSignal(list)
    def __init__(self):
        super().__init__()
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAccessibleName('Playlist tracks')
        self.setAlternatingRowColors(False)
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()
        else: super().dragEnterEvent(event)
    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()
        else: super().dragMoveEvent(event)
    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            self.external_drop.emit([u.toLocalFile() if u.isLocalFile() else u.toString() for u in event.mimeData().urls()])
            event.acceptProposedAction()
        else:
            super().dropEvent(event);self.reordered.emit()

class Window(QMainWindow):
    def __init__(self, state_path=None, silent=False):
        super().__init__()
        self.setWindowTitle('FireMedia')
        self.setWindowIcon(QIcon(str(Path(__file__).parent/'assets'/'firemedia.svg')))
        self.resize(1200,760);self.setMinimumSize(660,400)
        self.setAcceptDrops(True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.state_path = Path(state_path) if state_path else Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))/'state.json'
        self.state = load_state(self.state_path)
        try:self.theme=theme_spec(self.state.get('theme',DEFAULT_THEME))
        except ValueError:self.theme=theme_spec(DEFAULT_THEME)
        self.theme_presets={}
        for name,spec in self.state.get('theme_presets',{}).items():
            try:self.theme_presets[valid_name(name)]=theme_spec(spec)
            except ValueError:pass
        self.covers=CoverLibrary(self);self.covers.available.connect(self.cover_ready)
        self.queue = [Track(**t) for t in self.state.get('queue',[]) if isinstance(t,dict) and 'source' in t and 'title' in t]
        self.saved = self.state.get('playlists',{})
        self.current = None
        self.shuffle_mode = self.state.get('shuffle','Off')
        self.loop_mode = self.state.get('loop','Off')
        self.order = PlaybackOrder()
        self.ldm = self.state.get('ldm','Auto')
        self.low_detail = False
        self.power_profile = ''
        self._was_active = True
        self._analysis_key = None
        self._last_position = 0
        self._last_eq = 0
        self.gains = self.state.get('eq',[0]*6)
        self.subtitle_style = self.state.get('subtitle_style','Glow')
        self.subtitle_presets={}
        for name,spec in self.state.get('subtitle_presets',{}).items():
            try:self.subtitle_presets[valid_name(name)]=subtitle_spec(spec)
            except ValueError:pass
        try:self.subtitle_spec=subtitle_spec(self.state.get('subtitle_spec',BUILTIN_PRESETS.get(self.subtitle_style,BUILTIN_PRESETS['Glow'])))
        except ValueError:self.subtitle_spec=dict(BUILTIN_PRESETS['Glow'])
        self.autoload_subtitles=self.state.get('autoload_subtitles',True)
        self._subtitle_loaded_source=None
        self.subtitles_visible=self.state.get('subtitles_visible',True)
        self._video = False
        self._closing = False
        self._silent=silent
        self._pending_source=None
        self._build_ui();self.apply_theme(self.theme)
        self.player = Player(parent=self,silent=silent,render_api=not silent)
        if not silent:
            self.video.bind(self.player)
            self.video.ready.connect(self.video_ready)
            self.video.failed.connect(self.notify)
        self.player.changed.connect(self.sync)
        self.player.ended.connect(self.on_end)
        self.player.error.connect(self.notify)
        self.player.set('volume',self.volume.value())
        self.analysis = AudioAnalysis(self)
        self.visual.level_provider = self.analysis.sample
        self.visual.waveform_provider = self.analysis.waveform
        self.analysis.warning.connect(self.notify)
        self.set_visual_bar_count(self.state.get('bar_count',64))
        self.visual.physics = self.state.get('physics',True)
        self.visual.tension = self.state.get('tension',140)
        self.visual.intensity = self.state.get('intensity',70)
        self.visual_presets={}
        for name,spec in self.state.get('visual_presets',{}).items():
            try:
                name=valid_name(name)
                if name not in BUILTIN_VISUALS:self.visual_presets[name]=visual_spec(spec)
            except ValueError:pass
        name=self.state.get('preset','Default')
        self.visual.preset=name if name in BUILTIN_VISUALS or name in self.visual_presets else 'Default'
        fallback=self.visual_presets.get(self.visual.preset,BUILTIN_VISUALS.get(self.visual.preset,BUILTIN_VISUALS['Default']))
        try:self.visual.configure(self.state.get('visual_spec',fallback))
        except ValueError:self.visual.configure(fallback)
        self.apply_subtitle_spec(self.subtitle_spec)
        self.visual.color = self.state.get('color','Rainbow')
        self.visual.subtitle_style = self.subtitle_style
        self.visual.subtitle_size=self.state.get('subtitle_size',38)
        self.visual.subtitle_font=self.state.get('subtitle_font','Sans Serif')
        self.player.equalizer(self.gains)
        self._shortcuts()
        self.refresh_queue();self.refresh_saved()
        self.power_timer = QTimer(self);self.power_timer.setInterval(5000)
        self.power_timer.timeout.connect(self.read_power_profile);self.power_timer.start()
        self.read_power_profile()
        QApplication.instance().applicationStateChanged.connect(self.application_state)
        self.save_timer = QTimer(self);self.save_timer.setSingleShot(True);self.save_timer.setInterval(350)
        self.save_timer.timeout.connect(self.persist)
        self.plugins=PluginManager(self.visual,self.state_path.parent/'plugins',self)
        self.visual.plugins=self.plugins;self.plugins.warning.connect(self.notify);self.plugins.changed.connect(self.schedule_save)
        self.plugins.discover()
        for id,fingerprint in (self.state.get('enabled_plugins',{}) if self.state.get('plugin_security')==2 else {}).items():
            if id in self.plugins.plugins and self.plugins.fingerprint(id)==fingerprint:self.plugins.enable(id)
        selected=self.state.get('plugin_visualizer','')
        pid=selected.partition(':')[0] if isinstance(selected,str) else ''
        self.plugins.selected=selected if pid in self.plugins.plugins and self.plugins.plugins[pid].active else ''
        self.mpris=Mpris(self)
        self.overlay_timer=QTimer(self);self.overlay_timer.setInterval(80)
        self.overlay_timer.timeout.connect(self.update_control_visibility);self.overlay_timer.start()
        self.update_transport_layout()

    def _build_ui(self):
        root = ThemeSurface('window');self.setCentralWidget(root)
        layout = QVBoxLayout(root);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        self.full_header=QWidget();title_layout=QHBoxLayout(self.full_header);title_layout.setContentsMargins(10,0,10,0)
        title_icon=QLabel();title_icon.setPixmap(self.windowIcon().pixmap(26,26));title_layout.addWidget(title_icon)
        self.full_title = QLabel('FireMedia');self.full_title.setObjectName('fullTitle');title_layout.addWidget(self.full_title,1)
        self.full_header.hide();layout.addWidget(self.full_header)
        self.splitter = QSplitter(Qt.Orientation.Vertical);layout.addWidget(self.splitter)
        player_area = self.player_area = QWidget();area = self.player_layout = QVBoxLayout(player_area);area.setContentsMargins(0,0,0,0);area.setSpacing(0)
        self.surface = Surface();self.surface.double_clicked.connect(self.toggle_fullscreen)
        self.stage_stack = QStackedLayout(self.surface);self.stage_stack.setContentsMargins(0,0,0,0)
        self.visual = Visualizer()
        self.video = QWidget() if self._silent else VideoSurface()
        self.video.setStyleSheet('background: black;')
        if not self._silent: self.video.double_clicked.connect(self.toggle_fullscreen)
        # Keep the GL surface initialized even when the visualizer covers it.
        self.stage_stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        self.stage_stack.addWidget(self.visual);self.stage_stack.addWidget(self.video)
        self.subtitle_overlay=SubtitleOverlay(self.surface)
        self.subtitle_overlay.configure(self.subtitle_spec)
        self.held_image=QLabel(self.surface);self.held_image.setStyleSheet('background:black;')
        self.held_image.setAlignment(Qt.AlignmentFlag.AlignCenter);self.held_image.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents);self.held_image.hide()
        area.addWidget(self.surface,1)
        self.effects_bar = ThemeSurface();self.effects_bar.setObjectName('effectsBar')
        fx = QHBoxLayout(self.effects_bar);fx.setContentsMargins(12,8,12,5);fx.setSpacing(16)
        fx.addWidget(button('settings','Settings',self.show_settings))
        fx.addWidget(button('vfx','Video effects',self.show_video_effects,'VFX'))
        fx.addWidget(button('sfx','Audio effects and equalizer',self.show_audio_effects,'SFX'))
        fx.addWidget(button('visual','Visualizer settings',self.show_visual_settings,'Visualizer'))
        fx.addWidget(button('subtitles','Subtitle settings',self.show_subtitles,'Subtitles'))
        fx.addStretch()
        fx.addWidget(button('open','Open media or playlist',self.open_files,'Open…'))
        fx.addWidget(button('fullscreen','Toggle fullscreen (F11)',self.toggle_fullscreen,'⛶'))
        self.effects_bar.hide();area.addWidget(self.effects_bar)
        transport = self.transport = ThemeSurface();transport.setObjectName('transport')
        controls = QHBoxLayout(transport);controls.setContentsMargins(12,8,12,8);controls.setSpacing(7)
        self.expand_button = button('up','Open effects menu',self.toggle_effects);controls.addWidget(self.expand_button)
        controls.addWidget(button('previous','Previous track',self.previous))
        self.play_button = button('play','Play or pause',self.toggle_play);controls.addWidget(self.play_button)
        controls.addWidget(button('next','Next track',self.next))
        self.cover_label=QLabel('♪');self.cover_label.setFixedSize(32,32);self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter);self.cover_label.setToolTip('Song cover');controls.addWidget(self.cover_label)
        self.elapsed = QLabel('0:00');self.elapsed.setObjectName('timeLabel');controls.addWidget(self.elapsed)
        self.seek = SeekSlider(Qt.Orientation.Horizontal);self.seek.setObjectName('seek');self.seek.setAccessibleName('Playback position');self.seek.setRange(0,10000)
        self.seek.sliderReleased.connect(self.seek_to);self.seek.actionTriggered.connect(self.keyboard_seek)
        controls.addWidget(self.seek,1)
        self.duration = QLabel('0:00');self.duration.setObjectName('timeLabel');controls.addWidget(self.duration)
        controls.addSpacing(10)
        self.mute_button = button('volume','Mute audio',self.toggle_mute);controls.addWidget(self.mute_button)
        self.volume = VolumeSlider(Qt.Orientation.Horizontal);self.volume.setObjectName('volume');self.volume.setRange(0,150);self.volume.setValue(self.state.get('volume',100));self.volume.setFixedWidth(105);self.volume.setAccessibleName('Volume (up to 150%)')
        self.volume.valueChanged.connect(self.volume_changed);controls.addWidget(self.volume)
        self.volume_label = QLabel(f'{self.volume.value()}%');self.volume_label.setMinimumWidth(35);controls.addWidget(self.volume_label)
        self.playlist_button = button('playlist','Open playlist drawer',self.toggle_playlist);controls.addWidget(self.playlist_button)
        area.addWidget(transport)
        self.transport_opacity=QGraphicsOpacityEffect(transport);transport.setGraphicsEffect(self.transport_opacity)
        self.transport_animation=QPropertyAnimation(self.transport_opacity,b'opacity',self)
        self.transport_animation.setDuration(140)
        self._opacity_goal=None
        self.overlay_controls=False
        self.surface.installEventFilter(self)
        self.splitter.addWidget(player_area)
        self.playlist_panel = ThemeSurface();self.playlist_panel.setObjectName('playlistPanel')
        panel = QVBoxLayout(self.playlist_panel);panel.setContentsMargins(0,8,0,8);panel.setSpacing(4)
        top = QHBoxLayout();top.setContentsMargins(18,0,18,0)
        self.saved_combo = QComboBox();self.saved_combo.setAccessibleName('Saved playlists');self.saved_combo.setMinimumWidth(180);self.saved_combo.activated.connect(self.load_saved)
        top.addWidget(self.saved_combo,1)
        self.load_saved_button=button('loadSaved','Load selected app playlist',lambda:self.load_saved(self.saved_combo.currentIndex()),'Load');top.addWidget(self.load_saved_button)
        top.addWidget(button('save','Save named playlist',self.save_named,'Save'))
        self.delete_saved_button=button('deleteSaved','Delete selected app playlist',self.delete_saved,'Delete');top.addWidget(self.delete_saved_button)
        self.saved_combo.currentIndexChanged.connect(self.update_saved_buttons)
        top.addWidget(button('manage','Playlist actions',self.playlist_menu,'⋯'))
        panel.addLayout(top)
        search_row=QHBoxLayout();search_row.setContentsMargins(18,0,18,0)
        self.search = QLineEdit();self.search.setPlaceholderText('Filter playlist');self.search.textChanged.connect(self.filter_queue);search_row.addWidget(self.search,1)
        search_row.addWidget(button('clearPlaylist','Clear entire playlist',self.clear_queue,'Clear playlist'))
        panel.addLayout(search_row)
        self.track_list = PlaylistList();self.track_list.setIconSize(QSize(36,36));self.track_list.itemDoubleClicked.connect(self.play_item);self.track_list.reordered.connect(self.reorder_queue);self.track_list.external_drop.connect(self.add_sources)
        self.track_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);self.track_list.customContextMenuRequested.connect(self.track_context)
        panel.addWidget(self.track_list,1)
        bottom = QHBoxLayout();bottom.setContentsMargins(12,0,12,0)
        bottom.addWidget(button('settings','Settings',self.show_settings))
        self.shuffle_button = button('shuffle','Shuffle mode',self.cycle_shuffle,'Shuffle: '+self.shuffle_mode);bottom.addWidget(self.shuffle_button)
        self.loop_button = button('loop','Loop mode',self.cycle_loop,'Loop: '+self.loop_mode);bottom.addWidget(self.loop_button)
        self.count_label = QLabel();bottom.addStretch();bottom.addWidget(self.count_label)
        bottom.addWidget(button('down','Move selected tracks down',lambda:self.move_selected(1)))
        bottom.addWidget(button('up','Move selected tracks up',lambda:self.move_selected(-1)))
        bottom.addWidget(button('save','Save playlist (Shift: relative paths)',self.export_playlist))
        bottom.addWidget(button('load','Load M3U or M3U8 playlist',self.open_playlist))
        bottom.addWidget(button('remove','Remove selected tracks',self.remove_selected))
        bottom.addWidget(button('plus','Add files or playlists',self.open_files))
        panel.addLayout(bottom)
        self.splitter.addWidget(self.playlist_panel)
        self.splitter.setStretchFactor(0,3);self.splitter.setStretchFactor(1,2)
        self.playlist_panel.hide()
        self.statusBar().hide()
        self._status_timer = QTimer(self);self._status_timer.setSingleShot(True);self._status_timer.timeout.connect(self.statusBar().hide)
        self.surface.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);self.surface.customContextMenuRequested.connect(self.surface_menu)

    def _shortcuts(self):
        for key,action in [('Ctrl+O',self.open_files),('Ctrl+L',self.open_url),('Ctrl+S',self.export_playlist),
                           ('Space',self.toggle_play),('F11',self.toggle_fullscreen),('Escape',self.escape),
                           ('Ctrl+P',self.toggle_playlist),('Ctrl+,',self.show_settings),
                           ('Ctrl+Shift+S',lambda:self.export_playlist(relative=True))]:
            shortcut = QShortcut(QKeySequence(key),self);shortcut.activated.connect(action)
        self.track_list.installEventFilter(self)

    def eventFilter(self, obj, event):
        if getattr(self,'_closing',False): return False
        if obj is self.windowHandle() and event.type()==QEvent.Type.Expose and hasattr(self,'analysis'):
            self.sync()
        if obj is self.surface and event.type()==QEvent.Type.Resize:
            self.position_transport_overlay()
            self.subtitle_overlay.setGeometry(self.surface.rect());self.held_image.setGeometry(self.surface.rect())
        if obj is getattr(self,'track_list',None) and event.type()==QEvent.Type.KeyPress:
            if event.key()==Qt.Key.Key_Delete: self.remove_selected();return True
            if event.key()==Qt.Key.Key_F2: self.rename_track();return True
            if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter):
                if self.track_list.currentItem(): self.play_item(self.track_list.currentItem())
                return True
        return super().eventFilter(obj,event)

    def toggle_effects(self):
        visible = not self.effects_bar.isVisible();self.effects_bar.setVisible(visible)
        self.expand_button.setIcon(self.themed_icon('down' if visible else 'up'));self.expand_button.setToolTip('Close effects menu' if visible else 'Open effects menu')
        self.update_transport_layout()

    def toggle_playlist(self):
        visible = not self.playlist_panel.isVisible();self.playlist_panel.setVisible(visible)
        self.playlist_button.setChecked(visible)
        if visible: self.splitter.setSizes([max(240,int(self.height()*.63)),max(150,int(self.height()*.37))])
        self.update_transport_layout()

    def update_transport_layout(self):
        overlay=self.effects_bar.isHidden() and self.playlist_panel.isHidden()
        self.overlay_controls=overlay
        if overlay:
            self.player_layout.removeWidget(self.transport)
            self.transport.setParent(self.surface)
            self.transport.setStyleSheet('QWidget#transport { background: transparent; }')
            self.position_transport_overlay()
        else:
            self.transport.setParent(self.player_area)
            self.player_layout.addWidget(self.transport)
            self.transport.setStyleSheet('')
        self.transport.show();self.transport.raise_()
        self.update_control_visibility(animate=False)

    def position_transport_overlay(self):
        if not getattr(self,'overlay_controls',False): return
        height=max(56,self.transport.sizeHint().height())
        self.transport.setGeometry(0,max(0,self.surface.height()-height),self.surface.width(),height)
        self.transport.raise_()

    def update_control_visibility(self,animate=True,nearby=None):
        if not hasattr(self,'transport_opacity'): return
        if nearby is None:
            point=self.surface.mapFromGlobal(QCursor.pos())
            nearby=(0<=point.x()<self.surface.width() and self.surface.height()-120<=point.y()<self.surface.height())
        goal=1.0 if not self.overlay_controls or nearby else (0.0 if self._video else .35)
        if goal==self._opacity_goal and animate: return
        self._opacity_goal=goal
        self.transport.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,goal==0)
        self.transport_animation.stop()
        if animate:
            self.transport_animation.setStartValue(self.transport_opacity.opacity())
            self.transport_animation.setEndValue(goal);self.transport_animation.start()
        else: self.transport_opacity.setOpacity(goal)

    def video_ready(self):
        if self._pending_source:
            source=self._pending_source;self._pending_source=None
            self.player.load(source)

    def toggle_fullscreen(self):
        if self.isFullScreen(): self.showNormal();self.full_header.hide()
        else: self.showFullScreen();self.full_header.show()

    def escape(self):
        if self.isFullScreen(): self.showNormal();self.full_header.hide()
        elif self.effects_bar.isVisible(): self.toggle_effects()
        elif self.playlist_panel.isVisible(): self.toggle_playlist()

    def open_files(self):
        paths,_ = QFileDialog.getOpenFileNames(self,'Open media or playlist','',
            'Media and playlists (*.mp3 *.flac *.wav *.ogg *.opus *.m4a *.aac *.mp4 *.mkv *.webm *.mov *.avi *.m3u *.m3u8);;FireMedia plugins (*.firemp);;All files (*)')
        if paths: self.add_sources(paths)

    def open_playlist(self):
        paths,_=QFileDialog.getOpenFileNames(self,'Load playlist','','Playlists (*.m3u *.m3u8);;All files (*)')
        if paths: self.add_sources(paths,replace=True)

    def open_url(self):
        source,ok = QInputDialog.getText(self,'Open stream','HTTP(S) media or M3U8 URL:')
        if ok and source.strip():
            if urlparse(source.strip()).scheme not in ('http','https'):
                self.notify('Enter an HTTP or HTTPS URL.');return
            self.add_sources([source.strip()])

    def add_sources(self, sources, autoplay=True, replace=False):
        media=[]
        for source in sources:
            if str(source).lower().endswith('.firemp'):
                try:
                    self.plugins.install(source);self.notify('Plugin installed, disabled. Open Settings → Plugins to enable trusted scripts.')
                except (OSError,ValueError,SyntaxError) as error:self.notify(str(error))
            else:media.append(source)
        if not media:return
        try:
            additions = expand_sources(media)
        except (OSError,ValueError) as error:
            self.notify(f'Could not read playlist: {error}');return
        if not additions:
            self.notify('No playable entries found.');return
        if replace:
            self.player.command('stop');self.analysis.stop();self._analysis_key=None
            self.current=None;self.queue=[]
        start = len(self.queue);self.queue.extend(additions);self.order.reset()
        self.refresh_queue();self.schedule_save()
        if self.current is None and autoplay: self.play_index(start)

    def play_index(self, index):
        if not 0<=index<len(self.queue): return
        self.current = self.queue[index]
        self.setWindowTitle('FireMedia : '+self.current.title);self.full_title.setText(self.windowTitle())
        self.visual.has_media = True;self.visual.demo = False
        self.covers.request(self.current.source);self.update_current_cover()
        self.analysis.stop();self._analysis_key=None
        self._last_position=0
        self._subtitle_loaded_source=None
        if not self._silent and not self.video.is_ready:
            self._pending_source=self.current.source
        else: self.player.load(self.current.source)
        self.plugins.emit_event('onTrackLoad',source=self.current.source,title=self.current.title)
        self.refresh_queue()

    def play_item(self, item):
        track=item.data(Qt.ItemDataRole.UserRole)
        for i,t in enumerate(self.queue):
            if t is track: self.play_index(i);return

    def toggle_play(self):
        if not self.current:
            if self.queue: self.play_index(0)
            else: self.open_files()
        elif self.player.get('idle-active')=='yes':
            self.play_index(self.current_index())
        else: self.player.set('pause',self.player.get('pause')!='yes')

    def current_index(self):
        return next((i for i,t in enumerate(self.queue) if t is self.current),-1)

    def next(self, automatic=False):
        if not self.queue: return
        target=self.order.next(self.current_index(),len(self.queue),self.shuffle_mode,self.loop_mode,automatic)
        if target is not None: self.play_index(target)

    def previous(self):
        if self.player.number('time-pos')>3: self.player.command('seek',0,'absolute');self.restart_analysis()
        elif self.queue: self.play_index((self.current_index()-1)%len(self.queue))

    def on_end(self):
        self.analysis.stop();self._analysis_key=None;self.visual.paused=True
        self.next(automatic=True)

    def cycle_shuffle(self):
        modes=['Off','Every loop','On'];self.shuffle_mode=modes[(modes.index(self.shuffle_mode)+1)%3]
        self.order.reset();self.shuffle_button.setText('Shuffle: '+self.shuffle_mode);self.schedule_save()

    def cycle_loop(self):
        modes=['Off','Playlist','Track'];self.loop_mode=modes[(modes.index(self.loop_mode)+1)%3]
        self.loop_button.setText('Loop: '+self.loop_mode);self.schedule_save()

    def refresh_queue(self):
        self.track_list.clear()
        for track in self.queue:
            suffix=Path(urlparse(track.source).path).suffix.lstrip('.').upper() or 'STREAM'
            item=QListWidgetItem(f'{"▶  " if track is self.current else "    "}{suffix}   {track.title}')
            cover=self.covers.request(track.source);item.setIcon(cover if not cover.isNull() else QIcon.fromTheme('audio-x-generic'))
            item.setData(Qt.ItemDataRole.UserRole,track);item.setToolTip(track.source);item.setSizeHint(QSize(0,48));self.track_list.addItem(item)
            if track is self.current: self.track_list.setCurrentItem(item)
        self.count_label.setText(f'{len(self.queue)} tracks');self.filter_queue(self.search.text())

    def filter_queue(self, text):
        for i in range(self.track_list.count()):
            item=self.track_list.item(i);item.setHidden(text.casefold() not in item.text().casefold())

    def reorder_queue(self):
        self.queue=[self.track_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.track_list.count())]
        self.order.reset();self.schedule_save()

    def move_selected(self, delta):
        rows=sorted((self.track_list.row(item) for item in self.track_list.selectedItems()),reverse=delta>0)
        selected=set(rows)
        for row in rows:
            dest=row+delta
            if 0<=dest<self.track_list.count() and dest not in selected:
                item=self.track_list.takeItem(row);self.track_list.insertItem(dest,item);item.setSelected(True)
                selected.discard(row);selected.add(dest)
        self.reorder_queue()

    def remove_selected(self):
        for item in list(self.track_list.selectedItems()):
            self.track_list.takeItem(self.track_list.row(item))
        self.reorder_queue()
        self.refresh_queue()

    def refresh_saved(self):
        self.saved_combo.blockSignals(True);self.saved_combo.clear();self.saved_combo.addItem('Current playlist')
        self.saved_combo.addItems(sorted(self.saved));self.saved_combo.blockSignals(False)
        self.update_saved_buttons()

    def update_saved_buttons(self):
        selected=self.saved_combo.currentIndex()>0
        self.load_saved_button.setEnabled(selected);self.delete_saved_button.setEnabled(selected)

    def save_named(self):
        name,ok=QInputDialog.getText(self,'Save playlist','Name:',text=self.saved_combo.currentText() if self.saved_combo.currentIndex()>0 else '')
        name=name.strip()
        if ok and name:
            self.saved[name]=[asdict(t) for t in self.queue];self.refresh_saved();self.saved_combo.setCurrentText(name);self.schedule_save()

    def load_saved(self, index):
        if index==0: return
        name=self.saved_combo.itemText(index)
        self.queue=[Track(**t) for t in self.saved.get(name,[])];self.order.reset()
        self.refresh_queue();self.schedule_save()

    def export_playlist(self,checked=False,*,relative=None):
        if relative is None:
            relative=bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier)
        title='Save playlist · relative paths' if relative else 'Save playlist · full paths'
        path,_=QFileDialog.getSaveFileName(self,title,'playlist.m3u8','UTF-8 playlist (*.m3u8);;M3U playlist (*.m3u)')
        if path:
            if Path(path).suffix.lower() not in ('.m3u','.m3u8'): path+='.m3u8'
            try: write_playlist(path,self.queue,relative=relative)
            except OSError as e: self.notify(str(e))

    def track_context(self, point):
        item=self.track_list.itemAt(point)
        if item is not None:
            if not item.isSelected(): self.track_list.setCurrentItem(item)
            else: self.track_list.setCurrentItem(item,QItemSelectionModel.SelectionFlag.NoUpdate)
        menu=QMenu(self);menu.addAction('Play',lambda:self.play_item(self.track_list.currentItem()) if self.track_list.currentItem() else None)
        rename=menu.addAction('Rename track…',self.rename_track);rename.setEnabled(item is not None)
        menu.addAction('Move up',lambda:self.move_selected(-1));menu.addAction('Move down',lambda:self.move_selected(1))
        menu.addAction('Remove',self.remove_selected);menu.exec(self.track_list.mapToGlobal(point))

    def rename_track(self):
        item=self.track_list.currentItem()
        if item is None:return
        track=item.data(Qt.ItemDataRole.UserRole)
        title,ok=QInputDialog.getText(self,'Rename track','Display name:',text=track.title)
        title=title.strip()
        if not ok or not title:return
        track.title=title
        if track is self.current:
            self.setWindowTitle('FireMedia : '+title);self.full_title.setText(self.windowTitle())
            self.mpris.refresh()
        self.refresh_queue()
        for i in range(self.track_list.count()):
            if self.track_list.item(i).data(Qt.ItemDataRole.UserRole) is track:
                self.track_list.setCurrentRow(i);break
        self.schedule_save()

    def playlist_menu(self):
        menu=QMenu(self);menu.addAction('Add files or playlist…',self.open_files);menu.addAction('Add folder…',self.add_folder)
        menu.addAction('Open stream URL…',self.open_url);menu.addSeparator();menu.addAction('Save playlist…',self.save_named)
        menu.addAction('Import app playlist (.firempl)…',self.import_firempl)
        menu.addAction('Export app playlist (.firempl)…',self.export_firempl)
        menu.addAction('Load selected app playlist',lambda:self.load_saved(self.saved_combo.currentIndex()))
        menu.addAction('Update selected app playlist',self.update_saved)
        menu.addAction('Save M3U8 · full paths…',self.export_playlist)
        menu.addAction('Save M3U8 · relative paths…',lambda:self.export_playlist(relative=True))
        menu.addAction('Rename saved playlist…',self.rename_saved)
        menu.addAction('Delete saved playlist',self.delete_saved);menu.addSeparator();menu.addAction('Clear queue',self.clear_queue)
        menu.exec(self.cursor().pos())

    def export_firempl(self):
        name=self.saved_combo.currentText() if self.saved_combo.currentIndex()>0 else 'Playlist'
        tracks=[Track(**t) for t in self.saved[name]] if name in self.saved else self.queue
        path,_=QFileDialog.getSaveFileName(self,'Export app playlist',name+'.firempl','FireMedia playlists (*.firempl)')
        if path:
            try:export_app_playlist(path if path.endswith('.firempl') else path+'.firempl',name,tracks)
            except (OSError,ValueError) as e:self.notify(str(e))

    def import_firempl(self):
        path,_=QFileDialog.getOpenFileName(self,'Import app playlist','','FireMedia playlists (*.firempl)')
        if path:
            try:
                name,tracks=import_app_playlist(path);name=unique_name(name,self.saved)
                self.saved[name]=[asdict(t) for t in tracks];self.refresh_saved();self.saved_combo.setCurrentText(name);self.schedule_save()
            except (OSError,ValueError) as e:self.notify(str(e))

    def update_saved(self):
        name=self.saved_combo.currentText()
        if name in self.saved:
            self.saved[name]=[asdict(t) for t in self.queue];self.schedule_save()

    def rename_saved(self):
        old=self.saved_combo.currentText()
        if old not in self.saved: return
        name,ok=QInputDialog.getText(self,'Rename playlist','Name:',text=old)
        if ok and name.strip() and name.strip()!=old:
            self.saved[name.strip()]=self.saved.pop(old);self.refresh_saved();self.saved_combo.setCurrentText(name.strip());self.schedule_save()

    def delete_saved(self):
        name=self.saved_combo.currentText()
        if name in self.saved:
            self.saved.pop(name);self.refresh_saved();self.schedule_save()

    def clear_queue(self):
        self.player.command('stop');self.analysis.stop();self._analysis_key=None;self._pending_source=None
        self.current=None;self.queue=[];self.order.reset()
        self.visual.has_media=False;self.visual.set_levels([0.0]*self.visual.bar_count)
        self.setWindowTitle('FireMedia');self.full_title.setText('FireMedia')
        self.refresh_queue();self.schedule_save()

    def add_folder(self):
        folder=QFileDialog.getExistingDirectory(self,'Add media folder')
        if folder: self.add_sources([folder])

    def playback_menu(self):
        menu=QMenu(self)
        shuffle=menu.addMenu('Shuffle')
        for mode in ['Off','Every loop','On']:
            action=shuffle.addAction(mode);action.setCheckable(True);action.setChecked(mode==self.shuffle_mode)
            action.triggered.connect(lambda checked,m=mode:self.set_shuffle(m))
        loop=menu.addMenu('Loop')
        for mode in ['Off','Playlist','Track']:
            action=loop.addAction(mode);action.setCheckable(True);action.setChecked(mode==self.loop_mode)
            action.triggered.connect(lambda checked,m=mode:self.set_loop(m))
        menu.exec(self.cursor().pos())

    def set_shuffle(self, mode):
        self.shuffle_mode=mode;self.order.reset();self.shuffle_button.setText('Shuffle: '+mode);self.schedule_save()
    def set_loop(self, mode):
        self.loop_mode=mode;self.loop_button.setText('Loop: '+mode);self.schedule_save()

    def surface_menu(self, point):
        menu=QMenu(self);menu.addAction('Open media or playlist…',self.open_files);menu.addAction('Open stream URL…',self.open_url)
        menu.addSeparator();menu.addAction('Visualizer…',self.show_visual_settings);menu.addAction('Equalizer…',self.show_audio_effects)
        menu.addAction('Subtitles…',self.show_subtitles);menu.addAction('Settings…',self.show_settings)
        menu.addSeparator();menu.addAction('Fullscreen',self.toggle_fullscreen);menu.exec(self.surface.mapToGlobal(point))

    def dialog(self, title,dialog_type=QDialog):
        dialog=dialog_type(self);dialog.setWindowTitle(title);dialog.setMinimumWidth(390)
        layout=QVBoxLayout(dialog);form=QFormLayout();form.setSpacing(16);layout.addLayout(form)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        return dialog,form

    def slider(self, minimum, maximum, value, callback):
        widget=QWidget();layout=QHBoxLayout(widget);layout.setContentsMargins(0,0,0,0)
        slider=QSlider(Qt.Orientation.Horizontal);slider.setRange(minimum,maximum);slider.setValue(int(value))
        label=QLabel(str(int(value)));label.setFixedWidth(32)
        slider.valueChanged.connect(lambda v:(label.setText(str(v)),callback(v)))
        layout.addWidget(slider,1);layout.addWidget(label)
        return widget,slider

    def show_settings(self):
        dialog,form=self.dialog('FireMedia settings')
        themes=QPushButton('Customize themes…');themes.clicked.connect(self.show_themes);form.addRow('Appearance',themes)
        row=QWidget();options=QHBoxLayout(row);options.setContentsMargins(0,0,0,0)
        shuffle=QComboBox();shuffle.addItems(['Off','Every loop','On']);shuffle.setCurrentText(self.shuffle_mode);shuffle.currentTextChanged.connect(self.set_shuffle)
        loop=QComboBox();loop.addItems(['Off','Playlist','Track']);loop.setCurrentText(self.loop_mode);loop.currentTextChanged.connect(self.set_loop)
        options.addWidget(QLabel('Shuffle'));options.addWidget(shuffle);options.addWidget(QLabel('Loop'));options.addWidget(loop);form.addRow('Playback',row)
        mode=QComboBox();mode.addItems(['Auto','On','Off']);mode.setCurrentText(self.ldm)
        mode.currentTextChanged.connect(self.set_ldm);form.addRow('Low Detail Mode',mode)
        info=QLabel('Auto follows the Linux power-saving profile.\nOn reduces bars and particles and hides the visualizer\nwhen switching to another application.');info.setWordWrap(True);form.addRow(info)
        autoload=QCheckBox('Automatically load SRT files beside videos');autoload.setChecked(self.autoload_subtitles)
        autoload.toggled.connect(lambda v:(setattr(self,'autoload_subtitles',v),self.schedule_save()));form.addRow(autoload)
        plugins=QPushButton('Manage plugins…');plugins.clicked.connect(self.show_plugins);form.addRow('Plugins',plugins)
        visual=QPushButton('Presets, background, images…');visual.clicked.connect(self.show_visual_settings);form.addRow('Visualizer',visual)
        profile=QLabel('System profile: '+(self.power_profile or 'not available (Auto uses full detail)'));form.addRow(profile)
        dialog.exec()

    def set_ldm(self, value):
        self.ldm=value;self.apply_quality();self.schedule_save()

    def show_visual_settings(self):
        dialog=VisualSettings(self)
        try:dialog.exec()
        finally:dialog.deleteLater()

    def themed_icon(self,name):return icon(name,self.theme['colors']['text'])

    def apply_theme(self,spec):
        self.theme=theme_spec(spec);self.setStyleSheet(theme_css(self.theme));set_theme_palette(self,self.theme)
        for surface in (self.centralWidget(),self.effects_bar,self.transport,self.playlist_panel):surface.configure_theme(self.theme)
        names={'settings','play','pause','next','previous','up','down','save','load','playlist','plus','volume','remove'}
        for widget in self.findChildren(QToolButton):
            if widget.objectName() in names and not widget.icon().isNull():widget.setIcon(self.themed_icon(widget.objectName()))
        self.expand_button.setIcon(self.themed_icon('down' if self.effects_bar.isVisible() else 'up'))
        if hasattr(self,'player'):self.play_button.setIcon(self.themed_icon('pause' if self.player.loaded and self.player.get('pause')!='yes' else 'play'))
        self.schedule_save()

    def show_themes(self):
        dialog=ThemeDialog(self)
        try:dialog.exec()
        finally:dialog.deleteLater()

    def cover_ready(self,directory,image,path):
        if self._closing:return
        for i in range(self.track_list.count()):
            item=self.track_list.item(i);track=item.data(Qt.ItemDataRole.UserRole)
            if cover_directory(track.source)==directory and not image.isNull():item.setIcon(QIcon(QPixmap.fromImage(image)))
        if self.current and cover_directory(self.current.source)==directory:self.update_current_cover()

    def update_current_cover(self):
        image=self.covers.image(self.current.source) if self.current else QImage()
        self.visual.set_cover(image)
        if image.isNull():self.cover_label.clear();self.cover_label.setText('♪')
        else:self.cover_label.setPixmap(QPixmap.fromImage(image).scaled(32,32,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))

    def show_plugins(self):
        dialog=PluginDialog(self)
        try:dialog.exec()
        finally:dialog.deleteLater()

    def set_visual_bar_count(self, count):
        self.visual.set_bar_count(count)
        self.analysis.bar_count=self.visual.bar_count
        self.schedule_save()

    def show_audio_effects(self):
        dialog,form=self.dialog('Audio effects · Equalizer')
        self.eq_debounce=QTimer(dialog);self.eq_debounce.setSingleShot(True);self.eq_debounce.setInterval(120);self.eq_debounce.timeout.connect(self.apply_eq)
        sliders=[]
        for i,f in enumerate([60,170,350,1000,3500,10000]):
            def change(value,index=i):
                self.gains[index]=value;self.eq_debounce.start();self.schedule_save()
            widget,slider=self.slider(-12,12,self.gains[i],change);slider.setAccessibleName(f'{f} Hz gain in decibels');sliders.append(slider)
            form.addRow(f'{f} Hz · dB',widget)
        reset=QPushButton('Reset equalizer');reset.clicked.connect(lambda:[s.setValue(0) for s in sliders]);form.addRow(reset)
        dialog.exec();self.apply_eq()

    def apply_eq(self):
        self.player.equalizer(self.gains);self.restart_analysis()

    def show_video_effects(self):
        import numpy as np
        dialog,form=self.dialog('Video effects · still-image preview',VfxDialog)
        video=self.video if self._video and not self._silent and self.video.is_ready else None
        session=VfxSession(self.player,video,dialog)
        preview=None
        if video:
            image=video.grabFramebuffer().scaled(800,450,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
            image=image.convertToFormat(QImage.Format.Format_RGBA8888)
            bits=image.constBits();bits.setsize(image.sizeInBytes())
            preview=np.frombuffer(bits,dtype=np.uint8).reshape(image.height(),image.bytesPerLine()//4,4)[:,:image.width(),:3].astype(np.float32)/255
            video.holding=True
            self.held_image.setGeometry(self.surface.rect());self.held_image.show();self.held_image.raise_()
        status=QLabel('Adjust the still image, then Apply.');status.setWordWrap(True);form.addRow(status)
        repaint=QTimer(dialog);repaint.setSingleShot(True);repaint.setInterval(70)
        def draw_preview():
            if preview is None:return
            values=session.draft
            rgb=(preview-.5)*(2**(values['contrast']/50))+.5+values['brightness']/200
            grey=(rgb*np.array([.2126,.7152,.0722],dtype=np.float32)).sum(axis=2,keepdims=True)
            rgb=grey+(rgb-grey)*(1+values['saturation']/100)
            rgb=np.power(np.clip(rgb,0,1),1/(2**(values['gamma']/100)))
            pixels=np.ascontiguousarray((rgb*255).astype(np.uint8))
            result=QImage(pixels.data,pixels.shape[1],pixels.shape[0],pixels.shape[1]*3,QImage.Format.Format_RGB888).copy()
            pixmap=QPixmap.fromImage(result).scaled(self.surface.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
            self.held_image.setPixmap(pixmap)
        repaint.timeout.connect(draw_preview)
        sliders=[]
        for key in session.draft:
            def change(value,name=key):session.draft[name]=value;repaint.start()
            widget,slider=self.slider(-100,100,session.draft[key],change);sliders.append(slider);form.addRow(key.capitalize(),widget)
        reset=QPushButton('Reset picture');reset.clicked.connect(lambda:[slider.setValue(0) for slider in sliders]);form.addRow(reset)
        apply=QPushButton('Apply');form.addRow(apply)
        def commit():
            repaint.stop();draw_preview();apply.setEnabled(False);dialog.applying=True
            status.setText('Applying… keeping the still image until the video is ready.')
            session.apply()
        def failed(message):status.setText(message);apply.setEnabled(True);dialog.applying=False
        apply.clicked.connect(commit);session.failed.connect(failed)
        session.finished.connect(dialog.accept,Qt.ConnectionType.QueuedConnection)
        draw_preview()
        try:dialog.exec()
        finally:
            repaint.stop();session.close();self.held_image.hide()

    def apply_subtitle_spec(self,spec):
        self.subtitle_spec=subtitle_spec(spec)
        self.visual.subtitle_size=self.subtitle_spec['size'];self.visual.subtitle_font=self.subtitle_spec['font']
        self.subtitle_overlay.configure(self.subtitle_spec)
        self.player.set('sub-visibility',False)
        self.player.set('sub-delay',self.subtitle_spec['delay'])
        self.schedule_save()

    def select_subtitle_preset(self,name):
        presets={**BUILTIN_PRESETS,**self.subtitle_presets}
        if name in presets:
            self.subtitle_style=name;self.apply_subtitle_spec(presets[name])

    def save_subtitle_preset(self):
        name,ok=QInputDialog.getText(self,'Save subtitle preset','Name:',text='Custom preset')
        if ok:
            try:
                name=valid_name(name)
                if name in BUILTIN_PRESETS:raise ValueError('Choose a new name for a custom preset')
                self.subtitle_presets[name]=dict(self.subtitle_spec);self.subtitle_style=name;self.schedule_save()
            except ValueError as e:self.notify(str(e))

    def update_subtitle_preset(self):
        if self.subtitle_style in self.subtitle_presets:
            self.subtitle_presets[self.subtitle_style]=dict(self.subtitle_spec);self.schedule_save()

    def rename_subtitle_preset(self):
        old=self.subtitle_style
        if old not in self.subtitle_presets:return
        name,ok=QInputDialog.getText(self,'Rename subtitle preset','Name:',text=old)
        if ok:
            try:
                name=valid_name(name)
                if name!=old and name in {**BUILTIN_PRESETS,**self.subtitle_presets}:raise ValueError('A preset already has that name')
                self.subtitle_presets[name]=self.subtitle_presets.pop(old);self.subtitle_style=name;self.schedule_save()
            except ValueError as e:self.notify(str(e))

    def remove_subtitle_preset(self):
        if self.subtitle_style in self.subtitle_presets:
            self.subtitle_presets.pop(self.subtitle_style);self.select_subtitle_preset('Glow')

    def export_firemsub(self):
        path,_=QFileDialog.getSaveFileName(self,'Export subtitle preset',self.subtitle_style+'.firemsub','FireMedia subtitle presets (*.firemsub)')
        if path:
            try:export_subtitle(path if path.endswith('.firemsub') else path+'.firemsub',self.subtitle_style,self.subtitle_spec)
            except (OSError,ValueError) as e:self.notify(str(e))

    def import_firemsub(self):
        path,_=QFileDialog.getOpenFileName(self,'Import subtitle preset','','FireMedia subtitle presets (*.firemsub)')
        if path:
            try:
                name,spec=import_subtitle(path);name=unique_name(name,{**BUILTIN_PRESETS,**self.subtitle_presets})
                self.subtitle_presets[name]=spec;self.select_subtitle_preset(name)
            except (OSError,ValueError) as e:self.notify(str(e))

    def subtitle_preset_menu(self):
        menu=QMenu(self)
        menu.addAction('Save as custom preset…',self.save_subtitle_preset)
        for title,callback in [('Update preset',self.update_subtitle_preset),('Rename preset…',self.rename_subtitle_preset),('Remove preset',self.remove_subtitle_preset)]:
            action=menu.addAction(title,callback);action.setEnabled(self.subtitle_style in self.subtitle_presets)
        menu.addSeparator();menu.addAction('Import .firemsub…',self.import_firemsub);menu.addAction('Export .firemsub…',self.export_firemsub)
        menu.exec(self.cursor().pos())

    def customize_subtitles(self):
        dialog,form=self.dialog('Customize subtitle preset')
        def change(key,value):
            spec=dict(self.subtitle_spec);spec[key]=value;self.apply_subtitle_spec(spec)
        font=QPushButton(self.subtitle_spec['font'])
        def choose_font():
            value,ok=QFontDialog.getFont(QFont(self.subtitle_spec['font']),dialog,'Art font')
            if ok:font.setText(value.family());change('font',value.family())
        font.clicked.connect(choose_font);form.addRow('Art font',font)
        size=QSpinBox();size.setRange(16,144);size.setValue(self.subtitle_spec['size']);size.valueChanged.connect(lambda v:change('size',v));form.addRow('Font size',size)
        delay=QDoubleSpinBox();delay.setRange(-60,60);delay.setSingleStep(.1);delay.setDecimals(2);delay.setValue(self.subtitle_spec['delay']);delay.valueChanged.connect(lambda v:change('delay',v));form.addRow('Delay (seconds)',delay)
        particles=QCheckBox('Subtitle sparks');particles.setChecked(self.subtitle_spec['particles']);particles.toggled.connect(lambda v:change('particles',v));form.addRow('Particles',particles)
        gradient=QCheckBox('Use gradient');gradient.setChecked(self.subtitle_spec['gradient']);gradient.toggled.connect(lambda v:change('gradient',v));form.addRow('Gradient',gradient)
        for key,title in [('color','Text color'),('gradient_color','Gradient end'),('stroke_color','Stroke color')]:
            control=QPushButton(self.subtitle_spec[key])
            def choose(checked=False,name=key,button=control,caption=title):
                color=QColorDialog.getColor(QColor(self.subtitle_spec[name]),dialog,caption)
                if color.isValid():button.setText(color.name());change(name,color.name())
            control.clicked.connect(choose);form.addRow(title,control)
        stroke=QDoubleSpinBox();stroke.setRange(0,12);stroke.setSingleStep(.5);stroke.setValue(self.subtitle_spec['stroke_width']);stroke.valueChanged.connect(lambda v:change('stroke_width',v));form.addRow('Stroke width',stroke)
        actions=QWidget();row=QHBoxLayout(actions);row.setContentsMargins(0,0,0,0)
        for title,callback in [('Save as…',self.save_subtitle_preset),('Update',self.update_subtitle_preset),('Rename',self.rename_subtitle_preset),('Remove',self.remove_subtitle_preset)]:
            control=QPushButton(title);control.clicked.connect(lambda checked=False,fn=callback:(fn(),dialog.accept()))
            if title!='Save as…':control.setEnabled(self.subtitle_style in self.subtitle_presets)
            row.addWidget(control)
        form.addRow(actions)
        transfers=QWidget();row=QHBoxLayout(transfers);row.setContentsMargins(0,0,0,0)
        for title,callback in [('Import .firemsub…',self.import_firemsub),('Export .firemsub…',self.export_firemsub)]:
            control=QPushButton(title);control.clicked.connect(lambda checked=False,fn=callback:(fn(),dialog.accept()));row.addWidget(control)
        form.addRow(transfers);dialog.exec()

    def show_subtitles(self):
        dialog,form=self.dialog('Art subtitles')
        load=QPushButton('Load subtitle file…');load.clicked.connect(self.load_subtitles);form.addRow(load)
        preset=QComboBox()
        def refresh():
            preset.blockSignals(True);preset.clear();preset.addItems(list(BUILTIN_PRESETS)+list(self.subtitle_presets))
            if preset.findText(self.subtitle_style)<0:preset.addItem(self.subtitle_style)
            preset.setCurrentText(self.subtitle_style);preset.blockSignals(False)
        preset.currentTextChanged.connect(self.select_subtitle_preset)
        row=QWidget();layout=QHBoxLayout(row);layout.setContentsMargins(0,0,0,0);layout.addWidget(preset,1)
        manage=QPushButton('⋯');manage.clicked.connect(lambda:(self.subtitle_preset_menu(),refresh()));layout.addWidget(manage);form.addRow('Preset',row)
        customize=QPushButton('Customize…');customize.clicked.connect(lambda:(self.customize_subtitles(),refresh()));form.addRow(customize)
        visible=QCheckBox('Show subtitles');visible.setChecked(self.subtitles_visible);visible.toggled.connect(lambda v:(setattr(self,'subtitles_visible',v),self.schedule_save()));form.addRow(visible)
        tracks=QComboBox();tracks.addItem('None','no')
        try:
            import json
            for track in json.loads(self.player.get('track-list','[]')):
                if track.get('type')=='sub':tracks.addItem(track.get('title') or track.get('lang') or f'Subtitle {track["id"]}',str(track['id']))
        except (ValueError,KeyError):pass
        tracks.setCurrentIndex(max(0,tracks.findData(self.player.get('sid'))))
        tracks.activated.connect(lambda i:self.player.set('sid',tracks.itemData(i)));form.addRow('Subtitle track',tracks)
        refresh();dialog.exec()

    def set_subtitle_size(self,value):
        spec=dict(self.subtitle_spec);spec['size']=value;self.apply_subtitle_spec(spec)

    def choose_subtitle_font(self):
        font,ok=QFontDialog.getFont(QFont(self.subtitle_spec['font']),self,'Art font')
        if ok:
            spec=dict(self.subtitle_spec);spec['font']=font.family();self.apply_subtitle_spec(spec)

    def load_subtitles(self):
        path,_=QFileDialog.getOpenFileName(self,'Load subtitles','','Subtitles (*.srt *.ass *.ssa *.vtt *.sub);;All files (*)')
        if path:self.player.command('sub-add',path,'select')

    def set_subtitle_style(self,style):self.select_subtitle_preset(style)

    def volume_changed(self, value):
        self.volume_label.setText(f'{value}%')
        if hasattr(self,'player'): self.player.set('volume',value);self.schedule_save()

    def toggle_mute(self):
        muted=self.player.get('mute')!='yes';self.player.set('mute',muted);self.mute_button.setText('×' if muted else '');self.mute_button.setIcon(QIcon() if muted else icon('volume'))

    @staticmethod
    def format_time(seconds):
        seconds=max(0,int(seconds));return f'{seconds//60}:{seconds%60:02d}'

    def seek_to(self):
        duration=self.player.number('duration')
        if duration: self.player.command('seek',self.seek.value()/10000*duration,'absolute');self.restart_analysis(self.seek.value()/10000*duration)

    def keyboard_seek(self, action):
        if not self.seek.isSliderDown(): QTimer.singleShot(0,self.seek_to)

    def sync(self):
        if self._closing: return
        playing=self.player.loaded and self.player.get('pause')!='yes'
        self.play_button.setIcon(self.themed_icon('pause' if playing else 'play'))
        position=self.player.number('time-pos');duration=self.player.number('duration')
        self.analysis.set_clock(position,playing)
        self.elapsed.setText(self.format_time(position));self.duration.setText(self.format_time(duration))
        self.seek.setEnabled(duration>0)
        if not self.seek.isSliderDown():
            self.seek.blockSignals(True);self.seek.setValue(int(position/duration*10000) if duration else 0);self.seek.blockSignals(False)
        video=bool(self.player.get('video-format')) and self.player.get('video-format') not in ('no','none')
        if video!=self._video:
            self._video=video;self.stage_stack.setCurrentWidget(self.video if video else self.visual)
            self.visual.setVisible(not video and not (self.low_detail and not self._was_active))
            self.transport.raise_();self.update_control_visibility()
        self.visual.paused=not playing
        playback=(playing,self.player.loaded)
        if playback!=getattr(self,'_plugin_playback',None):
            self._plugin_playback=playback;self.plugins.emit_event('onPlaybackState',playing=playing,loaded=self.player.loaded,position=position)
        self.visual.subtitle=''
        text=self.player.get('sub-text')
        self.subtitle_overlay.set_text(text if self.subtitles_visible else '')
        if text!=getattr(self,'_plugin_subtitle_text',''):
            self._plugin_subtitle_text=text;self.plugins.emit_event('onSubtitleMessage',text=text,position=position)
        subtitle=(self.player.load_generation,self.player.get('sid'),self.player.get('current-tracks/sub/external-filename'))
        if subtitle!=getattr(self,'_plugin_subtitle',None):
            self._plugin_subtitle=subtitle
            if subtitle[1] not in ('','no','none','auto'):
                self.plugins.emit_event('onSubtitleLoad',track=subtitle[1],source=subtitle[2],media=self.current.source if self.current else '')
        self.subtitle_overlay.raise_()
        if self.held_image.isVisible():self.held_image.raise_()
        self.transport.raise_()
        if self.player.loaded and self.current and self._subtitle_loaded_source!=(self.current.source,self.player.load_generation):
            self._subtitle_loaded_source=(self.current.source,self.player.load_generation)
            self.apply_subtitle_spec(self.subtitle_spec)
            if video and self.autoload_subtitles:
                sidecar=matching_srt(self.current.source)
                if sidecar:self.player.command('sub-add',str(sidecar),'select')
        allowed=playing and not video and is_presented(self.visual) and not (self.low_detail and not self._was_active)
        self.analysis.enabled=allowed
        key=(self.current.source,self.player.load_generation,self.visual.bar_count) if self.current and allowed else None
        if key!=self._analysis_key:
            self._analysis_key=key
            if key: self.analysis.start(key[0],position,self.gains)
            else: self.analysis.stop()
        # Streaming seeks/chapters made by the backend also restart FFT at the correct time.
        if key and (abs(position-self._last_position)>1.5 or self.analysis.needs_recovery(position,duration)):
            self.analysis.start(key[0],position,self.gains)
        self._last_position=position
        self.refresh_effect_activity()

    def restart_analysis(self, position=None):
        if self.current and self.analysis.enabled:
            position=self.player.number('time-pos') if position is None else position
            self.analysis.set_clock(position,self.player.get('pause')!='yes')
            self.analysis.start(self.current.source,position,self.gains)

    def read_power_profile(self):
        self.power_profile=''
        try:
            from PyQt6.QtDBus import QDBusInterface,QDBusConnection
            for service,path in [('org.freedesktop.UPower.PowerProfiles','/org/freedesktop/UPower/PowerProfiles'),('net.hadess.PowerProfiles','/net/hadess/PowerProfiles')]:
                interface=QDBusInterface(service,path,service,QDBusConnection.systemBus())
                if interface.isValid():
                    profile=interface.property('ActiveProfile')
                    if profile: self.power_profile=str(profile);break
        except (ImportError,RuntimeError): pass
        self.apply_quality()

    def apply_quality(self):
        self.low_detail=self.ldm=='On' or (self.ldm=='Auto' and self.power_profile=='power-saver')
        self.visual.set_quality(self.low_detail)
        self.subtitle_overlay.low_detail=self.low_detail
        self.subtitle_overlay.refresh_animation()
        self.visual.setVisible(not (self.low_detail and not self._was_active) and not self._video)
        self.refresh_effect_activity()

    def refresh_effect_activity(self):
        hidden=self._closing or not is_presented(self)
        suspended=hidden or (self.low_detail and not self._was_active) or self._video
        self.visual.suspend(suspended)
        if suspended and hasattr(self,'analysis'):
            self.analysis.enabled=False
            if not self.analysis.cancel.is_set():self.analysis.stop()
            self._analysis_key=None
        self.subtitle_overlay.refresh_animation()
        for surface in self.findChildren(ThemeSurface):surface.refresh_animation()
        if hasattr(self,'overlay_timer'):
            if hidden:
                self.overlay_timer.stop();self.transport_animation.stop()
            elif not self.overlay_timer.isActive():self.overlay_timer.start()

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type()==QEvent.Type.WindowStateChange and hasattr(self,'analysis'):
            self.refresh_effect_activity()
            if not self.isMinimized():self.sync()

    def hideEvent(self,event):
        super().hideEvent(event)
        if hasattr(self,'analysis'):self.refresh_effect_activity()

    def showEvent(self,event):
        super().showEvent(event)
        handle=self.windowHandle()
        if handle is not None:handle.installEventFilter(self)
        if hasattr(self,'analysis'):self.sync()

    def application_state(self, state):
        self._was_active=state==Qt.ApplicationState.ApplicationActive
        self.apply_quality()

    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()
    def dropEvent(self,event):
        self.add_sources([u.toLocalFile() if u.isLocalFile() else u.toString() for u in event.mimeData().urls()]);event.acceptProposedAction()

    def notify(self,message):
        self.statusBar().show();self.statusBar().showMessage(str(message));self._status_timer.start(6500)

    def schedule_save(self):
        if hasattr(self,'save_timer') and not self._closing: self.save_timer.start()

    def persist(self):
        state={'queue':[asdict(t) for t in self.queue],'playlists':self.saved,'shuffle':self.shuffle_mode,
               'loop':self.loop_mode,'ldm':self.ldm,'volume':self.volume.value(),'eq':self.gains,
               'bar_count':self.visual.bar_count,'physics':self.visual.physics,'tension':self.visual.tension,'intensity':self.visual.intensity,
               'preset':self.visual.preset,'color':self.visual.color,'subtitle_style':self.subtitle_style,
               'visual_spec':self.visual.spec,'visual_presets':self.visual_presets,
               'enabled_plugins':self.plugins.enabled_state(),'plugin_security':2,'plugin_visualizer':self.plugins.selected,
               'theme':self.theme,'theme_presets':self.theme_presets,
               'subtitle_size':self.visual.subtitle_size,'subtitle_font':self.visual.subtitle_font,
               'subtitle_spec':self.subtitle_spec,'subtitle_presets':self.subtitle_presets,'autoload_subtitles':self.autoload_subtitles,'subtitles_visible':self.subtitles_visible}
        try: save_state(self.state_path,state)
        except OSError as e: self.notify(f'Could not save player state: {e}')

    def closeEvent(self,event):
        self._closing=True
        self.save_timer.stop();self.overlay_timer.stop();self.power_timer.stop();self.visual.timer.stop();self.subtitle_overlay.timer.stop()
        self.player.timer.stop()
        self.persist();self.plugins.close();self.covers.close();self.mpris.close();self.analysis.stop();
        if not self._silent: self.video.shutdown()
        self.player.close();event.accept()
