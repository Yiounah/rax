"""Native Gemini CLI development over a scoped RAX MCP socket and the operator's Sol route."""
from contextlib import contextmanager
import http.client
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import shutil
import socketserver
import threading
import time
from urllib.parse import urlsplit
import sys

from harness import agent_host
from harness.cli_runtime import reference_sources
from harness.isolated_cli.adapter import Adapter
from services.controller.storage import persist

NAME='gemini'
ACCOUNT='unconfigured'
PROVIDERS=('custom',)
MODEL='gpt-6.1-sol'
TOOLS=Path.home()/'.local/share/basal-a800-tools'
NODE=TOOLS/'node-v24.14.1-linux-x64'
HERE=Path(__file__).resolve().parent
ROUTES={f'/v1beta/models/{MODEL}:'+action for action in ('generateContent','streamGenerateContent','countTokens')}
def model(provider):return MODEL
def default_binary():return TOOLS/'clients/node_modules/@google/gemini-cli/bundle/gemini.js'
def installation(binary):return TOOLS/'clients'
def arguments(prompt,resume):
    return ['--skip-trust','-m',MODEL,'-o','stream-json',*(['--resume',resume] if resume else []),'-p',prompt]
def environment(home,*,install=None):
    return {'GEMINI_CLI_HOME':str(home),'GEMINI_API_KEY':'rax-session','GEMINI_MODEL':MODEL,
        'GOOGLE_GEMINI_BASE_URL':'http://rax-model.invalid','CI':'true','NO_COLOR':'1'}
def write_home(config,home,selected_model,socket):
    if selected_model!=MODEL:raise ValueError('Unexpected study model')
    folder=home/'.gemini'
    folder.mkdir(mode=0o700,exist_ok=True)
    persist(folder/'settings.json',{'model':{'name':MODEL},'telemetry':{'enabled':False},
        'security':{'auth':{'selectedType':'gemini-api-key'}},'experimental':{'enableAgents':False},
        'tools':{'exclude':['google_web_search','web_fetch','ask_user','activate_skill']},
        'mcpServers':{'auto_research':{'command':str(agent_host.agent_python()),'args':['-I','/tmp/rax-bridge/mcp_bridge.py',str(socket)],'timeout':900000,'trust':True}}})
    policies=folder/'policies';policies.mkdir(exist_ok=True)
    (policies/'tools.toml').write_text(''.join('[[rule]]\ntoolName = "'+name+'"\ndecision = "allow"\npriority = 100\n' for name in ('read_file','read_many_files','list_directory','glob','search_file_content','run_shell_command','write_file','replace','mcp_auto_research_*')))
def event(v):
    ident=v.get('session_id') if v.get('type')=='init' else None
    err=(v.get('message') or v.get('error')) if v.get('type')=='error' else None
    return ident,err,v.get('stats') if v.get('type')=='result' else None
def session_files(home,session_id):
    return [x.relative_to(home) for x in (home/'.gemini/tmp').glob('*/chats/*') if x.is_file() and not x.is_symlink()]

class Relay(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        route=urlsplit(self.path)
        if route.path not in ROUTES or route.query not in ('','alt=sse'):
            return self.send_error(403)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=80*1024**2:return self.send_error(413)
            body=self.rfile.read(size)
            upstream=http.client.HTTPConnection('127.0.0.1',self.server.port,timeout=420)
            upstream.request('POST',self.path,body,{'content-type':'application/json','x-goog-api-key':self.server.token})
            r=upstream.getresponse()
            self.send_response(r.status);self.send_header('Content-Type',r.getheader('Content-Type','application/json'));self.end_headers()
            while chunk:=r.read1(65536):
                self.wfile.write(chunk);self.wfile.flush()
        except (ConnectionError,TimeoutError):
            pass
        finally:
            if 'upstream' in locals():upstream.close()
            with self.server.audit.open('a') as out:
                out.write(json.dumps({'at':time.time(),'path':route.path,'http':r.status if 'r' in locals() else None,'bytes':size if 'size' in locals() else None})+'\n')

class Native(Adapter):
    def deploy(self,config,**kwargs):
        if config.subagents or config.agent_formal or config.agent_provider!='custom':
            raise ValueError('Gemini uses the scoped Sol route, serial agent and frozen-code evaluation')
        deployed=super().deploy(config,**kwargs)
        if config.adaptation_source:
            if config.adaptation_context!='clear':raise ValueError('Only frozen memory/code transfer is implemented')
            from services.adaptation import import_source
            deployed['resume_session']=import_source(config,deployed['workspace'],deployed[self.HOME_KEY])
        return deployed

    def agent_environment(self,config,deployed,socket):
        env=super().agent_environment(config,deployed,socket)
        env['NODE_OPTIONS']='--import=/tmp/rax-bridge/gemini_fetch.mjs'
        return env

    def sandbox(self,config,deployed,command):
        home=Path(deployed[self.HOME_KEY]).resolve();workspace=Path(deployed['workspace']).resolve()
        sock=agent_host.socket_path(config.root).parent
        args=[shutil.which('bwrap') or '/usr/bin/bwrap','--die-with-parent','--new-session','--unshare-net','--unshare-ipc','--unshare-uts','--unshare-pid','--dev','/dev','--proc','/proc','--tmpfs','/tmp']
        for name in ('/usr','/etc/ld.so.cache','/etc/localtime','/etc/passwd','/etc/group','/etc/fonts'):
            p=Path(name)
            if p.exists():args+=['--ro-bind',name,name]
        for name in ('/bin','/sbin','/lib','/lib64'):
            p=Path(name)
            if p.is_symlink():args+=['--symlink',os.readlink(p),name]
            elif p.exists():args+=['--ro-bind',name,name]
        for p in (NODE,TOOLS/'clients',agent_host.agent_python().parent.parent,config.root/'published',*(x for x,_ in reference_sources(config))):
            args+=['--ro-bind',str(p),str(p)]
        for p in (workspace,home,sock):args+=['--bind',str(p),str(p)]
        return args+['--ro-bind',str(agent_host.BRIDGE),'/tmp/rax-bridge/mcp_bridge.py','--ro-bind',str(HERE/'gemini_fetch.mjs'),'/tmp/rax-bridge/gemini_fetch.mjs','--chdir',str(workspace),'--',*command]

    @contextmanager
    def relay(self,config,deployed):
        class Server(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):daemon_threads=True
        sock=agent_host.socket_path(config.root).with_name('model.sock')
        sock.unlink(missing_ok=True)
        cred=self.credential(deployed)
        endpoint=urlsplit(cred.endpoint)
        if endpoint.hostname!='127.0.0.1':raise ValueError('Use the authorized local Sol profile')
        with Server(str(sock),Relay) as server:
            sock.chmod(0o600);server.port=endpoint.port
            server.token=cred.headers()['Authorization'].removeprefix('Bearer ')
            server.audit=config.root/self.HOME_NAME/'request-audit.jsonl'
            t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
            try:yield server
            finally:server.shutdown();t.join();sock.unlink(missing_ok=True)

_adapter=Native(sys.modules[__name__])
HOME_KEY,HOME_NAME,HOME_FILES=_adapter.HOME_KEY,_adapter.HOME_NAME,_adapter.HOME_FILES
deploy,redeploy,launch=_adapter.deploy,_adapter.redeploy,_adapter.launch
latest_session,last_error,record_subagents=_adapter.latest_session,_adapter.last_error,_adapter.record_subagents
