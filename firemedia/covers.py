"""Asynchronous local cover-art discovery shared by queue icons and visualizer."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
from PyQt6.QtCore import QObject,pyqtSignal, QSize, Qt
from PyQt6.QtGui import QImage,QImageReader,QIcon,QPixmap
from .sources import source_scheme,file_uri_path
from .runtime import find_tool,subprocess_options


def cover_directory(source):
    scheme=source_scheme(source)
    if scheme not in ('','file'):return None
    return str(Path(file_uri_path(source) if scheme=='file' else source).expanduser().resolve().parent)


def read_cover(directory):
    priority={'.png':0,'.jpg':1,'.jpeg':2,'.webp':3,'.jxl':4,'.avif':5}
    try:files=sorted((p for p in Path(directory).iterdir() if p.is_file() and p.stem.casefold()=='cover'),key=lambda p:(priority.get(p.suffix.lower(),20),p.name))
    except OSError:return QImage(),''
    for path in files:
        try:
            if path.stat().st_size>16*1024*1024:continue
            reader=QImageReader(str(path));reader.setAutoTransform(True);size=reader.size()
            if size.isValid() and size.width()*size.height()<=16_000_000:
                if max(size.width(),size.height())>1024:reader.setScaledSize(size.scaled(QSize(1024,1024),Qt.AspectRatioMode.KeepAspectRatio))
                image=reader.read()
                if not image.isNull():return image,str(path)
            # Optional codecs (notably JPEG XL) can be supplied by FFmpeg.
            if path.suffix.lower() in ('.jxl','.avif') and find_tool('ffmpeg'):
                result=subprocess.run([find_tool('ffmpeg'),'-nostdin','-hide_banner','-loglevel','error','-threads','1','-i',str(path),'-frames:v','1','-vf','scale=1024:1024:force_original_aspect_ratio=decrease','-f','image2pipe','-c:v','png','-'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=4,**subprocess_options())
                image=QImage.fromData(result.stdout)
                if not image.isNull():return image,str(path)
        except (OSError,subprocess.SubprocessError):continue
    return QImage(),''


class CoverLibrary(QObject):
    available=pyqtSignal(str,QImage,str)
    _loaded=pyqtSignal(str,QImage,str)
    def __init__(self,parent=None):
        super().__init__(parent);self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='firemedia-cover');self.cache={};self.closed=False
        self._loaded.connect(self.store)
    def request(self,source):
        directory=cover_directory(source)
        if directory is None:return QIcon()
        if directory not in self.cache:
            self.cache[directory]=None;future=self.pool.submit(read_cover,directory)
            def done(f):
                if self.closed:return
                try:
                    image,path=f.result();self._loaded.emit(directory,image,path)
                except Exception:pass
            future.add_done_callback(done)
        result=self.cache[directory]
        return QIcon(QPixmap.fromImage(result[0])) if result and not result[0].isNull() else QIcon()
    def store(self,directory,image,path):
        if self.closed:return
        self.cache[directory]=(image,path);self.available.emit(directory,image,path)
    def image(self,source):
        value=self.cache.get(cover_directory(source));return value[0] if value else QImage()
    def path(self,source):
        value=self.cache.get(cover_directory(source));return value[1] if value else ''
    def close(self):self.closed=True;self.pool.shutdown(wait=False,cancel_futures=True)
