"""Desktop integration check: actual pixels in Qt, resizing, and audio/video switching.

Run inside dbus-run-session to keep the generated test player off the real
session's media controls. Requires a working X11 or Wayland display and FFmpeg.
"""
import sys
import tempfile
import time
import subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PyQt6.QtCore import Qt,QTimer
from PyQt6.QtWidgets import QApplication,QSlider,QPushButton
from firemedia.window import Window,STYLE

QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app=QApplication([]);app.setStyleSheet(STYLE)

def wait_for(condition,timeout=6):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        app.processEvents();time.sleep(.008)
        if condition():return True
    return False

with tempfile.TemporaryDirectory() as folder:
    folder=Path(folder)
    video=folder/'video.mp4';audio=folder/'audio.wav'
    video.with_suffix('.srt').write_text('1\n00:00:00,000 --> 00:00:04,900\nFireMedia subtitle test\n')
    subprocess.run(['ffmpeg','-nostdin','-loglevel','error','-f','lavfi','-i','testsrc2=size=480x270:rate=12',
                    '-t','5','-c:v','libx264','-pix_fmt','yuv420p',str(video)],check=True)
    subprocess.run(['ffmpeg','-nostdin','-loglevel','error','-f','lavfi','-i','sine=frequency=440',
                    '-t','5',str(audio)],check=True)
    w=Window(folder/'state.json');w.resize(960,600);w.show()
    w.player.set('mute',True)
    errors=[];w.video.failed.connect(errors.append);w.player.error.connect(errors.append)
    try:
        w.add_sources([str(video),str(audio)])
        assert wait_for(lambda:w._video and w.video.frames_rendered>=5),errors
        def colors():
            frame=w.video.grabFramebuffer()
            return len({frame.pixelColor(x,y).name() for x in range(0,frame.width(),40) for y in range(0,frame.height(),40)})
        assert colors()>8,'Frame pixels must contain the decoded test pattern'
        assert w.player.get('current-vo')=='libmpv','Video must use the embedded renderer'
        assert w.visual.isHidden()
        assert wait_for(lambda:'FireMedia subtitle test' in w.subtitle_overlay.text),'Matching SRT must autoload into the Qt overlay'
        from firemedia.vfx import VfxSession
        position=w.player.number('time-pos');w.video.grabFramebuffer();w.video.holding=True
        assert wait_for(lambda:w.player.number('time-pos')>position+.15),'Holding the image must not pause playback'
        session=VfxSession(w.player,w.video,w);finished=[];session.finished.connect(lambda:finished.append(True))
        session.draft['brightness']=20;session.apply()
        assert wait_for(lambda:bool(finished)),'VFX must complete after new frames are rendered'
        assert w.player.number('brightness')==20
        session.close()
        checked=[]
        def edit_vfx():
            dialog=QApplication.activeModalWidget()
            sliders=dialog.findChildren(QSlider)
            sliders[0].setValue(30);sliders[1].setValue(40)
            assert w.player.number('brightness')==20,'Slider edits must stay local'
            def apply():
                assert w.held_image.isVisible() and w.video.holding
                assert w.held_image.pixmap() is not None
                dialog.grab().save(str(Path(__file__).resolve().parents[1]/'docs'/'vfx-still-preview.png'))
                next(b for b in dialog.findChildren(QPushButton) if b.text()=='Apply').click()
                dialog.reject()
                assert dialog.isVisible(),'Do not release the held frame while applying'
                checked.append(True)
            QTimer.singleShot(140,apply)
        QTimer.singleShot(0,edit_vfx);w.show_video_effects()
        assert checked and not w.held_image.isVisible() and not w.video.holding
        assert w.player.number('brightness')==30 and w.player.number('contrast')==40
        def capture_customization():
            dialog=QApplication.activeModalWidget()
            dialog.grab().save(str(Path(__file__).resolve().parents[1]/'docs'/'subtitle-customize.png'));dialog.reject()
        QTimer.singleShot(0,capture_customization);w.customize_subtitles()
        w.overlay_timer.stop()
        w.update_control_visibility(animate=False,nearby=False)
        assert w.transport_opacity.opacity()==0
        root=Path(__file__).resolve().parents[1]/'docs'
        w.grab().save(str(root/'native-video-clean.png'))
        w.update_control_visibility(animate=False,nearby=True)
        w.grab().save(str(root/'native-video-controls.png'))
        w.toggle_playlist();w.toggle_effects();app.processEvents()
        assert w.transport_opacity.opacity()==1 and not w.overlay_controls
        assert colors()>8
        w.toggle_effects();w.toggle_playlist()
        w.toggle_fullscreen();app.processEvents()
        assert colors()>8
        w.toggle_fullscreen()
        w.play_index(1)
        assert wait_for(lambda:w.player.loaded and not w._video)
        assert w.visual.isVisible()
        assert wait_for(lambda:len(w.visual.waveform)>0 and max(abs(v) for v in w.visual.waveform)>.01),'PCM waveform must reach the native visualizer'
        w.set_ldm('Off');w.showMinimized();assert wait_for(lambda:not w.windowHandle().isExposed()),'Compositor must stop exposing the minimized window'
        phase=w.visual.phase;position=w.player.number('time-pos')
        assert not w.visual.timer.isActive() and w.analysis.cancel.is_set(),'Minimizing must immediately stop visualizer and analysis'
        w.apply_quality();assert not w.visual.timer.isActive(),'Quality changes must not restart minimized effects'
        assert wait_for(lambda:w.player.number('time-pos')>position+.15),'Audio must continue while minimized'
        assert w.visual.phase==phase,'Minimized effects must not advance'
        # Wayland has no programmatic unminimize request; remap for this automated check.
        w.hide();w.showNormal();assert wait_for(lambda:w.windowHandle().isExposed()),'Compositor must expose the restored window'
        assert wait_for(lambda:w.visual.timer.isActive() and w.analysis.last_timestamp is not None),'Restore must restart effects at the playback clock'

        w.player.set('pause',True);assert wait_for(lambda:w.visual.paused)
        held=w.visual.waveform.copy();deadline=time.monotonic()+.12
        while time.monotonic()<deadline:app.processEvents();time.sleep(.008)
        assert (held==w.visual.waveform).all(),'Pausing must hold the PCM trace'
        w.player.set('pause',False);assert wait_for(lambda:not w.visual.paused and w.analysis.last_timestamp is not None)
        w.play_index(0)
        assert wait_for(lambda:w.player.loaded and w._video)
        assert colors()>8
        assert not errors,errors
        print({'platform':app.platformName(),'renderer':w.player.get('current-vo'),
               'rendered_frames':w.video.frames_rendered,'colors':colors(),
               'embedded_video':True,'audio_video_switch':True,'overlay_controls':True,'srt_autoload':True,'vfx_hold_apply':True,'pcm_waveform_pause_resume':True,'minimized_effects_suspended':True})
    finally:
        w.close();app.processEvents()
