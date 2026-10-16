"""Clock-alignment and bounded decode tests with audible/silent time markers."""
import shutil
import tempfile
import time
import unittest
import wave
from pathlib import Path
import numpy as np
from firemedia.visualizer import AudioAnalysis


def wait_for(condition, timeout=3):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if condition(): return True
        time.sleep(.005)
    return False

@unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg not installed')
class AnalysisClockTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'markers.wav'
        rate=22050;t=np.arange(rate*5)/rate
        # Pulses at 0.5–0.8 and 1.5–1.8 seconds identify the actual audio time.
        mask=((t>=.5)&(t<.8))|((t>=1.5)&(t<1.8))
        audio=(np.sin(t*2*np.pi*440)*mask*20000).astype('<i2')
        with wave.open(str(self.path),'wb') as f:
            f.setparams((1,2,rate,0,'NONE',''));f.writeframes(audio.tobytes())
        self.analysis=AudioAnalysis()
    def tearDown(self):
        self.analysis.stop()
        if self.analysis.worker: self.analysis.worker.join(timeout=2)
        self.temp.cleanup()
    def wait_frame(self, position):
        def ready():
            with self.analysis.condition:
                return bool(self.analysis.frames and self.analysis.frames[-1][0]>=position)
        self.assertTrue(wait_for(ready),'Decoder must provide the requested media time')
    def test_decode_ahead_is_bounded_and_not_paced_on_another_clock(self):
        self.analysis.start(str(self.path))
        self.assertTrue(wait_for(lambda:len(self.analysis.frames)==self.analysis.MAX_FRAMES))
        self.assertGreater(self.analysis.frames[-1][0],1)
        time.sleep(.03)
        self.assertLessEqual(len(self.analysis.frames),self.analysis.MAX_FRAMES)
    def test_samples_follow_media_time_and_skip_old_backlog(self):
        a=self.analysis;a.start(str(self.path));self.wait_frame(.7)
        self.assertLess(max(a.sample(.2)),.01)
        self.assertGreater(max(a.sample(.65)),.5)
        pcm=a.waveform();end=round(a.last_timestamp*a.RATE+a.WINDOW/2)
        expected=(np.sin(np.arange(end-a.WINDOW,end)/a.RATE*2*np.pi*440)*20000).astype('<i2')/32768
        np.testing.assert_allclose(pcm,expected,atol=1e-5)
        self.assertGreater(float(np.max(np.abs(pcm))),.5)
        self.wait_frame(1.1)
        self.assertLess(max(a.sample(1.05)),.01)
        self.assertEqual(float(np.max(np.abs(a.waveform()))),0)
        self.wait_frame(1.7)
        self.assertGreater(max(a.sample(1.65)),.5)
        self.assertLessEqual(a.last_timestamp,1.65)
        self.assertLess(1.65-a.last_timestamp,a.HOP/a.RATE+.001)
    def test_backward_seek_discards_old_frames(self):
        a=self.analysis;a.start(str(self.path),1.5);self.wait_frame(1.65)
        self.assertGreater(max(a.sample(1.65)),.5)
        old=a.worker;a.start(str(self.path),.05);old.join(timeout=2)
        self.assertEqual(float(np.max(np.abs(a.waveform()))),0)
        self.wait_frame(.2)
        self.assertLess(max(a.sample(.2)),.01)
        self.assertLessEqual(a.last_timestamp,.2)
    def test_playback_clock_freezes_when_paused(self):
        a=self.analysis;a.set_clock(10,False);time.sleep(.02)
        self.assertEqual(a.position(),10)
        a.set_clock(10,True);time.sleep(.02)
        self.assertGreater(a.position(),10.01)
