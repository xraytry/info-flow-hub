import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HTML='''<!doctype html><html><body><article><h2><a href="/item/1">Sandbox CDP item</a></h2><p>Local content</p></article></body></html>'''
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        payload=HTML.encode()
        self.send_response(200)
        self.send_header('Content-Type','text/html')
        self.send_header('Content-Length',str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    def log_message(self,*args):pass

server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
thread=threading.Thread(target=server.serve_forever,daemon=True)
thread.start()
proc=None
stage='launch_fresh_local_browser'
result={}
try:
    executable='/usr/lib/chromium/chromium'
    if not Path(executable).is_file():raise FileNotFoundError()
    proc=subprocess.Popen([executable,'--headless','--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--disable-background-networking','--disable-component-update','--disable-sync','--no-first-run','--no-default-browser-check','--remote-debugging-address=127.0.0.1','--remote-debugging-port=9222','--remote-allow-origins=http://127.0.0.1:9222','--user-data-dir=/tmp/fresh-cdp-fixture','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,start_new_session=True)
    stage='wait_local_cdp_endpoint'
    ready=False
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        if proc.poll() is not None:raise RuntimeError('Browser exited')
        try:
            with urllib.request.urlopen('http://127.0.0.1:9222/json/version',timeout=0.5) as response:
                if response.status==200:ready=True;break
        except (OSError,urllib.error.URLError):pass
        time.sleep(0.1)
    if not ready:raise TimeoutError()
    stage='source_cdp_fetch'
    os.environ['CDP_URL']='http://127.0.0.1:9222'
    sys.path.insert(0,str(Path.cwd()/'backend'))
    from app.fetchers import fetch_cdp_browser
    items=fetch_cdp_browser({'url':f'http://127.0.0.1:{server.server_port}/page','item_selector':'article','title_selector':'h2','link_selector':'a','content_selector':'p','wait_seconds':0.2})
    assert len(items)==1 and items[0].title=='Sandbox CDP item'
    result={'status':'PASS','checks':['real_cdp_browser_local_navigation_and_dom_extract'],'item_count':len(items),'external_session_used':False}
except Exception as exc:
    result={'status':'FAIL','stage':stage,'exception_type':type(exc).__name__,'external_session_used':False}
    if isinstance(exc,urllib.error.HTTPError):
        result['http_status']=exc.code
        parsed=urllib.parse.urlparse(exc.url)
        result['failed_local_endpoint']=parsed.path
        if parsed.hostname=='127.0.0.1' and parsed.port==9222 and parsed.path=='/json/new':
            try:
                request=urllib.request.Request(exc.url,method='PUT')
                with urllib.request.urlopen(request,timeout=3) as response:
                    result['controlled_put_status']=response.status
            except Exception as probe_exc:
                result['controlled_put_exception_type']=type(probe_exc).__name__
finally:
    if proc is not None and proc.poll() is None:
        os.killpg(proc.pid,signal.SIGTERM)
        try:proc.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid,signal.SIGKILL)
            proc.communicate(timeout=3)
    server.shutdown();server.server_close();thread.join(timeout=2)
print(json.dumps(result))
sys.exit(0 if result.get('status')=='PASS' else 1)
