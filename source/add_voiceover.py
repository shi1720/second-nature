#!/usr/bin/env python3
"""Fit a recorded making-of narration to the prepared 75-second picture edit."""
import argparse,json,shutil,subprocess,sys
from pathlib import Path

def main():
    root=Path(__file__).resolve().parents[1]
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--voice',required=True,type=Path);p.add_argument('--video',type=Path,default=root/'film/optional-making-of-no-voice.mp4');p.add_argument('--output',type=Path,default=root/'film/optional-making-of-narrated.mp4');a=p.parse_args()
    if not a.voice.is_file() or not a.video.is_file():p.error('Both the recording and prepared video must exist')
    if a.output.resolve() in [a.voice.resolve(),a.video.resolve()]:p.error('Output must be a new file')
    ffmpeg=shutil.which('ffmpeg');probe=shutil.which('ffprobe')
    if not ffmpeg or not probe:p.error('Install FFmpeg and FFprobe first')
    data=json.loads(subprocess.check_output([probe,'-v','error','-show_entries','stream=codec_type:format=duration','-of','json',str(a.voice)],text=True))
    if not any(s['codec_type']=='audio' for s in data.get('streams',[])):p.error('The recording contains no audio stream')
    duration=float(data['format']['duration'])
    if not 60<=duration<=90:p.error('Record the included script in 60-90 seconds; about 75 seconds sounds most natural')
    # A modest atempo adjustment preserves pitch while matching the approved edit.
    filt='atempo=%.8f,apad,atrim=duration=75,loudnorm=I=-16:TP=-1.5:LRA=9'%(duration/75)
    a.output.parent.mkdir(parents=True,exist_ok=True);temp=a.output.with_name(a.output.stem+'.partial.mp4')
    subprocess.run([ffmpeg,'-hide_banner','-y','-i',str(a.video),'-i',str(a.voice),'-map','0:v:0','-map','1:a:0','-c:v','copy','-af',filt,'-c:a','aac','-b:a','256k','-ar','48000','-t','75','-movflags','+faststart',str(temp)],check=True)
    temp.replace(a.output);print(a.output)
if __name__=='__main__':main()
