"""Run against a private session bus: dbus-run-session -- ... unittest ..."""
import os
import shutil
import subprocess
import tempfile
import time
import unittest
import wave
from pathlib import Path
import numpy as np
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QEvent
from firemedia.window import Window

app=QApplication.instance() or QApplication([])


def wait_until(condition,timeout=4):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        app.processEvents()
        if condition(): return True
        time.sleep(.005)
    return False

@unittest.skipUnless(os.environ.get('FIREMEDIA_TEST_DBUS')=='1' and shutil.which('gdbus'),
                     'Use FIREMEDIA_TEST_DBUS=1 inside dbus-run-session')
class MprisTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        t=np.arange(44100*8)/44100;data=(np.sin(t*2*np.pi*440)*10000).astype('<i2').tobytes()
        for name in ('one','two'):
            with wave.open(str(self.root/(name+'.wav')),'wb') as f:
                f.setparams((1,2,44100,0,'NONE',''));f.writeframes(data)
        self.window=Window(self.root/'state.json',silent=True)
        self.window.show();app.processEvents()
        self.assertTrue(self.window.mpris.available,self.window.mpris.bus.lastError().message())
        self.window.add_sources([str(self.root/'one.wav'),str(self.root/'two.wav')])
        self.assertTrue(wait_until(lambda:self.window.player.loaded))
    def tearDown(self):
        self.window.close();app.processEvents();app.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.temp.cleanup()
    def call(self,method,*args):
        command=['gdbus','call','--session','--dest',self.window.mpris.service_name,
                 '--object-path','/org/mpris/MediaPlayer2','--method',method,*args]
        p=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        self.assertTrue(wait_until(lambda:p.poll() is not None),f'D-Bus call timed out: {method}')
        out,err=p.communicate();self.assertEqual(p.returncode,0,err)
        return out
    def get(self,name):
        return self.call('org.freedesktop.DBus.Properties.Get','org.mpris.MediaPlayer2.Player',name)
    def test_controls_work_while_window_hidden(self):
        w=self.window;w.hide();app.processEvents()
        self.call('org.mpris.MediaPlayer2.Player.Pause')
        self.assertTrue(wait_until(lambda:w.player.get('pause')=='yes'))
        self.assertIn('Paused',self.get('PlaybackStatus'))
        self.call('org.mpris.MediaPlayer2.Player.PlayPause')
        self.assertTrue(wait_until(lambda:w.player.get('pause')=='no'))
        self.call('org.mpris.MediaPlayer2.Player.Next')
        self.assertTrue(wait_until(lambda:w.current.title=='two' and w.player.loaded))
        self.call('org.mpris.MediaPlayer2.Player.Pause')
        self.call('org.mpris.MediaPlayer2.Player.Previous')
        self.assertTrue(wait_until(lambda:w.current.title=='one' and w.player.loaded))
        self.assertEqual(w.player.get('pause'),'yes')
        self.call('org.mpris.MediaPlayer2.Player.Play')
        self.assertTrue(wait_until(lambda:w.player.get('pause')=='no'))
    def test_metadata_types_and_writable_properties(self):
        meta=self.get('Metadata')
        self.assertIn('objectpath',meta);self.assertIn('int64',meta);self.assertIn('one',meta)
        self.assertIn('int64',self.get('Position'))
        self.call('org.freedesktop.DBus.Properties.Set','org.mpris.MediaPlayer2.Player','Volume','<1.5>')
        self.assertEqual(self.window.volume.value(),150)
        self.call('org.freedesktop.DBus.Properties.Set','org.mpris.MediaPlayer2.Player','Shuffle','<true>')
        self.assertEqual(self.window.shuffle_mode,'On')
        self.call('org.freedesktop.DBus.Properties.Set','org.mpris.MediaPlayer2.Player','LoopStatus',"<'Playlist'>")
        self.assertEqual(self.window.loop_mode,'Playlist')
    def test_seek_rejects_stale_track_id(self):
        player='org.mpris.MediaPlayer2.Player.'
        self.call(player+'SetPosition','/wrong_track','6000000')
        self.assertLess(self.window.player.number('time-pos'),2)
        self.call(player+'SetPosition',self.window.mpris.track_id(),'3000000')
        self.assertTrue(wait_until(lambda:self.window.player.number('time-pos')>=2.8))
        self.call(player+'Seek','1000000')
        self.assertTrue(wait_until(lambda:self.window.player.number('time-pos')>=3.8))
    def test_desktop_receives_typed_property_change_signals(self):
        import threading
        lines=[]
        process=subprocess.Popen(['stdbuf','-oL','gdbus','monitor','--session','--dest',
            self.window.mpris.service_name,'--object-path','/org/mpris/MediaPlayer2'],
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        def read():
            for line in process.stdout: lines.append(line)
        reader=threading.Thread(target=read,daemon=True);reader.start()
        try:
            self.assertTrue(wait_until(lambda:any('is owned by' in line for line in lines)))
            self.call('org.freedesktop.DBus.Properties.Set','org.mpris.MediaPlayer2.Player','Volume','<1.37>')
            self.assertTrue(wait_until(lambda:any('PropertiesChanged' in line and 'Volume' in line for line in lines)))
            signal=next(line for line in lines if 'PropertiesChanged' in line and 'Volume' in line)
            self.assertIn('org.mpris.MediaPlayer2.Player',signal)
            self.assertIn('@as []',signal)
        finally:
            process.terminate();process.wait(timeout=2);reader.join(timeout=2);process.stdout.close()

    def test_stop_play_and_multiple_instances(self):
        w=self.window
        self.call('org.mpris.MediaPlayer2.Player.Stop')
        self.assertTrue(wait_until(lambda:not w.player.loaded))
        self.assertIn('Stopped',self.get('PlaybackStatus'))
        self.call('org.mpris.MediaPlayer2.Player.Play')
        self.assertTrue(wait_until(lambda:w.player.loaded))
        other=Window(self.root/'other.json',silent=True)
        try:
            self.assertTrue(other.mpris.available)
            self.assertNotEqual(other.mpris.service_name,w.mpris.service_name)
        finally:other.close()

if __name__=='__main__':unittest.main()
