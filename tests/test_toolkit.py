#!/usr/bin/env python3
"""Offline integration tests with a fake local Ollama API. No model downloads."""
import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/'nbai.py'

class FakeOllama(BaseHTTPRequestHandler):
    def log_message(self,*args):
        pass
    def body(self, code, obj):
        raw=json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def do_GET(self):
        if self.path=='/api/tags':
            self.body(200,{'models':[{'name':'llama3.2:3b','size':2000000000},{'name':'qwen2.5-coder:7b','size':4700000000},{'name':'deepseek-r1:8b','size':5200000000},{'name':'embeddinggemma','size':120000000},{'name':'gemma4:cloud','size':1}]})
        elif self.path=='/api/version': self.body(200,{'version':'0.40.11-test'})
        elif self.path=='/api/ps': self.body(200,{'models':[]})
        else: self.body(404,{'error':'Unknown'})
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path=='/api/chat':
            self.body(200,{'message':{'role':'assistant','content':'Mock answer from '+body['model']},'eval_count':20,'eval_duration':1000000000,'load_duration':100000000})
        elif self.path=='/api/embed':
            # simple deterministic vectors dependent on whether content mentions 'python'
            self.body(200,{'embeddings':[[1.0,0.0] if 'python' in x.lower() else [0.0,1.0] for x in body['input']]})
        elif self.path=='/api/generate': self.body(200,{'done':True})
        else: self.body(404,{'error':'Unknown'})

class ToolkitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),FakeOllama)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(timeout=3)
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env=os.environ.copy()
        self.env['NBAI_OLLAMA_URL']=f'http://127.0.0.1:{self.server.server_port}'
        self.env['XDG_DATA_HOME']=self.tmp.name
    def runapp(self,*args,input=None,ok=True):
        result=subprocess.run([sys.executable,str(APP),*args],input=input,text=True,env=self.env,capture_output=True,timeout=30)
        if ok:
            self.assertEqual(result.returncode,0,result.stderr)
        return result
    def test_status_doctor_and_bench(self):
        res=self.runapp('status','--json')
        self.assertIn('llama3.2:3b',res.stdout)
        res=self.runapp('doctor','--json')
        self.assertTrue(json.loads(res.stdout)['api_ok'])
        res=self.runapp('bench','--models','llama3.2:3b,qwen2.5-coder:7b','--json')
        self.assertEqual(len(json.loads(res.stdout)),2)
    def test_roles_and_cloud_block(self):
        self.assertIn('qwen2.5-coder:7b',self.runapp('ask','--model','code','sample').stdout)
        bad=self.runapp('ask','--model','gemma4:cloud','hello',ok=False)
        self.assertNotEqual(bad.returncode,0)
        self.assertIn('Cloud models are blocked',bad.stderr)
    def test_index_grounded_and_search(self):
        project=Path(self.tmp.name)/'project'; project.mkdir()
        (project/'howto.py').write_text('python code can be documented\n'*20)
        (project/'notes.md').write_text('cats love boxes\n'*15)
        (project/'.env').write_text('secret=never_index_this')
        out=self.runapp('index',str(project))
        self.assertIn('Indexed/updated: 2',out.stdout)
        out=self.runapp('search','python','--json')
        self.assertIn('howto.py',out.stdout)
        self.assertNotIn('.env',out.stdout)
        out=self.runapp('ask','--grounded','python indexing')
        self.assertIn('Mock answer',out.stdout)
        again=self.runapp('index',str(project))
        self.assertIn('unchanged: 2',again.stdout)
    def test_profile_import_is_private_and_not_auto_shared(self):
        private=Path(self.tmp.name)/'input.md'
        private.write_text('Private technology context. Phone number example: 555-0100')
        imported=self.runapp('profile-import',str(private))
        self.assertIn('Private profile imported',imported.stdout)
        dest=Path(self.tmp.name)/'nbai/context/private_profile.md'
        self.assertEqual(dest.stat().st_mode&0o777,0o600)
        self.assertIn('Phone number',dest.read_text())
    def test_mcp_protocol_and_opt_in_search(self):
        msgs='\n'.join(json.dumps(x) for x in [
            {'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18'}},
            {'jsonrpc':'2.0','method':'notifications/initialized'},
            {'jsonrpc':'2.0','id':2,'method':'tools/list'},
            {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'local_code','arguments':{'prompt':'Review this'}}},
            {'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'local_search','arguments':{'query':'private information'}}},
        ])+'\n'
        r=self.runapp('mcp',input=msgs)
        lines=[json.loads(x) for x in r.stdout.splitlines()]
        self.assertEqual(len(lines),4)
        self.assertEqual(lines[0]['result']['protocolVersion'],'2025-06-18')
        self.assertGreater(len(lines[1]['result']['tools']),3)
        self.assertIn('Mock answer',lines[2]['result']['content'][0]['text'])
        self.assertTrue(lines[3]['result']['isError'])
    def test_mcp_merge_preserves_existing(self):
        config=Path(self.tmp.name)/'mcp_config.json'
        config.write_text(json.dumps({'mcpServers':{'ollama':{'command':'existing'}}}))
        out=self.runapp('mcp-install','--config',str(config))
        self.assertIn('Backup',out.stdout)
        value=json.loads(config.read_text())
        self.assertEqual(value['mcpServers']['ollama']['command'],'existing')
        self.assertIn('nightbreed-local-ai',value['mcpServers'])
        out=self.runapp('mcp-install','--config',str(config))
        self.assertIn('already installed',out.stdout)
        self.assertTrue(list(config.parent.glob('*.backup-*')))

if __name__=='__main__':
    unittest.main()
