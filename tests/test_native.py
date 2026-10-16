"""Exercise the native widgets and real libmpv/FFmpeg decoding offscreen."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import time
import unittest
import wave
from pathlib import Path
import numpy as np
from PyQt6.QtCore import QMimeData, QUrl, Qt
from PyQt6.QtGui import QDropEvent
from PyQt6.QtWidgets import QApplication
from firemedia.window import Window,STYLE

app=QApplication.instance() or QApplication([])
app.setStyleSheet(STYLE)

def wait_until(condition,timeout=4):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        app.processEvents()
        if condition(): return True
        time.sleep(.01)
    return False

class NativeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.audio=self.root/'tone.wav'
        samples=(np.sin(np.arange(44100*4)*2*np.pi*440/44100)*10000).astype('<i2')
        with wave.open(str(self.audio),'wb') as f:
            f.setparams((1,2,44100,0,'NONE',''));f.writeframes(samples.tobytes())
        self.window=Window(self.root/'state.json',silent=True);self.window.show();app.processEvents()
    def tearDown(self):
        self.window.close();app.processEvents();self.temp.cleanup()
    def test_layout_and_drawer(self):
        w=self.window
        self.assertFalse(w.effects_bar.isVisible());self.assertFalse(w.playlist_panel.isVisible())
        w.toggle_effects();w.toggle_playlist();app.processEvents()
        self.assertTrue(w.effects_bar.isVisible());self.assertTrue(w.playlist_panel.isVisible())
        self.assertLess(w.visual.height(),w.height()-150)
        w.toggle_effects();self.assertFalse(w.effects_bar.isVisible())
    def test_m3u8_import_playback_eq_seek_and_analysis(self):
        p=self.root/'mix.m3u8';p.write_text('#EXTM3U\n#EXTINF:4,Actual native audio test\ntone.wav\n')
        w=self.window;errors=[];w.player.error.connect(errors.append)
        w.add_sources([str(p)])
        self.assertTrue(wait_until(lambda:w.player.loaded),'libmpv must decode the file')
        self.assertTrue(wait_until(lambda:w.player.number('time-pos')>.15))
        self.assertTrue(wait_until(lambda:max(w.visual.levels)>.1),'FFmpeg FFT must receive real PCM')
        w.gains=[3,-2,0,1,0,-1];w.apply_eq();app.processEvents()
        self.assertIn('equalizer',w.player.get('af'))
        w.seek.setValue(5000);w.seek_to()
        self.assertTrue(wait_until(lambda:w.player.number('time-pos')>1.5))
        w.toggle_play();self.assertTrue(wait_until(lambda:w.player.get('pause')=='yes'))
        self.assertFalse(errors,errors)
    def test_drag_drop_and_reorder(self):
        w=self.window
        mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(self.audio))])
        from PyQt6.QtCore import QPointF
        event=QDropEvent(QPointF(20,20),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        w.dropEvent(event)
        self.assertEqual(len(w.queue),1)
        w.add_sources([str(self.audio)],autoplay=False)
        w.track_list.clearSelection();w.track_list.item(1).setSelected(True)
        original=w.queue[1];w.move_selected(-1);self.assertIs(w.queue[0],original)
    def test_ldm_unfocused_hides_visualizer_and_stops_work(self):
        w=self.window;w.set_ldm('On');self.assertTrue(w.low_detail)
        self.assertEqual(w.visual.timer.interval(),33)
        w.application_state(Qt.ApplicationState.ApplicationInactive)
        self.assertFalse(w.visual.isVisible());self.assertFalse(w.visual.timer.isActive())
        w.application_state(Qt.ApplicationState.ApplicationActive)
        self.assertTrue(w.visual.isVisible());self.assertTrue(w.visual.timer.isActive())
        w.set_ldm('Off');self.assertFalse(w.low_detail)
        w.power_profile='power-saver';w.set_ldm('Auto');self.assertTrue(w.low_detail)
    def test_minimize_and_hide_suspend_effects_in_full_detail_without_pausing_audio(self):
        from copy import deepcopy
        from firemedia.themes import DEFAULT_THEME,ThemeSurface
        w=self.window;w.set_ldm('Off');theme=deepcopy(DEFAULT_THEME);theme.update(mode='advanced',surface_mode='gradient',speed=36);w.apply_theme(theme)
        w.add_sources([str(self.audio)])
        self.assertTrue(wait_until(lambda:w.analysis.last_timestamp is not None))
        self.assertTrue(w.centralWidget().timer.isActive())
        for hide,restore in ((w.showMinimized,w.showNormal),(w.hide,w.show)):
            hide();app.processEvents();phase=w.visual.phase;position=w.player.number('time-pos')
            self.assertFalse(w.visual.timer.isActive());self.assertTrue(w.analysis.cancel.is_set());self.assertFalse(w.analysis.enabled)
            self.assertFalse(w.subtitle_overlay.timer.isActive());self.assertFalse(w.overlay_timer.isActive())
            self.assertTrue(all(not s.timer.isActive() for s in w.findChildren(ThemeSurface)))
            # Quality and theme updates must not wake invisible animation.
            w.apply_quality();w.apply_theme(theme);w.visual.tick()
            self.assertEqual(w.visual.phase,phase);self.assertFalse(w.visual.timer.isActive())
            self.assertTrue(all(not s.timer.isActive() for s in w.findChildren(ThemeSurface)))
            self.assertTrue(wait_until(lambda:w.player.number('time-pos')>position+.12))
            self.assertEqual(w.visual.phase,phase);self.assertNotEqual(w.player.get('pause'),'yes')
            restore();app.processEvents()
            self.assertTrue(wait_until(lambda:w.visual.timer.isActive() and w.analysis.last_timestamp is not None))
            self.assertTrue(w.centralWidget().timer.isActive());self.assertTrue(w.overlay_timer.isActive())
            self.assertLess(abs(w.player.number('time-pos')-w.analysis.last_timestamp),.3)
    def test_unexposed_window_stops_effects_even_without_minimized_flag(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from copy import deepcopy
        from firemedia.themes import DEFAULT_THEME,ThemeSurface
        w=self.window;w.set_ldm('Off');theme=deepcopy(DEFAULT_THEME);theme.update(surface_mode='gradient',speed=36);w.apply_theme(theme)
        self.assertFalse(w.isMinimized());self.assertTrue(w.visual.timer.isActive())
        with patch.object(w,'windowHandle',return_value=SimpleNamespace(isExposed=lambda:False)):
            w.sync();w.apply_quality();w.apply_theme(theme)
            self.assertFalse(w.visual.timer.isActive());self.assertFalse(w.overlay_timer.isActive())
            self.assertTrue(w.analysis.cancel.is_set())
            self.assertTrue(all(not s.timer.isActive() for s in w.findChildren(ThemeSurface)))
        w.sync();self.assertTrue(w.visual.timer.isActive());self.assertTrue(w.centralWidget().timer.isActive())
    def test_supplied_logo_and_six_drawer_actions(self):
        self.assertFalse(self.window.windowIcon().pixmap(128,128).isNull())
        from PyQt6.QtWidgets import QToolButton
        actions=[b.toolTip() for b in self.window.playlist_panel.findChildren(QToolButton)]
        self.assertEqual(actions[-6:],[
            'Move selected tracks down','Move selected tracks up',
            'Save playlist (Shift: relative paths)','Load M3U or M3U8 playlist',
            'Remove selected tracks','Add files or playlists'])

    def test_custom_bar_count_and_ldm_preserve_preference(self):
        w=self.window
        for count in (8,96,256):
            w.set_visual_bar_count(count)
            self.assertEqual(w.visual.effective_bar_count,count)
            self.assertEqual(w.analysis.bar_count,count)
            self.assertEqual(len(w.visual.bars),count)
            w.visual.tick();w.visual.grab()
        w.set_ldm('On');self.assertEqual(w.visual.effective_bar_count,24)
        w.set_ldm('Off');self.assertEqual(w.visual.effective_bar_count,256)
        w.set_visual_bar_count(8);w.set_ldm('On')
        self.assertEqual(w.visual.effective_bar_count,8)

    def test_150_percent_volume_and_custom_count_restore(self):
        w=self.window;w.volume.setValue(150);w.set_visual_bar_count(128);w.persist()
        self.assertEqual(w.volume.maximum(),150)
        self.assertEqual(w.player.number('volume'),150)
        restored=Window(self.root/'state.json',silent=True)
        try:
            self.assertEqual(restored.volume.value(),150)
            self.assertEqual(restored.player.number('volume'),150)
            self.assertEqual(restored.visual.bar_count,128)
        finally: restored.close()

    def test_startup_after_qt_adopts_non_c_numeric_locale(self):
        import locale
        from firemedia.backend import Player
        numeric=locale.setlocale(locale.LC_NUMERIC)
        other=locale.setlocale(locale.LC_TIME)
        try:
            for name in ('en_US.utf8','en_DK.utf8','en_US.UTF-8','de_DE.UTF-8'):
                try: locale.setlocale(locale.LC_NUMERIC,name)
                except locale.Error: continue
                player=Player(silent=True)
                try:
                    self.assertTrue(player.handle)
                    self.assertEqual(locale.setlocale(locale.LC_NUMERIC),'C')
                    self.assertEqual(locale.setlocale(locale.LC_TIME),other)
                finally: player.close()
                break
            else: self.skipTest('No non-C locale installed')
        finally: locale.setlocale(locale.LC_NUMERIC,numeric)

    def test_particle_cap_is_400(self):
        from unittest.mock import patch
        v=self.window.visual;v.level_provider=None;v.set_bar_count(256);v.paused=False;v.levels=[1.0]*256;v.intensity=100
        with patch('firemedia.visualizer.random.random',return_value=0):
            for _ in range(8): v.tick()
        self.assertEqual(v.MAX_PARTICLES,400)
        self.assertEqual(len(v.particles),400)

    def test_playlist_drop_concatenates_and_resolves_relative_paths(self):
        w=self.window;w.add_sources([str(self.audio)])
        self.assertTrue(wait_until(lambda:w.player.loaded))
        current=w.current
        sub=self.root/'lists';sub.mkdir();playlist=sub/'mix.m3u8'
        playlist.write_text('#EXTM3U\n../tone.wav\n../tone.wav\n')
        mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(playlist))])
        from PyQt6.QtCore import QPointF
        event=QDropEvent(QPointF(20,20),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        w.track_list.dropEvent(event)
        self.assertEqual(len(w.queue),3)
        self.assertIs(w.current,current)
        self.assertTrue(all(t.source==str(self.audio) for t in w.queue))

    def test_saved_playlists_can_be_updated_loaded_and_deleted(self):
        from unittest.mock import patch
        w=self.window;w.add_sources([str(self.audio)],autoplay=False)
        with patch('firemedia.window.QInputDialog.getText',return_value=('Mix',True)): w.save_named()
        w.add_sources([str(self.audio)],autoplay=False);w.update_saved()
        self.assertEqual(len(w.saved['Mix']),2)
        w.clear_queue();self.assertEqual(w.queue,[])
        w.load_saved(w.saved_combo.findText('Mix'))
        self.assertEqual(len(w.queue),2)
        w.delete_saved();self.assertNotIn('Mix',w.saved)
        self.assertEqual(len(w.queue),2);self.assertTrue(self.audio.exists())

    def test_shift_save_writes_relative_paths(self):
        from unittest.mock import patch
        w=self.window;w.add_sources([str(self.audio)],autoplay=False)
        for shifted in (False,True):
            path=self.root/('relative.m3u8' if shifted else 'full.m3u8')
            modifier=Qt.KeyboardModifier.ShiftModifier if shifted else Qt.KeyboardModifier.NoModifier
            with patch('firemedia.window.QApplication.keyboardModifiers',return_value=modifier), patch('firemedia.window.QFileDialog.getSaveFileName',return_value=(str(path),'')):
                w.export_playlist()
            self.assertEqual(path.read_text().splitlines()[-1],'tone.wav' if shifted else str(self.audio))

    def test_clear_playlist_stops_playback_but_preserves_saved_lists(self):
        w=self.window;w.add_sources([str(self.audio)])
        self.assertTrue(wait_until(lambda:w.player.loaded))
        w.saved['Keep']=[];w.clear_queue()
        self.assertTrue(wait_until(lambda:not w.player.loaded))
        self.assertIsNone(w.current);self.assertEqual(w.queue,[])
        self.assertIn('Keep',w.saved);self.assertTrue(self.audio.exists())

    def test_overlay_controls_fade_and_panels_restore_solid_layout(self):
        w=self.window
        self.assertTrue(w.overlay_controls);self.assertIs(w.transport.parent(),w.surface)
        w.update_control_visibility(animate=False,nearby=False)
        self.assertEqual(w.transport_opacity.opacity(),.35)
        w._video=True;w.update_control_visibility(animate=False,nearby=False)
        self.assertEqual(w.transport_opacity.opacity(),0)
        w.update_control_visibility(animate=False,nearby=True)
        self.assertEqual(w.transport_opacity.opacity(),1)
        w.toggle_effects()
        self.assertFalse(w.overlay_controls);self.assertIs(w.transport.parent(),w.player_area)
        self.assertEqual(w.transport_opacity.opacity(),1)
        w.toggle_effects();w.toggle_playlist()
        self.assertFalse(w.overlay_controls)
        w.toggle_playlist();self.assertTrue(w.overlay_controls)

    def test_subtitle_presets_and_firemsub_persist_roundtrip(self):
        from unittest.mock import patch
        from firemedia.formats import BUILTIN_PRESETS
        w=self.window;spec=dict(BUILTIN_PRESETS['Glow'],delay=1.25,particles=True,stroke_color='#123456')
        w.apply_subtitle_spec(spec)
        with patch('firemedia.window.QInputDialog.getText',return_value=('Art',True)):w.save_subtitle_preset()
        path=self.root/'art.firemsub'
        with patch('firemedia.window.QFileDialog.getSaveFileName',return_value=(str(path),'')):w.export_firemsub()
        w.remove_subtitle_preset();self.assertNotIn('Art',w.subtitle_presets)
        with patch('firemedia.window.QFileDialog.getOpenFileName',return_value=(str(path),'')):w.import_firemsub()
        self.assertEqual(w.subtitle_style,'Art');self.assertEqual(w.subtitle_spec,spec)
        with patch('firemedia.window.QInputDialog.getText',return_value=('Renamed',True)):w.rename_subtitle_preset()
        w.autoload_subtitles=False;w.persist()
        restored=Window(self.root/'state.json',silent=True)
        try:
            self.assertEqual(restored.subtitle_spec,spec)
            self.assertIn('Renamed',restored.subtitle_presets)
            self.assertFalse(restored.autoload_subtitles)
        finally:restored.close()

    def test_firempl_import_export_library_without_replacing_queue(self):
        from unittest.mock import patch
        w=self.window;w.add_sources([str(self.audio)],autoplay=False)
        with patch('firemedia.window.QInputDialog.getText',return_value=('Mix',True)):w.save_named()
        path=self.root/'mix.firempl'
        with patch('firemedia.window.QFileDialog.getSaveFileName',return_value=(str(path),'')):w.export_firempl()
        with patch('firemedia.window.QFileDialog.getOpenFileName',return_value=(str(path),'')):w.import_firempl()
        self.assertEqual(len(w.queue),1)
        self.assertIn('Mix (2)',w.saved)
        self.assertEqual(w.saved['Mix (2)'][0]['source'],str(self.audio))

    def test_rename_track_persists_and_exports_without_renaming_file(self):
        from unittest.mock import patch
        from PyQt6.QtTest import QTest
        from firemedia.formats import import_app_playlist
        w=self.window;w.add_sources([str(self.audio)])
        original=w.current;w.track_list.setCurrentRow(0)
        with patch('firemedia.window.QInputDialog.getText',return_value=('My custom title',True)):
            QTest.keyClick(w.track_list,Qt.Key.Key_F2)
        self.assertIs(w.current,original)
        self.assertEqual(w.current.title,'My custom title')
        self.assertEqual(w.current.source,str(self.audio));self.assertTrue(self.audio.is_file())
        self.assertEqual(w.windowTitle(),'FireMedia : My custom title')
        if hasattr(w.mpris,'player'):
            self.assertEqual(w.mpris.player.Metadata['xesam:title'],'My custom title')
        with patch('firemedia.window.QInputDialog.getText',return_value=('Mix',True)):w.save_named()
        path=self.root/'custom.firempl'
        with patch('firemedia.window.QFileDialog.getSaveFileName',return_value=(str(path),'')):w.export_firempl()
        self.assertEqual(import_app_playlist(path)[1][0].title,'My custom title')
        w.persist();restored=Window(self.root/'state.json',silent=True)
        try:
            self.assertEqual(restored.queue[0].title,'My custom title')
            restored.load_saved(restored.saved_combo.findText('Mix'))
            self.assertEqual(restored.queue[0].title,'My custom title')
        finally:restored.close()

    def test_cancel_or_blank_track_rename_keeps_title(self):
        from unittest.mock import patch
        w=self.window;w.add_sources([str(self.audio)],autoplay=False);w.track_list.setCurrentRow(0)
        for answer in [('Ignored',False),('   ',True)]:
            with patch('firemedia.window.QInputDialog.getText',return_value=answer):w.rename_track()
            self.assertEqual(w.queue[0].title,'tone')

    def test_seek_by_clicking_away_from_handle(self):
        from PyQt6.QtCore import QPoint
        from PyQt6.QtTest import QTest
        w=self.window;w.add_sources([str(self.audio)])
        self.assertTrue(wait_until(lambda:w.player.loaded and w.player.number('duration')>0))
        w.player.set('pause',True);w.toggle_effects();app.processEvents()
        QTest.mouseClick(w.seek,Qt.MouseButton.LeftButton,pos=QPoint(round(w.seek.width()*.75),w.seek.height()//2))
        self.assertTrue(wait_until(lambda:2.5<w.player.number('time-pos')<3.5))
        self.assertEqual(w.player.get('pause'),'yes')

    def test_visualizer_recovers_after_failed_decoder_start(self):
        from unittest.mock import patch
        import subprocess,time
        original=subprocess.Popen;attempts=[]
        def spawn(*args,**kwargs):
            attempts.append(1)
            if len(attempts)==1:raise OSError('temporary decoder startup failure')
            return original(*args,**kwargs)
        w=self.window
        with patch('firemedia.visualizer.subprocess.Popen',side_effect=spawn):
            w.add_sources([str(self.audio)])
            self.assertTrue(wait_until(lambda:bool(attempts)))
            self.assertTrue(wait_until(lambda:w.analysis.worker and not w.analysis.worker.is_alive()))
            w.analysis.started_at=w.analysis.last_progress=time.monotonic()-5
            w.sync()
            self.assertTrue(wait_until(lambda:max(w.visual.levels)>.1))
            self.assertGreaterEqual(len(attempts),2)
            self.assertEqual(w.player.get('pause'),'no')

    def test_visual_presets_editor_images_and_library_persist(self):
        from unittest.mock import patch
        from firemedia.visualui import VisualSettings
        from firemedia.visualspec import embed_image,import_visual
        from PyQt6.QtGui import QImage,QColor
        w=self.window;dialog=VisualSettings(w)
        try:
            dialog.presets.setCurrentText('Starry')
            self.assertTrue(w.visual.spec['collision_tint'])
            self.assertEqual(w.visual.preset,'Starry')
            image=QImage(8,8,QImage.Format.Format_RGBA8888);image.fill(QColor('#88CCFF'));path=self.root/'particle.png';image.save(str(path))
            dialog.widgets['particle_decal'][1].set_value(embed_image(path),True)
            dialog.widgets['background_mode'][1].setCurrentText('gradient')
            with patch('firemedia.visualui.QInputDialog.getText',return_value=('Night sky',True)):dialog.save_as()
            self.assertIn('Night sky',w.visual_presets)
            dialog.widgets['speed'][1].setValue(12);dialog.save()
            exported=self.root/'night.firemv'
            with patch('firemedia.visualui.QFileDialog.getSaveFileName',return_value=(str(exported),'')):dialog.export_file()
            self.assertEqual(import_visual(exported)[1]['speed'],12)
            path.unlink();w.persist();restored=Window(self.root/'state.json',silent=True)
            try:
                self.assertEqual(restored.visual.spec['speed'],12)
                self.assertEqual(restored.visual.spec['background_mode'],'gradient')
                self.assertIn('particle_decal',restored.visual_presets['Night sky'])
                self.assertFalse(restored.visual._images['particle_decal'].isNull())
            finally:restored.close()
            with patch('firemedia.visualui.QInputDialog.getText',return_value=('Renamed sky',True)):dialog.rename()
            self.assertIn('Renamed sky',w.visual_presets);dialog.remove();self.assertNotIn('Renamed sky',w.visual_presets)
        finally:dialog.close();dialog.deleteLater()

    def test_plugin_subtitle_events_and_changed_package_autostart(self):
        import json
        from zipfile import ZipFile
        from unittest.mock import patch
        path=self.root/'observer.firemp'
        def make(script):
            with ZipFile(path,'w') as z:
                z.writestr('manifest.json',json.dumps({'format':'FireMediaPlugin','api':1,'id':'test.observer','name':'Observer','version':'1'}))
                z.writestr('plugin.py',script)
        make("def onSubtitleLoad(e):api.log('loaded '+str(e.track))\ndef onSubtitleMessage(e):api.log('text '+e.text)")
        w=self.window;id=w.plugins.install(path);w.plugins.enable(id);self.assertTrue(wait_until(lambda:w.plugins.plugins[id].ready))
        original=w.player.get
        def get(key,default=''):
            return {'sid':'1','current-tracks/sub/external-filename':'captions.srt','sub-text':'Hello'}.get(key,original(key,default))
        with patch.object(w.player,'get',side_effect=get):w.sync();w.sync()
        self.assertTrue(wait_until(lambda:'test.observer: text Hello' in w.plugins.messages))
        self.assertEqual(list(w.plugins.messages).count('test.observer: text Hello'),1)
        self.assertIn('test.observer: loaded 1',w.plugins.messages)
        w.persist();first=Window(self.root/'state.json',silent=True)
        try:self.assertTrue(wait_until(lambda:first.plugins.plugins[id].ready))
        finally:first.close()
        make("api.log('changed')")
        (w.plugins.directory/(id+'.firemp')).write_bytes(path.read_bytes())
        # Saving an active old plugin must not grant new on-disk code autostart.
        w.persist();second=Window(self.root/'state.json',silent=True)
        try:self.assertFalse(second.plugins.plugins[id].active)
        finally:second.close()

    def test_subtitle_dialog_uses_preset_and_customize(self):
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QLabel,QPushButton
        found=[]
        def inspect():
            dialog=QApplication.activeModalWidget()
            found.extend(label.text() for label in dialog.findChildren(QLabel))
            found.extend(button.text() for button in dialog.findChildren(QPushButton))
            dialog.reject()
        QTimer.singleShot(0,inspect);self.window.show_subtitles()
        self.assertIn('Preset',found);self.assertIn('Customize…',found);self.assertNotIn('Style',found)

    def test_srt_autoload_can_be_disabled_and_reenabled(self):
        import subprocess,json
        video=self.root/'movie.mp4'
        subprocess.run(['ffmpeg','-nostdin','-loglevel','error','-f','lavfi','-i','color=blue:s=160x90:r=2','-t','2','-c:v','libx264',str(video)],check=True)
        video.with_suffix('.srt').write_text('1\n00:00:00,000 --> 00:00:01,900\nSidecar test\n')
        w=self.window;w.autoload_subtitles=False;w.add_sources([str(video)])
        self.assertTrue(wait_until(lambda:w.player.loaded and w._video))
        self.assertFalse(any(t['type']=='sub' for t in json.loads(w.player.get('track-list','[]'))))
        w.autoload_subtitles=True;w.play_index(0)
        self.assertTrue(wait_until(lambda:any(t['type']=='sub' for t in json.loads(w.player.get('track-list','[]')))))
        self.assertTrue(wait_until(lambda:'Sidecar test' in w.subtitle_overlay.text))
        w.play_index(0)
        self.assertTrue(wait_until(lambda:w.player.loaded and any(t['type']=='sub' for t in json.loads(w.player.get('track-list','[]')))))
        self.assertEqual(len([t for t in json.loads(w.player.get('track-list','[]')) if t['type']=='sub']),1)

    def test_saved_state(self):
        w=self.window;w.add_sources([str(self.audio)],autoplay=False);w.set_ldm('On');w.persist()
        from firemedia.playlists import load_state
        state=load_state(self.root/'state.json')
        self.assertEqual(state['ldm'],'On');self.assertEqual(state['queue'][0]['source'],str(self.audio))

if __name__=='__main__': unittest.main()
