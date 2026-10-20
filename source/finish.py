"""Original deterministic synthesis, typography and film assembly.
Requires numpy and Pillow; FFmpeg performs H.264/AAC delivery encoding.
"""
import sys,json,math,wave,subprocess,hashlib
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
SR=48000;DURATION=24

def score(out):
    n=SR*DURATION;audio=np.zeros((n,2),dtype=np.float64);rng=np.random.default_rng(1720)
    def add(start,x,level=1,pan=0):
        first=int(start*SR)
        if first>=n:return
        if first<0:x=x[-first:];first=0
        x=x[:n-first]*level
        audio[first:first+len(x),0]+=x*math.sqrt((1-pan)/2)
        audio[first:first+len(x),1]+=x*math.sqrt((1+pan)/2)
    def tone(freq,dur,decay=2,attack=.015):
        t=np.arange(int(SR*dur))/SR
        env=(1-np.exp(-t/attack))*np.exp(-t*decay)
        return (np.sin(2*np.pi*freq*t)+.22*np.sin(2*np.pi*freq*2*t)+.07*np.sin(2*np.pi*freq*3*t))*env
    def whoosh(start,dur,level=.1,pan=0,rise=True):
        t=np.arange(int(SR*dur))/SR;u=t/dur
        noise=rng.normal(0,1,len(t));noise=np.convolve(noise,np.ones(9)/9,mode='same')
        env=np.sin(np.pi*u)**2
        freq=(170+900*u*u) if rise else (1100-950*u)
        phase=2*np.pi*np.cumsum(freq)/SR
        add(start,(noise*.6+np.sin(phase)*.15)*env,level,pan)
    # The first two seconds breathe: a seed, a distant pulse, and a mechanical clock.
    add(0,tone(146.832,3.2,.65,.4),.09)
    for sec in [.32,1.12,1.82]:add(sec,tone(1200,.14,34,.001),.035,-.2)
    # One evolving arpeggio, with pulse intervals shortening as the drop accelerates.
    notes=[146.832,220,293.665,349.228,440,293.665,220,261.626]
    tm=2.0;i=0
    while tm<13.65:
        u=(tm-2)/11.65;step=.43-.23*u
        add(tm,tone(notes[i%8]*(2 if i%4==3 else 1),.8,4.5,.007),.11+.045*u,math.sin(i*.8)*.45)
        t=np.arange(int(.28*SR))/SR
        kick=np.sin(2*np.pi*(49*t+9*(1-np.exp(-t*35))/35))*np.exp(-t*22)
        add(tm,kick,.095)
        if i%2==1:
            noise=rng.normal(0,1,int(.08*SR));add(tm,noise*np.exp(-np.arange(len(noise))/SR*70),.014,.35)
        tm+=step;i+=1
    # A smooth motor bed follows the route; the score drops away before impact.
    t=np.arange(int(11.7*SR))/SR;u=t/11.7
    phase=2*np.pi*np.cumsum(62+145*u*u)/SR
    add(2,np.sin(phase)*np.sin(np.pi*u)**.6,.055)
    for start,pan in [(3.0,-.6),(4.15,.5),(5.3,-.5),(6.0,.4),(8.1,-.6),(10.6,.6),(11.7,-.4)]:whoosh(start,.55,.13,pan)
    whoosh(13.15,.68,.16,0,False)
    # Suspension is almost silent. A delicate droplet releases at 15.25 seconds.
    for fq,lv in [(920,.15),(1380,.06),(1840,.025)]:add(15.22,tone(fq,1.8,5,.001),lv)
    # Bloom opens into D major: harmonically distinct from the race's minor third.
    chord=[146.832,220,293.665,369.994,440,587.33]
    for i,freq in enumerate(chord):add(15.5+i*.055,tone(freq,8.5,.20,.7),.055,(-1 if i%2 else 1)*.3)
    for i,fq in enumerate([587.33,739.989,880,1174.66]):add(17+i*.36,tone(fq,4.5,1.1,.02),.038,math.sin(i)*.6)
    whoosh(15.35,2.6,.055,.1)
    # Short original feedback delays create space without samples or plugins.
    wet=audio.copy()
    for delay,gain in [(.137,.15),(.271,.11),(.413,.075)]:
        d=int(delay*SR);wet[d:,0]+=audio[:-d,1]*gain;wet[d:,1]+=audio[:-d,0]*gain
    wet*=np.minimum(1,np.arange(n)/(SR*.06))[:,None]
    wet*=np.minimum(1,(n-1-np.arange(n))/(SR*1.1))[:,None]
    wet=np.tanh(wet*1.4);wet*=.88/max(.001,np.max(np.abs(wet)))
    with wave.open(str(out/'soundtrack.wav'),'wb') as w:w.setnchannels(2);w.setsampwidth(2);w.setframerate(SR);w.writeframes((wet*32767).astype('<i2').tobytes())

def titles(out,width,height):
    scale=width/1920;FONT=ROOT/'assets/fonts/SpaceGrotesk.ttf'
    def font(size):return ImageFont.truetype(str(FONT),round(size*scale))
    def tracking(draw,xy,body,size,fill,space=4):
        x,y=xy;f=font(size)
        for c in body:
            draw.text((x,y),c,font=f,fill=fill);x+=draw.textlength(c,font=f)+space*scale
    for name,kind in [('opening.png','opening'),('closing.png','closing')]:
        im=Image.new('RGBA',(width,height));a=np.zeros((height,width,4),dtype=np.uint8)
        # Designed left scrim maintains readability without obscuring the hero.
        xx=np.arange(width)/width
        opacity=(np.maximum(0,1-xx/.66)**1.7*(170 if kind=='closing' else 115)).astype(np.uint8)
        a[:,:,0]=4;a[:,:,1]=20;a[:,:,2]=27;a[:,:,3]=opacity[None,:];im=Image.fromarray(a)
        d=ImageDraw.Draw(im);s=scale;x=96*s
        tracking(d,(x,78*s),'SECOND NATURE',25,'#EADAC6',5)
        d.line((x,132*s,x+56*s,132*s),fill='#FF9467',width=max(1,round(3*s)))
        if kind=='opening':
            d.text((x,174*s),'One drop.\nOne chance.',font=font(64),fill='#FFF2DE',spacing=6*s)
            tracking(d,(x,950*s),'A RACE TO BRING SOMETHING TO LIFE',18,'#EADAC6',2)
        else:
            d.text((x,370*s),'Make every\nsecond grow.',font=font(79),fill='#FFF2DE',spacing=5*s)
            tracking(d,(x,940*s),'SHIVAM GUPTA',23,'#FFF2DE',4)
            tracking(d,(x,985*s),'A PROCEDURAL BLENDER FILM',16,'#C6C6B7',2)
        im.save(out/name)

def main():
    out=Path(sys.argv[1]);ffmpeg=sys.argv[2];state=json.loads((out/'render-state.json').read_text());w,h=state['width'],state['height']
    score(out);titles(out,w,h)
    # Overlay alpha fades retain the original full-frame Blender motion.
    filt="[1:v]format=rgba,fade=t=in:st=0:d=0.25:alpha=1,fade=t=out:st=1.65:d=0.3:alpha=1[op];[2:v]format=rgba,fade=t=in:st=20.25:d=0.6:alpha=1[cl];[0:v][op]overlay=0:0:enable='lt(t,2)'[v1];[v1][cl]overlay=0:0:enable='gte(t,20.25)',format=yuv420p[v];[3:a]loudnorm=I=-16:TP=-1.5:LRA=9[a]"
    temp=out/'second-nature.partial.mp4'
    cmd=[ffmpeg,'-hide_banner','-loglevel','warning','-y','-framerate','24','-start_number','1','-i',str(out/'frames/frame_%04d.png'),'-loop','1','-framerate','24','-i',str(out/'opening.png'),'-loop','1','-framerate','24','-i',str(out/'closing.png'),'-i',str(out/'soundtrack.wav'),'-filter_complex',filt,'-map','[v]','-map','[a]','-t','24','-c:v','libx264','-preset','slow','-crf','16','-c:a','aac','-b:a','256k','-ar','48000','-movflags','+faststart','-metadata','title=SECOND NATURE','-metadata','artist=Shivam Gupta','-metadata','comment=Procedural Blender film; AI-assisted production. Original synthetic audio.','-threads','6',str(temp)]
    subprocess.run(cmd,check=True);temp.replace(out/'second-nature.mp4')
    path=out/'second-nature.mp4';(out/'delivery.json').write_text(json.dumps({'title':'SECOND NATURE','entrant':'Shivam Gupta','duration_seconds':24,'frames':576,'fps':24,'width':w,'height':h,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'profile':state['profile']},indent=2)+'\n')
if __name__=='__main__':main()
