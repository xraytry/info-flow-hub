import importlib
import json
import os
from pathlib import Path
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

project=sys.argv[1]
rss='''<?xml version="1.0"?><rss version="2.0"><channel><title>Local fixture</title><link>http://127.0.0.1/</link><description>Fixture</description><item><title>Sandbox item</title><link>http://127.0.0.1/item/1</link><guid>fixture-1</guid><description>Local content</description><pubDate>Fri, 02 Oct 2026 12:00:00 GMT</pubDate></item></channel></rss>'''
html='''<!doctype html><html><body><article><h2><a href="/item/1">Sandbox item</a></h2><p>Local content</p></article></body></html>'''

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        content=rss if self.path=='/feed' else html
        payload=content.encode()
        self.send_response(200)
        self.send_header('Content-Type','application/rss+xml' if self.path=='/feed' else 'text/html')
        self.send_header('Content-Length',str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    def log_message(self,*args):pass

server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
thread=threading.Thread(target=server.serve_forever,daemon=True)
thread.start()
url=f'http://127.0.0.1:{server.server_port}'
checks=[]
try:
    if project=='forum-rss-adapter':
        sys.path.insert(0,str(Path.cwd()))
        from adapters import nodeseek
        fetched=nodeseek.fetch(url=url+'/feed')
        assert len(fetched.items)==1 and fetched.items[0].title=='Sandbox item'
        checks.append('real_local_http_rss_fetch_and_parse')
        os.environ['FORUM_RSS_DATA_DIR']='/tmp/forum-rss-fixture/data'
        os.environ['FORUM_RSS_FEEDS_DIR']='/tmp/forum-rss-fixture/feeds'
        os.environ['FORUM_RSS_LOGS_DIR']='/tmp/forum-rss-fixture/logs'
        os.environ['FORUM_RSS_DB']='/tmp/forum-rss-fixture/forum.sqlite3'
        app=importlib.import_module('app')
        from fastapi.testclient import TestClient
        client=TestClient(app.app)
        response=client.get('/health')
        assert response.status_code==200
        checks.append('health_endpoint_against_disposable_sqlite')
    else:
        sys.path.insert(0,str(Path.cwd()))
        from backend.app.fetchers import fetch_rss,fetch_http_scrape
        items=fetch_rss({'feed_url':url+'/feed'})
        assert len(items)==1 and items[0].title=='Sandbox item'
        checks.append('real_local_http_rss_fetch_and_parse')
        items=fetch_http_scrape({'list_url':url+'/page','item_selector':'article','title_selector':'h2','link_selector':'a','content_selector':'p'})
        assert len(items)==1 and items[0].title=='Sandbox item'
        checks.append('real_local_http_scrape_and_selector_parse')
        os.environ['INFO_FLOW_DB']='/tmp/info-flow-fixture.sqlite3'
        from backend.app.main import app
        from fastapi.testclient import TestClient
        with TestClient(app) as client:
            response=client.get('/api/health')
            assert response.status_code==200
            response=client.get('/api/sources')
            assert response.status_code==200
        checks.append('backend_startup_and_health_against_disposable_sqlite')
    print(json.dumps({'status':'PASS','checks':checks}))
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
