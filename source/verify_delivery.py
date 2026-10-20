#!/usr/bin/env python3
"""Decode and validate an assembled submission, independently from rendering."""
import argparse,json,shutil,struct,subprocess,sys
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('movie',type=Path);p.add_argument('--report',type=Path);a=p.parse_args()
    probe=shutil.which('ffprobe');ffmpeg=shutil.which('ffmpeg')
    if not probe or not ffmpeg:p.error('FFmpeg and FFprobe are required')
    data=json.loads(subprocess.check_output([probe,'-v','error','-count_frames','-show_entries','stream=codec_type,codec_name,width,height,r_frame_rate,nb_read_frames,sample_rate,channels,pix_fmt:format=duration,size','-of','json',str(a.movie)],text=True))
    video=next((s for s in data['streams'] if s['codec_type']=='video'),{});audio=next((s for s in data['streams'] if s['codec_type']=='audio'),{})
    checks={'duration_24_seconds':abs(float(data['format']['duration'])-24)<.01,'frames_576':int(video.get('nb_read_frames',0))==576,'fps_24':video.get('r_frame_rate')=='24/1','h264_video':video.get('codec_name')=='h264','yuv420p':video.get('pix_fmt')=='yuv420p','aac_stereo_48k':audio.get('codec_name')=='aac' and audio.get('channels')==2 and audio.get('sample_rate')=='48000','resolution':(video.get('width'),video.get('height')) in [(1920,1080),(960,540)]}
    # Inspect ISO BMFF top-level atom ordering without trusting metadata labels.
    atoms=[]
    with a.movie.open('rb') as f:
        size=a.movie.stat().st_size
        while f.tell()<size:
            head=f.read(8)
            if len(head)!=8:break
            length,kind=struct.unpack('>I4s',head);header=8
            if length==1:
                length=struct.unpack('>Q',f.read(8))[0];header=16
            elif length==0:length=size-f.tell()+8
            if length<header:break
            atoms.append(kind.decode('ascii','replace'));f.seek(length-header,1)
    checks['fast_start']='moov' in atoms and 'mdat' in atoms and atoms.index('moov')<atoms.index('mdat')
    decoded=subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-xerror','-i',str(a.movie),'-f','null','-'],capture_output=True,text=True)
    checks['full_decode_without_errors']=decoded.returncode==0
    report={'movie':a.movie.name,'checks':checks,'media':data,'passed':all(checks.values())}
    if a.report:a.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
