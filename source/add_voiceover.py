#!/usr/bin/env python3
"""Fit a recorded making-of narration to the prepared 75-second picture edit."""
import argparse,json,math,os,shutil,subprocess,tempfile
from pathlib import Path

def main():
    root=Path(__file__).resolve().parents[1]
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--voice',required=True,type=Path);p.add_argument('--video',type=Path,default=root/'film/optional-making-of-no-voice.mp4');p.add_argument('--output',type=Path,default=root/'film/optional-making-of-narrated.mp4');a=p.parse_args()
    if not a.voice.is_file() or not a.video.is_file():p.error('Both the recording and prepared video must exist')
    if a.output.resolve() in [a.voice.resolve(),a.video.resolve()]:p.error('Output must be a new file')
    if a.output.suffix.lower()!='.mp4':p.error('Use an .mp4 output filename')
    ffmpeg=shutil.which('ffmpeg');probe=shutil.which('ffprobe')
    if not ffmpeg or not probe:p.error('Install FFmpeg and FFprobe first')
    def inspect(path,kind):
        try:
            data=json.loads(subprocess.check_output([probe,'-v','error','-show_entries','stream=codec_type,duration:format=duration','-of','json',str(path)],text=True,stderr=subprocess.PIPE))
            stream=next((s for s in data.get('streams',[]) if s.get('codec_type')==kind),None)
            if stream is None:p.error(f'{path.name} contains no {kind} stream')
            duration=stream.get('duration')
            if duration in (None,'N/A'):duration=data.get('format',{}).get('duration')
            duration=float(duration)
            if not math.isfinite(duration) or duration<=0:raise ValueError('Invalid media duration')
            return duration
        except (subprocess.CalledProcessError,ValueError,TypeError,KeyError):
            p.error(f'Cannot read a valid duration from {path.name}')
    duration=inspect(a.voice,'audio')
    if not 60<=duration<=90:p.error('Record the included script in 60-90 seconds; about 75 seconds sounds most natural')
    if abs(inspect(a.video,'video')-75)>1/24:p.error('The prepared picture edit must be 75 seconds; do not use the 24-second contest film')
    # A modest atempo adjustment preserves pitch while matching the approved edit.
    filt='atempo=%.8f,apad,atrim=duration=75,loudnorm=I=-16:TP=-1.5:LRA=9'%(duration/75)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=a.output.stem+'.',suffix='.partial.mp4',dir=a.output.parent);os.close(fd);temp=Path(name)
    try:
        subprocess.run([ffmpeg,'-hide_banner','-y','-i',str(a.video),'-i',str(a.voice),'-map','0:v:0','-map','1:a:0','-c:v','copy','-af',filt,'-c:a','aac','-b:a','256k','-ar','48000','-t','75','-movflags','+faststart',str(temp)],check=True)
        temp.replace(a.output)
    finally:temp.unlink(missing_ok=True)
    print(a.output)
if __name__=='__main__':main()
