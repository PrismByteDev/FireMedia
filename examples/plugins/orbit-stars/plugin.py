"""Example FireMedia API v1 plugin. No external Python dependencies."""
import math


def radial(e):
    f=e.frame
    cx,cy=f.width/2,f.height/2
    radius=min(f.width,f.height)*.2
    count=min(len(f.levels),24 if f.low_detail else 96)
    for i in range(count):
        level=0 if f.paused else f.levels[i*len(f.levels)//count]
        angle=i/count*math.tau+f.time*.08
        dx,dy=math.cos(angle),math.sin(angle)
        length=12+level*min(f.width,f.height)*.28
        color=[80+round(i/count*100),170,255,220]
        e.draw.line(cx+dx*radius,cy+dy*radius,cx+dx*(radius+length),cy+dy*(radius+length),color,3)
    e.draw.text(cx-52,cy+6,'Orbit Stars','#C5E4FFFF',18)


api.registerVisualizer('radial','Orbit Stars · radial spectrum',radial)


@api.on('onBarCollision')
def sparks(e):
    if e.index%4==0:
        api.summonParticle(e.x,e.y,color=[180,220,255,230],vx=[-25,25],vy=[80,140],lifetime=1.2,size=5)


def onLoad(e):api.log('Orbit Stars ready. Choose its renderer in Visualizer settings.')
def onUnload(e):api.log('Orbit Stars stopped.')
def onSubtitleLoad(e):api.log('Subtitle track loaded: '+str(e.track))
def onSubtitleMessage(e):
    if e.text:api.log('Subtitle: '+e.text[:80])
