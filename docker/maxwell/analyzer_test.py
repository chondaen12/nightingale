"""Exercise the app's persistent analyzer protocol, without CUDA warmup."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading

out = Path('/gpu-test/analyzer-test')
out.mkdir(exist_ok=True)
if 'TEST_AUDIO' not in os.environ:
    raise SystemExit('Set TEST_AUDIO to a short audio file mounted inside the container')
env = dict(os.environ, HF_HOME='/data/models/huggingface',
           TORCH_HOME='/data/models/torch', NLTK_DATA='/data/models/nltk_data')
log = (out/'server.log').open('w')
p = subprocess.Popen([sys.executable, '/data/vendor/analyzer/server.py'],
                     stdout=subprocess.PIPE, stderr=log, text=True, env=env)
try:
    ready = json.loads(p.stdout.readline())
    print(ready, flush=True)
    def drain():
        for line in p.stdout:
            log.write(line); log.flush()
    threading.Thread(target=drain, daemon=True).start()
    with socket.create_connection(('127.0.0.1', ready['port']), timeout=1200) as sock:
        stream = sock.makefile('rw')
        def send(data):
            stream.write(json.dumps(data)+'\n'); stream.flush()
        send({'type':'hello', 'token':ready['token']})
        assert json.loads(stream.readline())['type'] == 'hello_ack'
        full = '--full' in sys.argv
        separators = [arg for arg in sys.argv[1:] if arg != '--full'] or ['karaoke']
        for separator in separators:
            send({'type':'analyze', 'hash':'integration_'+separator+('_full' if full else ''),
                  'audio_path':os.environ.get('TEST_AUDIO', '/gpu-test/input.wav'), 'cache_path':str(out),
                  'separator':separator, 'skip_transcription':not full,
                  'model':'large-v3', 'beam_size':1, 'batch_size':1,
                  'language':os.environ.get('TEST_LANGUAGE') if full else None})
            while True:
                event=json.loads(stream.readline())
                print(event, flush=True)
                if event['type']=='error':
                    raise RuntimeError(event)
                if event['type']=='done':
                    break
        send({'type':'quit'})
    p.wait(timeout=30)
    assert p.returncode == 0
finally:
    if p.poll() is None:
        p.kill(); p.wait()
    log.close()
