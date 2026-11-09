#!/usr/bin/env python3
"""A stand-in for the `yt-dlp` command, for tests: answers the calls tubes makes, without the network.

  --version                                          prints a version
  --dump-single-json --no-playlist URL               one video's info with an H.264 and an AAC format (duration $FAKE_YTDLP_SECONDS, default 6)
  -f v264|a-aac -o - URL                             that stream as fragmented MP4 on stdout, made by ffmpeg from a test pattern or a tone

Set FAKE_YTDLP_FAIL=<substring of the command line> to make a matching call fail with an ERROR line."""
import json, os, subprocess, sys

args = sys.argv[1:]
line = ' '.join(args)
if os.environ.get('FAKE_YTDLP_FAIL') and os.environ['FAKE_YTDLP_FAIL'] in line:
    print('ERROR: [youtube] fake: Video unavailable', file=sys.stderr); sys.exit(1)
if '--version' in args: print('2026.10.26'); sys.exit(0)
url = args[-1]
seconds = float(os.environ.get('FAKE_YTDLP_SECONDS', '6'))

if '--dump-single-json' in args:
    vid = url.rsplit('=', 1)[-1]
    print(json.dumps(dict(id=vid, title=f'Video {vid}', duration=seconds, webpage_url=url, formats=[
        dict(format_id='v264', vcodec='avc1.64001f', acodec='none', height=180, width=320, tbr=300, protocol='https'),
        dict(format_id='a-aac', vcodec='none', acodec='mp4a.40.2', abr=128, protocol='https', language_preference=10, format_note='original'),
    ])))
    sys.exit(0)

fmt = args[args.index('-f') + 1]
ff = os.environ.get('TUBES_FFMPEG', 'ffmpeg')
if fmt == 'v264': src, codec = ['-f', 'lavfi', '-i', f'testsrc=size=320x180:rate=25:duration={seconds}'], ['-c:v', 'libx264', '-preset', 'ultrafast', '-g', '25', '-pix_fmt', 'yuv420p']
else: src, codec = ['-f', 'lavfi', '-i', f'sine=frequency=440:duration={seconds}'], ['-c:a', 'aac']
sys.exit(subprocess.call([ff, '-hide_banner', '-loglevel', 'error', '-nostdin', *src, *codec, '-f', 'mp4', '-movflags', 'frag_keyframe+empty_moov+default_base_moof', 'pipe:1']))
