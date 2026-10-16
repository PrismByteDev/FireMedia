"""Themes, cover art, visualizer channels/layers, sliders, and OS mod boundaries."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
import json,math,time,tempfile,unittest,subprocess,base64,sys
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
from PyQt6.QtCore import Qt,QPoint,QTimer
from PyQt6.QtGui import QImage,QColor,QPalette
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication,QToolButton,QTabWidget,QLabel
from firemedia.window import Window
from firemedia.visualizer import Visualizer,Bar,advance_bar
from firemedia.visualspec import DEFAULT,visual_spec,embed_image,export_visual,import_visual,gradient_color
from firemedia.visualui import VisualSettings
from firemedia.themeui import ThemeDialog
from firemedia.themes import DEFAULT_THEME,simple_theme,theme_spec,theme_css,export_theme,import_theme,group_surface
from firemedia.plugins import PluginManager
from firemedia.covers import read_cover
from firemedia.sliders import VolumeSlider

app=QApplication.instance() or QApplication([])

def wait(condition,timeout=4):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        app.processEvents()
        if condition():return True
        time.sleep(.003)
    return False


def mod(path,id,source):
    with ZipFile(path,'w') as z:
        z.writestr('manifest.json',json.dumps({'format':'FireMediaPlugin','api':1,'id':id,'name':id,'version':'1'}));z.writestr('plugin.py',source)
    return path


class ExtendedVisualTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.v=Visualizer();self.v.timer.stop();self.v.resize(640,360);self.v.has_media=True
    def tearDown(self):self.v.close();self.v.deleteLater();app.processEvents();self.temp.cleanup()
    def test_legacy_presets_migrate_to_four_independent_channels(self):
        spec=visual_spec(dict(DEFAULT,start_vx=123,particles_enabled=True))
        self.assertEqual(len(spec['channels']),4);self.assertEqual(spec['channels'][0]['start_vx'],123)
        self.assertEqual([c['particles_enabled'] for c in spec['channels']],[True,False,False,False])
        spec['channels'][1].update(particles_enabled=True,start_vx=-200,start_vy=0)
        self.v.configure(spec);self.v.summon_particle(20,100,channel=2);self.assertEqual(self.v.particles[0].vx,-200)
        self.assertEqual(self.v.particles[0].channel,1);self.assertEqual(self.v.channels[0]['start_vx'],123)
        out=self.root/'channels.firemv';export_visual(out,'Channels',spec);self.assertEqual(import_visual(out)[1],visual_spec(spec))
        with self.assertRaises(ValueError):visual_spec(dict(DEFAULT,channels=[{}]*5))
    def test_four_channels_share_cap_and_fog_is_separate(self):
        s=visual_spec(DEFAULT)
        for c in s['channels']:c['particles_enabled']=True
        s.update(fog_enabled=True,fog_emission=2);self.v.configure(s)
        for i in range(500):self.v.summon_particle(i,100,channel=i%4+1)
        self.assertEqual(len(self.v.particles),400);self.v.spawn_fog(100)
        self.assertEqual(len(self.v.fog),2);self.assertEqual(len(self.v.particles),400)
        for _ in range(100):self.v.spawn_fog(50)
        self.assertEqual(len(self.v.fog),96)
        self.v.set_quality(True);self.assertFalse(self.v.fog);self.assertFalse(self.v.particles)
    def test_fog_origin_and_lifetime_follow_collision(self):
        self.v.configure(dict(DEFAULT,fog_enabled=True,fog_emission=1,fog_lifetime=.2));self.v.paused=False;self.v.levels=[1]*64
        self.v.clock=time.monotonic()-.01;self.v.tick();self.assertGreater(len(self.v.fog),0)
        self.assertAlmostEqual(self.v.fog[0]['y'],self.v.height()-5,delta=1)
        self.v.levels=[0]*64;self.v.paused=True
        for _ in range(20):self.v.clock=time.monotonic()-.05;self.v.tick()
        self.assertFalse(self.v.fog)
    def test_resize_clears_old_geometry_and_spawns_at_new_baseline(self):
        self.v.show();app.processEvents();self.v.timer.stop()
        self.v.configure(dict(DEFAULT,fog_enabled=True,fog_emission=1));self.v.paused=False;self.v.levels=[1]*64
        for width,height in ((960,540),(480,270),(720,270)):
            self.v.summon_particle(500,300);self.v.spawn_fog(100);self.v.bars[0].cap=500
            self.v.resize(width,height)
            self.assertFalse(self.v.particles);self.assertFalse(self.v.fog);self.assertEqual(self.v.bars[0].cap,0)
            self.v.clock=time.monotonic()-.01;self.v.tick()
            self.assertTrue(self.v.fog);self.assertAlmostEqual(self.v.fog[0]['y'],height-5,delta=1)
            self.assertTrue(all(0<=p['x']<=width for p in self.v.fog))
    def test_subtitle_resize_clears_old_sparks(self):
        from firemedia.subtitles import SubtitleOverlay
        from PyQt6.QtCore import QRectF
        overlay=SubtitleOverlay(self.v);self.v.show();overlay.show();app.processEvents()
        overlay.sparks=[[100,100,20,1]];overlay.bounds=QRectF(10,10,30,30);overlay.resize(400,200)
        self.assertFalse(overlay.sparks);self.assertTrue(overlay.bounds.isEmpty())
    def test_gradient_size_multiplier_samples_correct_parts(self):
        s=dict(DEFAULT,speed=0,offset=0,size=2);self.v.configure(s)
        self.assertEqual(self.v.horizontal_color(.125),gradient_color(self.v.spec['horizontal'],.25))
        self.assertEqual(self.v.horizontal_color(.125),self.v.horizontal_color(.625))
        self.v.configure(dict(s,size=.5));self.assertEqual(self.v.horizontal_color(.5),gradient_color(self.v.spec['horizontal'],.25))
    def test_wave_is_a_pcm_trace_without_generated_motion_or_fill(self):
        s=dict(DEFAULT,bars_visible=False,line_visible=False,wave_enabled=True,wave_mode='solid',wave_color='#FF0000FF',wave_height=10,wave_transparency=0,background_mode='off')
        self.v.configure(s);self.v.waveform=[0,.5,-.5,0];self.v.show();app.processEvents()
        image=self.v.grab().toImage()
        self.assertGreater(image.pixelColor(213,162).red(),150)
        self.assertEqual(image.pixelColor(213,330).red(),0)  # no filled area
        self.v.phase=37;self.assertEqual(image,self.v.grab().toImage())  # no procedural motion
        self.v.waveform=[0]*1024;image=self.v.grab().toImage()
        self.assertEqual(image.pixelColor(213,162).red(),0)
        self.assertGreater(image.pixelColor(213,180).red(),150)  # silence is flat
        self.v.configure(dict(s,wave_mode='gradient',wave_size=2));self.assertFalse(self.v.grab().isNull())
        self.assertEqual(DEFAULT['wave_mode'],'solid');self.assertEqual(DEFAULT['wave_color'],'#FFFFFF33')
    def test_cover_background_and_modes(self):
        image=QImage(10,10,QImage.Format.Format_RGB32);image.fill(QColor('red'));self.v.set_cover(image)
        self.v.configure(dict(DEFAULT,background_mode='cover',cover_mode='stretch',bars_visible=False,line_visible=False));self.v.show();app.processEvents()
        self.assertEqual(self.v.grab().toImage().pixelColor(2,2).name(),'#ff0000')
        self.v.set_cover(QImage());self.assertFalse(self.v.grab().isNull())
    def test_launch_height_bounds_zero_and_different_gravity(self):
        for height in (0,20,120,300):
            bar=Bar(height=0,cap=5);maximum=0
            for i in range(180):
                advance_bar(bar,100,1/120,gravity=1000,spring=2,launch_height=height)
                maximum=max(maximum,bar.cap-105)
            self.assertLessEqual(maximum,height+.001)
            if height:self.assertGreater(maximum,height*.8)
            else:self.assertEqual(maximum,0)


class ThemeCoverUITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.w=Window(self.root/'state.json',silent=True)
    def tearDown(self):self.w.close();app.processEvents();self.temp.cleanup()
    def test_theme_modes_portable_image_and_restart(self):
        image=QImage(16,8,QImage.Format.Format_RGBA8888);image.fill(QColor('#77BBFF'));path=self.root/'theme.png';image.save(str(path))
        s=simple_theme(200,'light');s.update(mode='advanced',surface_mode='image',image=embed_image(path),font='Sans Serif',font_size=16)
        out=self.root/'mine.firemt';export_theme(out,'Mine',s);path.unlink();name,loaded=import_theme(out)
        self.assertEqual(name,'Mine');self.assertEqual(loaded,theme_spec(s));self.w.apply_theme(loaded);self.w.persist()
        restored=Window(self.root/'state.json',silent=True)
        try:
            self.assertEqual(restored.theme,loaded);self.assertFalse(restored.transport.image.isNull())
            self.assertEqual(restored.palette().color(QPalette.ColorRole.Text),QColor('#16121C'))
        finally:restored.close()
        with self.assertRaises(ValueError):theme_spec(dict(s,font='Sans"; background:url(/etc/passwd);'))
        with self.assertRaises(ValueError):theme_spec(dict(s,size=float('nan')))
    def test_theme_editor_changes_simple_palette_and_advanced(self):
        dialog=ThemeDialog(self.w)
        try:
            dialog.appearance.setCurrentText('light');dialog.hue.setValue(90);self.assertEqual(self.w.theme['appearance'],'light')
            dialog.mode.setCurrentIndex(1);dialog.palette.setCurrentText('Ocean');self.assertEqual(self.w.theme['mode'],'palette')
            dialog.mode.setCurrentIndex(2);dialog.surface.setCurrentText('gradient');dialog.numbers['size'].setValue(2)
            self.assertEqual(group_surface(self.w.theme,'panel')['size'],2);self.assertEqual(group_surface(self.w.theme,'panel')['surface_mode'],'gradient')
            dialog.surface.setCurrentText('color');self.assertTrue(dialog.gradient.isHidden())
        finally:dialog.close();dialog.deleteLater()
    def test_fog_row_click_toggles_setting_and_warns_when_ldm_suppresses_it(self):
        self.w.show();app.processEvents();dialog=VisualSettings(self.w);dialog.show();tabs=dialog.findChild(QTabWidget);tabs.setCurrentIndex(3);app.processEvents()
        try:
            self.w.visual.set_quality(True)
            checkbox=dialog.widgets['fog_enabled'][1];QTest.mouseClick(checkbox,Qt.MouseButton.LeftButton)
            self.assertTrue(checkbox.isChecked());self.assertTrue(self.w.visual.spec['fog_enabled'])
            self.assertIn('Low Detail Mode',dialog.status.text())
            self.w.visual.set_quality(False);self.w.visual.paused=False;self.w.visual.level_provider=None;self.w.visual.levels=[1]*64
            self.w.visual.clock=time.monotonic()-.01;self.w.visual.tick();self.assertTrue(self.w.visual.fog)
            QTest.mouseClick(checkbox,Qt.MouseButton.LeftButton);self.assertFalse(self.w.visual.spec['fog_enabled']);self.assertFalse(self.w.visual.fog)
        finally:dialog.close();dialog.deleteLater()
    def test_advanced_groups_are_independent_and_portable(self):
        dialog=ThemeDialog(self.w)
        try:
            dialog.mode.setCurrentIndex(2);dialog.group.setCurrentText('Panel');dialog.surface.setCurrentText('gradient');dialog.numbers['size'].setValue(2)
            dialog.group.setCurrentText('Window');dialog.group_color.text.setText('#102030FF');dialog.surface.setCurrentText('color')
            dialog.group.setCurrentText('Control');dialog.group_color.text.setText('#223344FF');dialog.surface.setCurrentText('gradient');dialog.numbers['offset'].setValue(90)
            dialog.group.setCurrentText('Text');dialog.group_color.text.setText('#EEEEEEFF');self.assertTrue(dialog.surface.isHidden())
            dialog.group.setCurrentText('Panel');self.assertEqual(dialog.surface.currentText(),'gradient');self.assertEqual(dialog.numbers['size'].value(),2)
            s=dialog.value();self.assertEqual(s['colors']['window'],'#102030FF');self.assertEqual(s['colors']['control'],'#223344FF')
            self.assertEqual(group_surface(s,'control')['offset'],90);self.assertEqual(group_surface(s,'window')['surface_mode'],'color')
            out=self.root/'groups.firemt';export_theme(out,'Groups',s);self.assertEqual(import_theme(out)[1],s)
            dialog.mode.setCurrentIndex(1);dialog.colors['panel'].text.setText('#445566FF');dialog.mode.setCurrentIndex(2)
            self.assertEqual(dialog.group_color.value(),'#445566FF')
        finally:dialog.close();dialog.deleteLater()
    def test_light_theme_styles_scroll_pages_tabs_and_labels(self):
        from firemedia.window import STYLE
        old=app.styleSheet();app.setStyleSheet(STYLE);self.w.apply_theme(simple_theme(275,'light'))
        dialog=VisualSettings(self.w);dialog.show();app.processEvents()
        try:
            image=dialog.grab().toImage();tabs=dialog.findChild(QTabWidget);page=tabs.widget(0).widget()
            point=page.mapTo(dialog,QPoint(100,page.height()-30));pixel=image.pixelColor(point)
            self.assertGreater(pixel.lightnessF(),.5)  # no inherited black viewport
            label=next(w for w in page.findChildren(QLabel) if w.text()=='Background')
            self.assertLess(label.palette().color(QPalette.ColorRole.WindowText).lightnessF(),.3)
            tabs.setCurrentIndex(1);app.processEvents();self.assertFalse(dialog.grab().isNull())
        finally:dialog.close();dialog.deleteLater();app.setStyleSheet(old)
    def test_cover_discovery_queue_icon_and_switch(self):
        first=self.root/'one';second=self.root/'two';first.mkdir();second.mkdir();a=first/'song.wav';b=second/'song.wav';a.touch();b.touch()
        image=QImage(40,40,QImage.Format.Format_RGBA8888);image.fill(QColor('blue'));image.save(str(first/'CoVeR.PNG'))
        found,path=read_cover(first);self.assertFalse(found.isNull());self.assertTrue(path.endswith('CoVeR.PNG'))
        self.w.add_sources([str(a),str(b)],autoplay=False)
        self.assertTrue(wait(lambda:not self.w.track_list.item(0).icon().isNull() and self.w.covers.cache.get(str(first)) is not None))
        self.w.current=self.w.queue[0];self.w.update_current_cover();self.assertFalse(self.w.visual.cover.isNull())
        self.w.current=self.w.queue[1];self.w.update_current_cover();self.assertTrue(self.w.visual.cover.isNull())
    def test_particle_channel_editor_preserves_other_channels_and_hidden_rows(self):
        dialog=VisualSettings(self.w)
        try:
            dialog.channel_select.setCurrentIndex(2);dialog.widgets['particles_enabled'][1].setChecked(True)
            editor=dialog.widgets['start_vx'][1];editor.ranged.setChecked(False);editor.minimum.setValue(250)
            self.assertEqual(self.w.visual.spec['channels'][2]['start_vx'],250)
            self.assertEqual(self.w.visual.spec['channels'][0]['start_vx'],[-30,30])
            dialog.channel_select.setCurrentIndex(0);self.assertEqual(dialog.widgets['start_vx'][1].value(),[-30,30])
            dialog.widgets['background_mode'][1].setCurrentText('cover');self.assertFalse(dialog.widgets['cover_mode'][1].isHidden());self.assertTrue(dialog.widgets['background_gradient'][1].isHidden())
            self.assertIn('launch_height',dialog.widgets)
        finally:dialog.close();dialog.deleteLater()
    def test_volume_uses_fixed_gradient_and_transparent_background(self):
        parent=self.w.transport;self.w.show();self.w.toggle_effects();app.processEvents();v=self.w.volume
        v.setValue(150);app.processEvents();full=v.grab().toImage()
        v.setValue(38);app.processEvents();part=v.grab().toImage()
        option,groove,handle=v.geometry_parts();start=groove.left()+handle.width()/2;end=groove.right()-handle.width()/2+1
        x=round(start+(end-start)*.12);y=v.height()//2
        self.assertEqual(full.pixelColor(x,y),part.pixelColor(x,y))
        x=round(start+(end-start)*.7);self.assertNotEqual(full.pixelColor(x,y),part.pixelColor(x,y))
        self.assertEqual(part.pixelColor(1,1).alpha(),0)
    def test_both_gears_open_same_settings(self):
        buttons=[b for b in self.w.findChildren(QToolButton) if b.objectName()=='settings']
        self.assertEqual(len(buttons),2);opened=[]
        from PyQt6.QtWidgets import QApplication,QLabel
        def close():
            dialog=QApplication.activeModalWidget();opened.append(dialog.windowTitle());dialog.reject()
        for b in buttons:QTimer.singleShot(0,close);b.click()
        self.assertEqual(opened,['FireMedia settings','FireMedia settings'])

    def test_custom_renderer_selection_survives_async_restart(self):
        path=mod(self.root/'renderer.firemp','test.renderer',"def paint(e):e.draw.rect(0,0,10,10,'#FFFFFF')\napi.registerVisualizer('bars','Custom bars',paint)")
        id=self.w.plugins.install(path);self.w.plugins.enable(id);self.assertTrue(wait(lambda:self.w.plugins.plugins[id].ready))
        self.w.plugins.selected=id+':bars';self.w.persist();restored=Window(self.root/'state.json',silent=True)
        try:
            self.assertEqual(restored.plugins.selected,id+':bars')
            self.assertTrue(wait(lambda:restored.plugins.plugins[id].ready));self.assertEqual(restored.plugins.selected,id+':bars')
        finally:restored.close()


class RestrictedModTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.v=Visualizer();self.v.timer.stop();self.manager=PluginManager(self.v,self.root/'plugins');self.v.plugins=self.manager
    def tearDown(self):self.manager.close();self.v.close();self.v.deleteLater();app.processEvents();self.temp.cleanup()
    def enable(self,source):
        id=self.manager.install(mod(self.root/'test.firemp','test.restricted',source));self.manager.enable(id)
        self.assertTrue(wait(lambda:self.manager.plugins[id].ready or not self.manager.plugins[id].active));return id
    def test_kernel_blocks_files_network_shell_and_native_bypasses(self):
        secret=self.root/'secret.txt';secret.write_text('private secret');output=self.root/'shell-output'
        source=f'''import os,socket,subprocess,ctypes
for name,fn in [
 ('read',lambda:open({str(secret)!r}).read()),
 ('write',lambda:open({str(output)!r},'w')),
 ('directory',lambda:os.listdir('/')),
 ('network',lambda:socket.socket()),
 ('shell',lambda:subprocess.run(['/bin/sh','-c','echo broken > {output}'])),
 ('asset',lambda:api.asset('../../secret.txt'))]:
 try:
  fn();api.log(name+' ALLOWED')
 except Exception as e:api.log(name+' denied')
libc=ctypes.CDLL(None,use_errno=True)
libc.open.argtypes=[ctypes.c_char_p,ctypes.c_int]
result=libc.open(b'/etc/passwd',0)
api.log('native denied' if result==-1 and ctypes.get_errno()==1 else 'native ALLOWED')
result=os.system('echo broken > {output}')
api.log('system denied' if result!=0 else 'system ALLOWED')
'''
        id=self.enable(source);self.assertTrue(self.manager.plugins[id].ready,self.manager.plugins[id].error)
        logs='\n'.join(self.manager.messages)
        for name in ('read','write','directory','network','shell','asset','native','system'):self.assertIn(name+' denied',logs)
        self.assertNotIn('ALLOWED',logs);self.assertFalse(output.exists());self.assertEqual(secret.read_text(),'private secret')
    def test_mod_response_from_old_size_cannot_restore_particles_or_drawing(self):
        self.v.show();app.processEvents();self.v.timer.stop()
        id=self.enable("def paint(e):\n e.draw.rect(0,0,10,10,'#FFFFFF')\n api.summonParticle(100,100)\napi.registerVisualizer('bars','Delayed',paint)")
        p=self.manager.plugins[id];self.manager.selected=id+':bars';self.manager.update_frame(self.v.frame_snapshot())
        self.assertTrue(p.busy);self.v.resize(900,500)
        self.assertTrue(wait(lambda:not p.busy));self.assertFalse(p.commands);self.assertFalse(self.v.particles)
        self.manager.update_frame(self.v.frame_snapshot());self.assertTrue(wait(lambda:not p.busy))
        self.assertTrue(p.commands);self.assertTrue(self.v.particles)
        self.manager.update_frame(self.v.frame_snapshot());self.v.suspend(True);self.v.suspend(False);self.v.timer.stop()
        self.assertTrue(wait(lambda:not p.busy));self.assertFalse(p.commands);self.assertFalse(self.v.particles)
        self.v.suspend(True);self.assertFalse(p.commands);self.assertFalse(self.v.particles)
        self.manager.update_frame(self.v.frame_snapshot());self.assertFalse(p.busy)
    def test_stuck_python_mod_does_not_block_ui(self):
        id=self.enable('def update(e):\n while True:pass')
        beats=[];timer=QTimer();timer.setInterval(10);timer.timeout.connect(lambda:beats.append(1));timer.start()
        self.manager.update_frame(self.v.frame_snapshot())
        self.assertTrue(wait(lambda:not self.manager.plugins[id].active,2));timer.stop();self.assertGreater(len(beats),5)
        self.assertIn('timed out',self.manager.plugins[id].error)
    def test_unsupported_platform_fails_closed(self):
        path=mod(self.root/'x.firemp','test.closed',"api.log('must not execute')");id=self.manager.install(path)
        with patch('firemedia.plugins.sys.platform','win32'):self.manager.enable(id)
        self.assertFalse(self.manager.plugins[id].active);self.assertFalse(self.manager.plugins[id].process)
        self.assertNotIn('must not execute','\n'.join(self.manager.messages))

    def test_missing_sandbox_library_does_not_execute_entry(self):
        output=self.root/'must-not-exist';worker=Path(__file__).resolve().parents[1]/'firemedia/mod_worker.py'
        wrapper=f"import runpy,json; ns=runpy.run_path({str(worker)!r}); ns['main'].__globals__['ctypes'].util.find_library=lambda name:None\ntry: ns['main']()\nexcept BaseException as e: print(json.dumps({{'error':str(e)}}))"
        code=f"open({str(output)!r},'w').write('unsafe')".encode()
        data=json.dumps({'entry':'plugin.py','files':{'plugin.py':base64.b64encode(code).decode()}})+'\n'
        result=subprocess.run([sys.executable,'-I','-S','-c',wrapper],input=data,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
        self.assertIn('libseccomp2',result.stdout);self.assertFalse(output.exists())

    def test_svg_assets_are_rejected_before_host_decoding(self):
        self.v.has_media=True;self.v.show();app.processEvents();self.v.timer.stop()
        source="pic=api.image('external.svg')\ndef paint(e):e.draw.image(pic,0,0,100,100)\napi.registerVisualizer('svg','SVG',paint)"
        path=mod(self.root/'svg.firemp','test.svg',source)
        with ZipFile(path,'a') as z:z.writestr('external.svg','<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><image href="file:///etc/passwd"/></svg>')
        id=self.manager.install(path);self.manager.enable(id);self.assertTrue(wait(lambda:self.manager.plugins[id].ready))
        self.manager.selected=id+':svg';self.manager.update_frame(self.v.frame_snapshot());self.assertTrue(wait(lambda:bool(self.manager.plugins[id].commands)))
        self.v.has_media=True;self.v.show();app.processEvents();self.v.grab()
        self.assertFalse(self.manager.plugins[id].active);self.assertIn('raster PNG',self.manager.plugins[id].error)
