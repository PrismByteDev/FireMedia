"""Isolated Linux mod interpreter. Pure stdlib: never imported by the GUI."""
import base64
import ctypes
import ctypes.util
import errno
import json
import math
import mmap
import os
import random
import resource
import signal
import socket
import subprocess
import sys
import time
from types import SimpleNamespace

EVENTS={'onLoad','onUnload','update','draw','onBarCollision','onSubtitleLoad','onSubtitleMessage','onTrackLoad','onPlaybackState'}
MAX_MESSAGE=48*1024*1024
MAX_COMMANDS=1024

def invoke(fn,event):
    start=time.monotonic();fn(event)
    if time.monotonic()-start>.05:raise RuntimeError('Hook exceeded the 50 ms budget')


def restrict_process():
    """Fail closed before executing ANY mod code. Default-deny syscall policy."""
    if not sys.platform.startswith('linux'):raise RuntimeError('Restricted mods require Linux')
    library=ctypes.util.find_library('seccomp')
    if not library:raise RuntimeError('Install libseccomp2 to enable restricted mods')
    sec=ctypes.CDLL(library,use_errno=True);libc=ctypes.CDLL(None,use_errno=True)
    if libc.prctl(1,signal.SIGKILL,0,0,0)!=0 or os.getppid()==1:raise RuntimeError('Could not tie mod lifetime to the player')
    sec.seccomp_init.argtypes=[ctypes.c_uint32];sec.seccomp_init.restype=ctypes.c_void_p
    sec.seccomp_syscall_resolve_name.argtypes=[ctypes.c_char_p];sec.seccomp_syscall_resolve_name.restype=ctypes.c_int
    sec.seccomp_rule_add.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint]
    sec.seccomp_load.argtypes=[ctypes.c_void_p];sec.seccomp_release.argtypes=[ctypes.c_void_p]
    # Resolve/load runtime libraries BEFORE closing the filesystem boundary.
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(0,0))
    resource.setrlimit(resource.RLIMIT_AS,(384*1024*1024,384*1024*1024))
    os.closerange(3,resource.getrlimit(resource.RLIMIT_NOFILE)[0])
    if libc.prctl(38,1,0,0,0)!=0:raise RuntimeError('Could not set no_new_privs')
    context=sec.seccomp_init(0x00050000|errno.EPERM) # SCMP_ACT_ERRNO(EPERM)
    if not context:raise RuntimeError('Could not create syscall filter')
    class Compare(ctypes.Structure):
        _fields_=[('arg',ctypes.c_uint),('op',ctypes.c_int),('a',ctypes.c_uint64),('b',ctypes.c_uint64)]
    try:
        allowed=('brk','munmap','mprotect','mremap','madvise','futex','futex_time64',
                 'clock_gettime','clock_gettime64','gettimeofday','time','getrandom','rt_sigaction',
                 'rt_sigprocmask','rt_sigreturn','sigaltstack','restart_syscall','nanosleep',
                 'clock_nanosleep','clock_nanosleep_time64','getpid','gettid','sched_yield',
                 'exit','exit_group','close')
        for name in allowed:
            nr=sec.seccomp_syscall_resolve_name(name.encode())
            if nr>=0 and sec.seccomp_rule_add(context,0x7fff0000,nr,0)!=0:raise RuntimeError('Could not add syscall restriction')
        for name,fds in [('read',(0,)),('write',(1,2)),('fstat',(0,1,2)),('fstat64',(0,1,2))]:
            nr=sec.seccomp_syscall_resolve_name(name.encode())
            if nr<0:continue
            for fd in fds:
                if sec.seccomp_rule_add(context,0x7fff0000,nr,1,Compare(0,4,fd,0))!=0:raise RuntimeError('Could not restrict stream descriptors')
        for name in ('mmap','mmap2'):
            nr=sec.seccomp_syscall_resolve_name(name.encode())
            if nr>=0 and sec.seccomp_rule_add(context,0x7fff0000,nr,1,Compare(3,7,mmap.MAP_ANONYMOUS,mmap.MAP_ANONYMOUS))!=0:raise RuntimeError('Could not restrict anonymous memory allocation')
        if sec.seccomp_load(context)!=0:raise RuntimeError('Kernel denied the mod syscall sandbox')
    finally:sec.seccomp_release(context)
    # No open/openat, stat-path, sockets, exec, fork/clone, ptrace, process_vm,
    # kill, ioctl, io_uring, mount, prctl, or namespace syscalls are permitted.


class Draw:
    def __init__(self,api):self.api=api
    def add(self,name,*args):self.api.command(name,*args)
    def rect(self,x,y,width,height,color='#FFFFFF',radius=0):self.add('rect',x,y,width,height,color,radius)
    def ellipse(self,x,y,width,height,color='#FFFFFF'):self.add('ellipse',x,y,width,height,color)
    def line(self,x1,y1,x2,y2,color='#FFFFFF',width=1):self.add('line',x1,y1,x2,y2,color,width)
    def text(self,x,y,text,color='#FFFFFF',size=16):self.add('text',x,y,str(text)[:1024],color,size)
    def image(self,image,x,y,width,height):self.add('image',image,x,y,width,height)


class API:
    version=1
    def __init__(self,files):
        self.files=files;self.hooks={};self.visualizers={};self.commands=[];self.logs=[];self.particles=[]
        self.frame=SimpleNamespace(width=1,height=1,baseline=1,time=0,dt=0,levels=(),bars=(),paused=True,low_detail=False)
    def on(self,name,callback=None):
        if name not in EVENTS:raise ValueError('Unknown event')
        def register(fn):self.hooks.setdefault(name,[]).append(fn);return fn
        return register(callback) if callback is not None else register
    def registerVisualizer(self,id,name,draw,update=None):
        if not isinstance(id,str) or not id or len(id)>64 or not all(c in 'abcdefghijklmnopqrstuvwxyz0123456789_-' for c in id):raise ValueError('Invalid renderer ID')
        if not isinstance(name,str) or len(name)>128 or not callable(draw):raise ValueError('Invalid renderer')
        self.visualizers[id]=(name,draw,update)
    def asset(self,name):return self.files[name]
    def image(self,name):
        if name not in self.files:raise ValueError('Missing packaged image')
        return name  # Opaque asset reference: only packaged bytes can reach host drawing.
    def log(self,text):
        if len(self.logs)<32:self.logs.append(str(text)[:2048])
    def summonParticle(self,x,y,**options):
        if len(self.particles)>=400:return False
        self.particles.append([x,y,options]);return True
    def command(self,name,*args):
        if len(self.commands)>=MAX_COMMANDS:raise ValueError('Drawing command limit exceeded')
        self.commands.append([name,*args])
    def event(self,name,values):
        event=SimpleNamespace(**values)
        for fn in self.hooks.get(name,()):invoke(fn,event)
    def response(self):
        return {'ready':True,'visualizers':[[id,v[0]] for id,v in self.visualizers.items()],
                'commands':self.commands,'logs':self.logs,'particles':self.particles}


def send(value):
    data=json.dumps(value,allow_nan=False,separators=(',',':'))
    if len(data)>1024*1024:raise ValueError('Mod response exceeds 1 MB')
    sys.stdout.write(data+'\n');sys.stdout.flush()


def main():
    init=json.loads(sys.stdin.buffer.readline(MAX_MESSAGE+1))
    files={name:base64.b64decode(data) for name,data in init['files'].items()}
    code=compile(files[init['entry']],init['entry'],'exec')
    restrict_process()
    api=API(files);namespace={'api':api,'__name__':'firemedia_mod','__file__':init['entry']}
    exec(code,namespace)
    for event in EVENTS:
        fn=namespace.get(event)
        if callable(fn) and fn not in api.hooks.get(event,[]):api.hooks.setdefault(event,[]).append(fn)
    api.event('onLoad',{'api':1});send(api.response())
    while True:
        line=sys.stdin.buffer.readline(1024*1024+1)
        if not line:return
        if len(line)>1024*1024:raise ValueError('Oversized host event')
        request=json.loads(line);api.commands=[];api.logs=[];api.particles=[]
        if request.get('frame'):
            f=request['frame'];f['levels']=tuple(f['levels']);f['bars']=tuple(f['bars']);api.frame=SimpleNamespace(**f)
        for name,values in request.get('events',[]):api.event(name,values)
        if request.get('frame'):
            api.event('update',{'frame':api.frame,'dt':api.frame.dt})
            selected=request.get('selected','');renderer=api.visualizers.get(selected)
            context=Draw(api);event=SimpleNamespace(draw=context,frame=api.frame,dt=api.frame.dt)
            if renderer:
                if renderer[2]:invoke(renderer[2],event)
                invoke(renderer[1],event)
            for fn in api.hooks.get('draw',[]):invoke(fn,event)
        send(api.response())


if __name__=='__main__':
    try:main()
    except BaseException as error:
        try:send({'error':type(error).__name__+': '+str(error)[:1024]})
        except BaseException:pass
        raise SystemExit(1)
