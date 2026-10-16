"""Render native preview artifacts from a generated audio test signal.

This does not capture or operate other desktop applications. Preview audio is
synthetic, generated in a temporary directory, and is never bundled as music.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import sys
sys.path.insert(0,str(__import__('pathlib').Path(__file__).resolve().parents[1]))
import tempfile,time,wave
from pathlib import Path
import numpy as np
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from firemedia.window import Window,STYLE
from firemedia.playlists import Track

root=Path(__file__).resolve().parents[1]
app=QApplication([]);app.setStyle('Fusion');app.setStyleSheet(STYLE)
with tempfile.TemporaryDirectory() as folder:
    path=Path(folder)/'Spectrum test.wav'
    rate=22050;t=np.arange(rate*12)/rate
    rng=np.random.default_rng(14)
    audio=np.zeros(len(t))
    for i,f in enumerate(np.geomspace(45,9800,90)):
        envelope=.2+.8*(np.sin(t*(1+i%5)+i*.9)+1)/2
        audio+=np.sin(2*np.pi*f*t+rng.random()*6)*envelope*.014
    audio+=rng.normal(0,.014,len(t))
    with wave.open(str(path),'wb') as f:
        f.setparams((1,2,rate,0,'NONE',''));f.writeframes((np.clip(audio,-1,1)*32767).astype('<i2').tobytes())
    w=Window(Path(folder)/'state.json',silent=True)
    w.resize(1200,760);w.show();w.full_header.show()
    w.add_sources([str(path)])
    def pump(seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            app.processEvents();time.sleep(.008)
    pump(2.2)
    assert w.player.loaded and max(w.visual.levels)>.1
    w.grab().save(str(root/'docs'/'native-player.png'))
    w.toggle_effects();pump(.2)
    w.grab().save(str(root/'docs'/'native-effects-menu.png'))
    w.toggle_effects();w.toggle_playlist()
    w.queue.extend([Track('/example/track-two.flac','Track two'),Track('/example/track-three.mp3','Track three')])
    w.refresh_queue();pump(.2)
    w.grab().save(str(root/'docs'/'native-playlist.png'))
    w.close();app.processEvents()
print('Saved three native Qt previews to docs/')
