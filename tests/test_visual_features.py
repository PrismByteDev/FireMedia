import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import base64
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from zipfile import ZipFile
from PyQt6.QtGui import QColor,QImage
from PyQt6.QtWidgets import QApplication
from firemedia.visualspec import (DEFAULT,BUILTIN_VISUALS,visual_spec,color4,gradient,gradient_color,
    embed_image,image_spec,export_visual,import_visual)
from firemedia.visualizer import Visualizer,Bar,advance_bar,AudioAnalysis
from firemedia.plugins import PluginManager,read_package

app=QApplication.instance() or QApplication([])


def package(path,id='test.plugin',script='',extra=None):
    with ZipFile(path,'w') as z:
        z.writestr('manifest.json',json.dumps({'format':'FireMediaPlugin','api':1,'id':id,'name':'Test','version':'1.0','entry':'plugin.py'}))
        z.writestr('plugin.py',script)
        for key,value in (extra or {}).items():z.writestr(key,value)
    return path


class VisualFeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.visual=Visualizer();self.visual.resize(640,360);self.visual.timer.stop();self.visual.demo=True
    def tearDown(self):self.visual.close();self.visual.deleteLater();app.processEvents();self.temp.cleanup()
    def test_requested_presets_and_color4_alpha(self):
        self.assertEqual(set(BUILTIN_VISUALS),{'Default','Classic','Frost','Amethyst','Ember','Starry'})
        for spec in BUILTIN_VISUALS.values():self.assertIn('particle_decal',visual_spec(spec))
        self.assertEqual(DEFAULT['speed'],36)
        self.assertEqual(color4('#11223380').getRgb(),(17,34,51,128))
        self.assertEqual(color4([10,20,30,40]).getRgb(),(10,20,30,40))
        self.assertEqual(color4('hsv(240,100,100,50)').blue(),255)
        self.assertAlmostEqual(color4('hsv(240,100,100,50)').alphaF(),.5,places=2)
        self.assertEqual(color4('#112233').alpha(),255)
    def test_invalid_settings_are_rejected(self):
        for change in ({'speed':float('nan')},{'emission_rate':[4,2]},{'gravity':-1},{'bars_visible':'true'},
                       {'particle_end_color':'red'},{'horizontal':[[.5,'#FFFFFF'],[.5,'#000000']]},{'background_mode':'file'}):
            with self.assertRaises(ValueError):visual_spec(change)
    def test_gradient_interpolates_rgba_and_offset_moves(self):
        stops=gradient([[0,'#00000000'],[1,'#FFFFFFFF']]);c=gradient_color(stops,.5)
        self.assertAlmostEqual(c.redF(),.5,places=3);self.assertAlmostEqual(c.alphaF(),.5,places=3)
        self.visual.configure(dict(DEFAULT,horizontal=stops));first=self.visual.horizontal_color(.1)
        self.visual.phase=2;self.assertNotEqual(first,self.visual.horizontal_color(.1))
    def image(self):
        image=QImage(20,10,QImage.Format.Format_RGBA8888);image.fill(QColor('#FF0000'))
        for x in range(10,20):
            for y in range(10):image.setPixelColor(x,y,QColor('#00FF00'))
        path=self.root/'texture.png';image.save(str(path));return path
    def test_images_embed_crop_slice_and_survive_export(self):
        path=self.image();embedded=embed_image(path);embedded.update(columns=2,cell=1,repeat_x=2,mode='stretch')
        spec=visual_spec(dict(DEFAULT,background_mode='image',background_image=embedded,particle_decal=embedded))
        output=self.root/'art.firemv';export_visual(output,'Art',spec);path.unlink()
        name,restored=import_visual(output);self.assertEqual(name,'Art');self.assertEqual(restored,spec)
        self.visual.configure(restored)
        self.assertEqual(self.visual._images['background_image'].pixelColor(1,1).name(),'#00ff00')
        self.visual.show();app.processEvents();self.visual.grab()
        for key,values in [('crop',[.6,0,.6,0]),('cell',4),('mode','invalid')]:
            with self.assertRaises(ValueError):image_spec(dict(embedded,**{key:values}))
    def test_peak_bounce_toggle_and_disabled_barline(self):
        peak=Bar(height=20,cap=25);advance_bar(peak,200,.03,peak=True)
        self.assertEqual(peak.cap_velocity,0);self.assertEqual(peak.cap,peak.height+5)
        falling=Bar(height=20,cap=26,cap_velocity=-200)
        advance_bar(falling,20,.03,bounce=False);self.assertEqual(falling.cap_velocity,0)
        disabled=Bar(cap=60,cap_velocity=-100);advance_bar(disabled,200,.03,enabled=False)
        self.assertEqual(disabled.cap,60)
        rising=Bar(height=20,cap=200,cap_velocity=500)
        advance_bar(rising,20,.03,peak=True);self.assertLess(rising.cap_velocity,0)

    def test_particle_image_start_tint_and_color_fade(self):
        embedded=embed_image(self.image());embedded.update(columns=2,cell=0,mode='stretch')
        spec=dict(DEFAULT,bars_visible=False,line_visible=False,particle_decal=embedded,particle_size=20,
                  particle_gradient_override=True,particle_gradient=[[0,'#0000FF'],[1,'#0000FF']],
                  start_vx=0,start_vy=0,fade_time=1,particle_end_override=False)
        self.visual.configure(spec);self.visual.summon_particle(100,100);self.visual.show();app.processEvents()
        pixel=self.visual.grab().toImage().pixelColor(100,100)
        self.assertGreater(pixel.blue(),200);self.assertLess(pixel.red(),10)
        self.visual.particles.clear();spec.update(particle_gradient_override=False,particle_end_override=True,particle_end_color='#0000FFFF')
        self.visual.configure(spec);self.visual.summon_particle(100,100);self.visual.particles[0].age=.5
        pixel=self.visual.grab().toImage().pixelColor(100,100)
        self.assertGreater(pixel.blue(),20);self.assertGreater(pixel.red(),20)
    def test_starry_collision_flash_fades_back_to_blue(self):
        self.visual.configure(BUILTIN_VISUALS['Starry']);self.visual.demo=False;self.visual.has_media=True
        self.visual.bars[0]=Bar(height=150,cap=155,collision_age=0)
        self.visual.show();app.processEvents()
        bright=self.visual.grab().toImage().pixelColor(20,300)
        self.visual.bars[0].collision_age=2
        normal=self.visual.grab().toImage().pixelColor(20,300)
        self.assertGreater(bright.red(),normal.red());self.assertGreater(normal.blue(),normal.red())
    def test_particle_cap_ranges_and_acceleration(self):
        self.visual.configure(dict(DEFAULT,particles_enabled=True,start_vx=10,start_vy=20,accel_vx=5,cbaccel_vx=10,expaccel_vx=2,fade_time=1,start_transparency=0,end_transparency=100))
        for _ in range(450):self.visual.summon_particle(10,20)
        self.assertEqual(len(self.visual.particles),400)
        p=self.visual.particles[0];self.visual.clock=time.monotonic()-.02;self.visual.tick()
        self.assertGreater(p.ax,5);self.assertGreater(p.x,10);self.assertLess(p.alpha,1)
        self.visual.configure(BUILTIN_VISUALS['Classic']);self.assertFalse(self.visual.particles)
        self.visual.configure(DEFAULT)
        with self.assertRaises(ValueError):self.visual.summon_particle(10,20,lifetime=float('nan'))
        self.visual.set_quality(True);self.assertFalse(self.visual.summon_particle(10,20));self.assertFalse(self.visual.particles)
    def test_every_preset_paints_and_dynamic_background_alpha(self):
        self.visual.show()
        for name,spec in BUILTIN_VISUALS.items():
            self.visual.configure(spec);self.visual.clock=time.monotonic()-.02;self.visual.tick();self.assertFalse(self.visual.grab().isNull())
        self.visual.configure(dict(DEFAULT,background_mode='color',background_color='#FF000080',background_transparency=50))
        c=self.visual.grab().toImage().pixelColor(2,2);self.assertTrue(60<=c.red()<=66);self.assertEqual(c.green(),0)
    def test_analyzer_detects_stall_without_mistaking_silence_for_failure(self):
        a=AudioAnalysis();a.enabled=True;a.cancel.clear();a.source='song.wav';a.started_at=a.last_progress=time.monotonic()-5
        self.assertTrue(a.needs_recovery(2,10))
        with a.condition:a.frames.append((2.01,[0]*64,[0]*a.WINDOW))
        self.assertFalse(a.needs_recovery(2,10))
        a.sample(2.02);self.assertFalse(a.needs_recovery(2.02,10))
        a.stop()


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.visual=Visualizer();self.visual.timer.stop()
        self.manager=PluginManager(self.visual,self.root/'plugins');self.visual.plugins=self.manager
    def wait(self,condition,timeout=3):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            app.processEvents()
            if condition():return True
            time.sleep(.003)
        return False
    def enable(self,id):
        self.manager.enable(id)
        self.assertTrue(self.wait(lambda:self.manager.plugins[id].ready or not self.manager.plugins[id].active))
        self.assertTrue(self.manager.plugins[id].ready,self.manager.plugins[id].error)
    def frame(self):
        self.manager.update_frame(self.visual.frame_snapshot())
    def tearDown(self):self.manager.close();self.visual.close();self.visual.deleteLater();app.processEvents();self.temp.cleanup()
    def test_package_does_not_execute_until_explicitly_enabled(self):
        path=package(self.root/'test.firemp',script="api.log('loaded')\n@api.on('onSubtitleMessage')\ndef message(e): api.log(e.text)\n")
        id=self.manager.install(path);self.assertFalse(self.manager.messages)
        self.enable(id);self.manager.emit_event('onSubtitleMessage',text='Hello',position=1)
        self.assertTrue(self.wait(lambda:'test.plugin: Hello' in self.manager.messages))
        self.assertIn(id,self.manager.enabled_state());self.manager.disable(id);self.assertNotIn(id,self.manager.enabled_state())
    def test_custom_visualizer_collision_particles_and_drawing(self):
        script="""def paint(e):
    e.draw.rect(0,0,e.frame.width,e.frame.height,'#FF0000')
api.registerVisualizer('red','Red canvas',paint)
@api.on('onBarCollision')
def collision(e):
    api.summonParticle(e.x,e.y,color=[255,200,100,128],vx=0,vy=10)
"""
        id=self.manager.install(package(self.root/'test.firemp',script=script));self.enable(id)
        self.manager.selected=id+':red';self.assertEqual(self.manager.choices(),[(id+':red','Red canvas')])
        self.manager.emit_event('onBarCollision',index=1,x=10,y=20,impact=100,height=50);self.assertTrue(self.wait(lambda:len(self.visual.particles)==1))
        self.frame();self.assertTrue(self.wait(lambda:bool(self.manager.plugins[id].commands)))
        self.visual.has_media=True;self.visual.show();app.processEvents();pixel=self.visual.grab().toImage().pixelColor(2,2)
        self.assertEqual(pixel.name(),'#ff0000')
    def test_failure_disables_plugin_without_disabling_others(self):
        a=self.manager.install(package(self.root/'a.firemp','test.bad',"def update(e):raise RuntimeError('oops')"))
        b=self.manager.install(package(self.root/'b.firemp','test.good',"def update(e):api.log('ok')"))
        self.enable(a);self.enable(b);self.manager.update_frame(self.visual.frame_snapshot())
        self.assertTrue(self.wait(lambda:not self.manager.plugins[a].active and 'test.good: ok' in self.manager.messages));self.assertTrue(self.manager.plugins[b].active)

    def test_plugin_exit_is_contained_and_drawing_assets_work(self):
        image=QImage(2,2,QImage.Format.Format_RGBA8888);image.fill(QColor('#00FF00'));path=self.root/'green.png';image.save(str(path))
        script="pic=api.image('assets/green.png')\ndef paint(e):e.draw.image(pic,0,0,20,20)\napi.registerVisualizer('image','Image',paint)"
        id=self.manager.install(package(self.root/'image.firemp',script=script,extra={'assets/green.png':path.read_bytes()}));self.enable(id)
        self.manager.selected=id+':image';self.frame();self.assertTrue(self.wait(lambda:bool(self.manager.plugins[id].commands)));self.visual.has_media=True;self.visual.show();app.processEvents()
        self.assertEqual(self.visual.grab().toImage().pixelColor(2,2).name(),'#00ff00')
        bad=self.manager.install(package(self.root/'exit.firemp','test.exit','def update(e):raise SystemExit(1)'))
        self.enable(bad);self.manager.update_frame(self.visual.frame_snapshot())
        self.assertTrue(self.wait(lambda:not self.manager.plugins[bad].active));self.assertTrue(self.manager.plugins[id].active)
    def test_slow_hook_is_disabled_after_return(self):
        id=self.manager.install(package(self.root/'test.firemp',script='import time\ndef update(e):time.sleep(.06)'))
        self.enable(id);self.manager.update_frame(self.visual.frame_snapshot());self.assertTrue(self.wait(lambda:not self.manager.plugins[id].active))
    def test_reject_traversal_and_duplicate_paths(self):
        path=package(self.root/'bad.firemp',extra={'../evil.py':'bad'})
        with self.assertRaises(ValueError):read_package(path)
        path=package(self.root/'bad.firemp',extra={'/evil.py':'bad'})
        with self.assertRaises(ValueError):read_package(path)
    def test_discovery_is_disabled_until_trusted_hash_is_restored(self):
        id=self.manager.install(package(self.root/'test.firemp',script="api.log('running')"));self.enable(id)
        fingerprint=self.manager.fingerprint(id);self.manager.close()
        restored=PluginManager(self.visual,self.root/'plugins');restored.discover()
        self.assertFalse(restored.plugins[id].active);self.assertEqual(restored.fingerprint(id),fingerprint)
        restored.remove(id);self.assertFalse((self.root/'plugins'/(id+'.firemp')).exists())
