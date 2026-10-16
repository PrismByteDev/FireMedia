"""Render the feature UI using generated cover artwork and demo spectrum."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import sys,time,tempfile
import numpy as np
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QImage,QPainter,QLinearGradient,QColor
from PyQt6.QtWidgets import QApplication,QTabWidget
from firemedia.window import Window
from firemedia.visualspec import BUILTIN_VISUALS,PALETTES,visual_spec
from firemedia.visualui import VisualSettings
from firemedia.themeui import ThemeDialog
from firemedia.themes import simple_theme

app=QApplication([]);root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as d:
    d=Path(d);cover=QImage(512,512,QImage.Format.Format_RGB32);p=QPainter(cover)
    g=QLinearGradient(0,0,512,512);g.setColorAt(0,QColor('#152253'));g.setColorAt(.5,QColor('#3659A7'));g.setColorAt(1,QColor('#7645A4'));p.fillRect(cover.rect(),g)
    p.setPen(QColor('#5DBCD5'));p.drawEllipse(QPointF(256,256),160,160);p.drawEllipse(QPointF(256,256),100,100);p.end();cover.save(str(d/'cover.png'))
    song=d/'Demo spectrum.flac';song.touch();w=Window(d/'state.json',silent=True);w.resize(1200,760);w.apply_theme(simple_theme(215));w.show();w.toggle_playlist();w.toggle_effects()
    w.add_sources([str(song)],autoplay=False);w.current=w.queue[0];w.refresh_queue();w.visual.has_media=True;w.visual.demo=True
    # PCM fixture for documentation; the running player receives samples from AudioAnalysis.
    samples=np.arange(1024)/22050;w.visual.waveform=.65*np.sin(samples*2*np.pi*110)+.15*np.sin(samples*2*np.pi*330)
    s=visual_spec(BUILTIN_VISUALS['Starry']);s.update(background_mode='cover',background_transparency=60,wave_enabled=True,wave_height=10,fog_enabled=True)
    s['channels'][1].update(particles_enabled=True,particle_gradient_override=True,particle_gradient=PALETTES['Ember'],emission_rate=.6,collision_emission=[0,1]);w.visual.configure(s);w.visual.preset='Starry'
    end=time.monotonic()+1.3
    while time.monotonic()<end:app.processEvents();time.sleep(.006)
    w.update_current_cover();w.grab().save(str(root/'docs/new-features.png'))
    editor=VisualSettings(w);editor.show();editor.channel_select.setCurrentIndex(1);tabs=editor.findChild(QTabWidget);tabs.setCurrentIndex(tabs.count()-1);app.processEvents();editor.grab().save(str(root/'docs/particle-channels.png'));editor.close();editor.deleteLater()
    editor=ThemeDialog(w);editor.mode.setCurrentIndex(2);editor.surface.setCurrentText('gradient');editor.show();app.processEvents();editor.grab().save(str(root/'docs/themes-advanced.png'));editor.close();editor.deleteLater()
    w.close();app.processEvents()
