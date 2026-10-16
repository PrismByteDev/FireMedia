import unittest
from PyQt6.QtCore import QObject,pyqtSignal
from firemedia.vfx import VfxSession

class Player(QObject):
    async_completed=pyqtSignal(int,str)
    def __init__(self):super().__init__();self.commands=[]
    def number(self,key):return 0
    def command_async(self,*args):self.commands.append(args);return len(self.commands)
class Video(QObject):
    frame_presented=pyqtSignal()
    def __init__(self):super().__init__();self.holding=True;self.is_ready=True;self.updates=0
    def update(self):self.updates+=1

class VfxTests(unittest.TestCase):
    def test_edits_stay_local_until_apply_and_wait_for_new_frames(self):
        p=Player();v=Video();s=VfxSession(p,v);done=[];s.finished.connect(lambda:done.append(True))
        s.draft['brightness']=25;s.draft['brightness']=40
        self.assertEqual(p.commands,[])
        s.apply();self.assertEqual(len(p.commands),4);self.assertTrue(v.holding)
        for token in (1,2,3):p.async_completed.emit(token,'')
        self.assertTrue(v.holding);self.assertFalse(done)
        p.async_completed.emit(4,'');self.assertFalse(v.holding);self.assertFalse(done)
        v.frame_presented.emit();self.assertFalse(done)
        v.frame_presented.emit();self.assertEqual(done,[True]);s.close()
    def test_apply_failure_keeps_held_image_and_allows_retry(self):
        p=Player();v=Video();s=VfxSession(p,v);errors=[];s.failed.connect(errors.append)
        s.apply()
        for token in (1,2,3,4):p.async_completed.emit(token,'failure' if token==2 else '')
        self.assertTrue(v.holding);self.assertTrue(errors);self.assertFalse(s.applying);s.close()
