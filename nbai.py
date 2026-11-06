#!/usr/bin/env python3
"""NightBreedLabs local-first Ollama toolkit. Python 3.9+, stdlib only."""
import argparse
import datetime as dt
import fnmatch
import json
import math
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import stat
import subprocess
import sys
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

VERSION = '1.1.0'
BASE = os.environ.get('NBAI_OLLAMA_URL', 'http://127.0.0.1:11434').rstrip('/')
DOCS_URL = os.environ.get('NBAI_DOCS_URL', 'http://127.0.0.1:3001').rstrip('/')
DOCS_KEY_FILE = Path(os.environ.get('NBAI_DOCS_KEY_FILE', str(Path.home() / '.local/share/anythingllm/agent-api.key')))
DOCS_WORKSPACES = tuple(w.strip() for w in os.environ.get('NBAI_DOCS_WORKSPACES', 'benefits-research').split(',') if w.strip())
DOCS_SERVICE = 'anythingllm.service'
DOCS_IDLE_UNIT = 'anythingllm-idle-stop'
DOCS_IDLE_SECONDS = int(os.environ.get('NBAI_DOCS_IDLE_SECONDS', '60'))
DATA = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'nbai'
DB = DATA / 'index.sqlite3'
ROLES = {
    'fast': os.environ.get('NBAI_FAST_MODEL', 'hermes3:8b'),
    'code': os.environ.get('NBAI_CODE_MODEL', 'qwen2.5-coder:7b'),
    'reason': os.environ.get('NBAI_REASON_MODEL', 'deepseek-r1:8b'),
}
EXCLUDE_DIRS = {'.git', '.hg', '.svn', 'node_modules', '.venv', 'venv', 'dist', 'build', '__pycache__', '.next', '.cache', '.idea', '.vscode'}
TEXT_EXTS = {'.txt', '.md', '.rst', '.py', '.sh', '.bash', '.js', '.jsx', '.ts', '.tsx', '.java', '.go', '.rs', '.c', '.h', '.cpp', '.hpp', '.json', '.toml', '.yaml', '.yml', '.xml', '.css', '.html'}
SENSITIVE_PATTERNS = {'.env', '.env.*', '*secret*', '*credential*', '*.pem', '*.key', '*.p12', '*.sqlite*', '*.db', 'id_rsa*', 'id_ed25519*', 'known_hosts', 'authorized_keys'}


def log(*parts):
    print(*parts, file=sys.stderr)


def require_local(url=BASE):
    u = urlparse(url)
    if u.scheme != 'http' or u.hostname not in ('localhost', '127.0.0.1', '::1') or u.username or u.password or u.path not in ('', '/') or u.query or u.fragment:
        raise ValueError('Only a plain HTTP loopback Ollama server is allowed (security-first default). Set NBAI_OLLAMA_URL=http://127.0.0.1:11434')
    return url.rstrip('/')


def api(path, payload=None, timeout=180):
    base = require_local()
    if not path.startswith('/') or not path.startswith('/api/'):
        raise ValueError('Unsupported API route')
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    req = Request(base + path, data=data, headers={'Content-Type': 'application/json'} if data else {}, method='POST' if data is not None else 'GET')
    try:
        with urlopen(req, timeout=timeout) as r:
            result = r.read(20 * 1024 * 1024 + 1)
            if len(result) > 20 * 1024 * 1024:
                raise ValueError('Ollama response exceeds 20 MiB safety limit')
            return json.loads(result)
    except HTTPError as exc:
        detail = exc.read(500).decode('utf-8', errors='replace')
        raise RuntimeError(f'Ollama HTTP {exc.code}: {detail}') from exc
    except URLError as exc:
        raise RuntimeError(f'Ollama unreachable on {base}: {exc.reason}') from exc


def docs_ready(base):
    try:
        with urlopen(base + '/api/ping', timeout=2) as r:
            return r.status == 200
    except (OSError, ValueError):
        return False


def docs_systemctl(*cmd):
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=False)


def docs_start(base):
    """Start the on-demand service and cancel any pending idle stop."""
    docs_systemctl('systemctl', '--user', 'stop', DOCS_IDLE_UNIT + '.timer')
    if docs_ready(base):
        return
    docs_systemctl('systemctl', '--user', 'start', '--no-block', DOCS_SERVICE)
    deadline = time.time() + 60
    while time.time() < deadline:
        if docs_ready(base):
            return
        time.sleep(0.5)
    raise RuntimeError('Document library did not start; check: systemctl --user status ' + DOCS_SERVICE)


def docs_release():
    """Free the service's memory shortly after the last call."""
    docs_systemctl('systemd-run', '--user', '--quiet', '--collect', '--unit=' + DOCS_IDLE_UNIT, f'--on-active={DOCS_IDLE_SECONDS}', 'systemctl', '--user', 'stop', DOCS_SERVICE)


def docs_api(path, payload, timeout=280):
    """POST to the loopback AnythingLLM developer API. The key is never logged or returned."""
    base = require_local(DOCS_URL)
    if not path.startswith('/api/v1/'):
        raise ValueError('Unsupported document API route')
    try:
        key = DOCS_KEY_FILE.read_text(encoding='utf-8').strip()
    except OSError as exc:
        raise RuntimeError('Document library key file is unavailable') from exc
    req = Request(base + path, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key}, method='POST')
    docs_start(base)
    try:
        with urlopen(req, timeout=timeout) as r:
            return json.loads(r.read(20 * 1024 * 1024))
    except HTTPError as exc:
        raise RuntimeError(f'Document library HTTP {exc.code}') from exc
    except URLError as exc:
        raise RuntimeError(f'Document library unreachable on {base}: {exc.reason}') from exc
    finally:
        docs_release()


def docs_workspace(args):
    workspace = args.get('workspace', DOCS_WORKSPACES[0] if DOCS_WORKSPACES else '')
    if workspace not in DOCS_WORKSPACES:
        raise ValueError('workspace is not enabled for agents; allowed: ' + ', '.join(DOCS_WORKSPACES))
    return workspace


def docs_search(query, workspace, limit=8):
    result = docs_api(f'/api/v1/workspace/{workspace}/vector-search', {'query': query, 'topN': limit, 'scoreThreshold': 0.2})
    return [{'source': (r.get('metadata') or {}).get('title'), 'score': r.get('score'), 'text': r.get('text')} for r in result.get('results', [])]


def docs_ask(question, workspace):
    # A new session each call keeps earlier answers out of the model's context.
    session = 'agent-' + dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    result = docs_api(f'/api/v1/workspace/{workspace}/chat', {'message': question, 'mode': 'query', 'sessionId': session})
    if result.get('error'):
        raise RuntimeError(str(result['error']))
    return {'answer': result.get('textResponse'), 'sources': sorted({s.get('title') for s in result.get('sources', []) if s.get('title')})}


def models():
    return api('/api/tags').get('models', [])


def local_names():
    return {name for m in models() if (name := (m.get('name') or m.get('model') or '')) and not name.lower().endswith(':cloud')}


def local_model(spec):
    model = ROLES.get(spec, spec)
    if ':cloud' in model.lower():
        raise ValueError('Cloud models are blocked by this toolkit. Use the stock Ollama CLI deliberately for cloud tasks.')
    return model


def installed_model(spec):
    """Resolve Ollama's implicit :latest tag against actual /api/tags names.

    Keep an explicit version tag intact. Return the exact server-reported name
    so indexing, lookup and model requests consistently use one identifier.
    """
    requested = local_model(spec)
    available = local_names()
    candidates = [requested]
    if ':' not in requested:
        candidates.append(requested + ':latest')
    elif requested.endswith(':latest'):
        candidates.append(requested[:-len(':latest')])
    for candidate in candidates:
        if candidate in available:
            return candidate
    present = ', '.join(sorted(available)) or '(none)'
    raise ValueError(
        f'Model {requested!r} not found on Ollama server {require_local()}. '
        f'Server reports: {present}. Check `nbai status` and `ollama list`. '
        'If they differ, verify the Ollama service address and model directory. '
        'Download to the same server with `ollama pull MODEL` only if needed.'
    )


def chat(model, prompt, system='', num_ctx=None, temperature=None, keep_alive=0, timeout=300):
    model = installed_model(model)
    payload = {'model': model, 'messages': [], 'stream': False, 'keep_alive': keep_alive}
    if system:
        payload['messages'].append({'role': 'system', 'content': system})
    payload['messages'].append({'role': 'user', 'content': prompt})
    options = {}
    if num_ctx is not None:
        if num_ctx < 512 or num_ctx > 131072:
            raise ValueError('Context must be between 512 and 131072 tokens')
        options['num_ctx'] = num_ctx
    if temperature is not None:
        options['temperature'] = temperature
    if options:
        payload['options'] = options
    return api('/api/chat', payload, timeout=timeout)


def answer_text(response):
    msg = response.get('message', {})
    return msg.get('content', '') or '(No final answer content; model may have produced reasoning only.)'


def read_prompt(args):
    if getattr(args, 'file', None):
        p = Path(args.file).expanduser()
        if p.stat().st_size > 256 * 1024:
            raise ValueError('Prompt file exceeds 256 KiB. Use indexing/search for larger projects.')
        return p.read_text(encoding='utf-8')
    if getattr(args, 'prompt', None):
        return ' '.join(args.prompt)
    if not sys.stdin.isatty():
        text = sys.stdin.read(256 * 1024 + 1)
        if len(text) > 256 * 1024:
            raise ValueError('Piped prompt exceeds 256 KiB')
        return text
    raise ValueError('Provide prompt text, --file FILE, or pipe text from stdin')


def cmd_ask(args):
    prompt = read_prompt(args)
    if not prompt.strip():
        raise ValueError('Empty prompt')
    if args.grounded:
        prompt = grounded_prompt(prompt, args.embed_model)
    role_sys = {'fast': 'Give a clear, concise, practical answer.', 'code': 'Act as a careful programming assistant. Prefer secure, portable solutions and explain assumptions.', 'reason': 'Reason carefully and communicate conclusions clearly.'}
    response = chat(args.model, prompt, args.system or role_sys.get(args.model, ''), args.ctx, args.temperature, args.keep_alive, args.timeout)
    output = json.dumps(response, indent=2) if args.json else answer_text(response)
    if args.output:
        p = Path(args.output).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(output + '\n', encoding='utf-8')
        print(f'Wrote {p}')
    else:
        print(output)


def cmd_status(args):
    result = {'server': BASE, 'models': models(), 'running': api('/api/ps').get('models', [])}
    if args.json:
        print(json.dumps(result, indent=2))
        return
    print(f'Ollama: {BASE}\nInstalled:')
    for m in result['models']:
        print(f"  {m.get('name', '?'):<28} {m.get('size', 0)/1024**3:.2f} GiB {'[cloud]' if m.get('name','').endswith(':cloud') else ''}")
    print('Loaded:')
    for m in result['running']:
        print(f"  {m.get('name', '?'):<28} {m.get('size', 0)/1024**3:.2f} GiB")
    if not result['running']:
        print('  (none)')


def cmd_doctor(args):
    d = {'platform': platform.platform(), 'python': sys.version.split()[0], 'url': BASE, 'systemd_user': shutil.which('systemctl') is not None,
         'ollama_binary': shutil.which('ollama'), 'vulkaninfo': shutil.which('vulkaninfo'), 'render_nodes': sorted(str(p) for p in Path('/dev/dri').glob('renderD*'))}
    d['systemd_user_service'] = None
    if shutil.which('systemctl'):
        try:
            x = subprocess.run(['systemctl', '--user', 'is-active', 'ollama.service'], capture_output=True, text=True, timeout=5)
            d['systemd_user_service'] = x.stdout.strip() or 'not active'
        except Exception:
            d['systemd_user_service'] = 'unavailable'
    try:
        d['server_version'] = api('/api/version').get('version')
        d['installed_models'] = [x.get('name') for x in models()]
        d['loaded_models'] = [{k: m.get(k) for k in ('name', 'size', 'size_vram')} for m in api('/api/ps').get('models', [])]
        d['api_ok'] = True
    except Exception as exc:
        d['api_ok'] = False
        d['api_error'] = str(exc)
    if args.json:
        print(json.dumps(d, indent=2))
    else:
        for k,v in d.items():
            print(f'{k:23}: {v}')
        print('\nGPU inference: run `ollama ps` while a model is responding and inspect PROCESSOR; use `journalctl --user -u ollama.service -b` to inspect backend detection.')
        print('The Radeon 680M is NOT listed as an officially supported ROCm GPU; Vulkan is worth testing, but must be measured, not assumed.')


def cmd_bench(args):
    chosen = [local_model(m.strip()) for m in args.models.split(',') if m.strip()]
    if not chosen:
        raise ValueError('At least one model is required')
    results=[]
    for model in chosen:
        for i in range(args.runs):
            print(f'Benchmarking {model} ({i+1}/{args.runs})...', file=sys.stderr)
            st = time.monotonic()
            r = chat(model, args.prompt, num_ctx=args.ctx, keep_alive='0' if args.unload else '5m', timeout=args.timeout)
            wall = time.monotonic()-st
            n = r.get('eval_count') or 0
            seconds = (r.get('eval_duration') or 0)/1e9
            rec={'model': model, 'run': i+1, 'wall_seconds': round(wall, 2), 'output_tokens': n, 'tokens_per_second': round(n/seconds, 2) if seconds else None, 'load_seconds': round((r.get('load_duration') or 0)/1e9, 2)}
            results.append(rec)
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f'{"model":26} {"run":>3} {"wall(s)":>9} {"tok/s":>9} {"load(s)":>9}')
        for r in results:
            print(f"{r['model'][:26]:26} {r['run']:>3} {r['wall_seconds']:>9.2f} {str(r['tokens_per_second']):>9} {r['load_seconds']:>9.2f}")
        print('\nCompare same prompt/context on the same machine. Generated token speed excludes model load and prompt processing.')


def db_connect():
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    conn = sqlite3.connect(DB)
    try:
        os.chmod(DB, 0o600)
    except OSError:
        pass
    conn.execute('PRAGMA foreign_keys=ON')
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL, embed_model TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY, path TEXT NOT NULL, chunk_index INTEGER NOT NULL, text TEXT NOT NULL, vector TEXT NOT NULL, FOREIGN KEY(path) REFERENCES files(path) ON DELETE CASCADE);
    CREATE INDEX IF NOT EXISTS chunks_path_idx ON chunks(path);
    ''')
    return conn


def embed(texts, model):
    model = installed_model(model)
    data = api('/api/embed', {'model':model, 'input':texts, 'truncate':False, 'keep_alive':'15s'}, timeout=300)
    vec = data.get('embeddings', [])
    if len(vec) != len(texts):
        raise RuntimeError('Unexpected Ollama embedding result length')
    return vec


def file_allowed(path):
    return path.suffix.lower() in TEXT_EXTS and not any(fnmatch.fnmatch(path.name.lower(), pattern) for pattern in SENSITIVE_PATTERNS)


def chunks_of(text, width=1400, overlap=200):
    text = text.replace('\r\n','\n')
    result=[]
    for start in range(0, len(text), width-overlap):
        part=text[start:start+width]
        if part:
            result.append(part)
        if start+width>=len(text):
            break
    return result


def cmd_index(args):
    root = Path(args.path).expanduser().resolve()
    if not root.is_dir():
        raise ValueError('Index path must be an existing directory')
    if root == Path.home().resolve() or root == Path('/'):
        raise ValueError('Index a specific project directory, not the entire home directory or root filesystem')
    model = installed_model(args.model)
    conn = db_connect()
    added=0; unchanged=0; skipped=0; count=0
    for base, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith('.') and not (Path(base)/d).is_symlink()]
        for name in files:
            path=Path(base)/name
            if not file_allowed(path) or path.is_symlink():
                continue
            count+=1
            if count>args.max_files:
                log('Reached --max-files limit; stopping safely')
                break
            try:
                s=path.stat()
                if s.st_size>args.max_bytes:
                    skipped+=1; continue
                absolute=str(path.resolve())
                old=conn.execute('SELECT size,mtime_ns,embed_model FROM files WHERE path=?',(absolute,)).fetchone()
                if old==(s.st_size,s.st_mtime_ns,model):
                    unchanged+=1; continue
                text=path.read_text(encoding='utf-8')
                if '\x00' in text:
                    skipped+=1; continue
                portions=chunks_of(text)
                if len(portions)>args.max_chunks_per_file:
                    skipped+=1; continue
                vectors=[]
                for i in range(0,len(portions),12):
                    vectors.extend(embed(portions[i:i+12], model))
                with conn:
                    conn.execute('DELETE FROM files WHERE path=?', (absolute,))
                    conn.execute('INSERT INTO files VALUES(?,?,?,?)', (absolute,s.st_size,s.st_mtime_ns,model))
                    conn.executemany('INSERT INTO chunks(path,chunk_index,text,vector) VALUES(?,?,?,?)', ((absolute,i,t,json.dumps(v,separators=(',',':'))) for i,(t,v) in enumerate(zip(portions,vectors))))
                added+=1
                if args.verbose:
                    print(f'Indexed {path} ({len(portions)} chunks)')
            except (OSError, UnicodeError, RuntimeError, ValueError) as exc:
                skipped+=1
                log(f'Skipped {path}: {exc}')
        if count>args.max_files:
            break
    conn.close()
    print(f'Indexed/updated: {added}, unchanged: {unchanged}, skipped: {skipped}; DB: {DB}')
    print('Only explicitly chosen project files are indexed. Review source trees for secrets before indexing.')


def search_local(query, model='embeddinggemma', limit=5):
    if not DB.exists():
        return [{'error':'No index yet. Run `nbai index /path/to/your/project` after installing an embedding model.'}]
    model = installed_model(model)
    v=embed([query],model)[0]
    magnitude=math.sqrt(sum(float(x)**2 for x in v)) or 1.0
    con=db_connect()
    rows=con.execute('SELECT path,chunk_index,text,vector FROM chunks JOIN files USING(path) WHERE files.embed_model=?', (model,)).fetchall()
    con.close()
    matches=[]
    for path,i,txt,vjson in rows:
        w=json.loads(vjson)
        if len(v)!=len(w):
            continue
        norm=math.sqrt(sum(float(x)**2 for x in w)) or 1.0
        score=sum(float(a)*float(b) for a,b in zip(v,w))/(magnitude*norm)
        matches.append({'path':path, 'chunk':i, 'score':round(score,4), 'snippet':txt[:1400]})
    return sorted(matches, key=lambda x:x['score'], reverse=True)[:limit]


def grounded_prompt(question, embed_model='embeddinggemma'):
    matches=search_local(question, embed_model, limit=3)
    excerpts=[f"SOURCE: {m['path']} (chunk {m['chunk']})\n{m['snippet'][:1100]}" for m in matches if 'snippet' in m]
    if not excerpts:
        raise ValueError('Local search index empty. Run `ollama pull embeddinggemma`, then `nbai index /path/to/your/project`.')
    return ('Answer the QUESTION using the following LOCAL REFERENCE EXCERPTS. '
            'State when evidence is missing, do not invent facts, and identify filenames used.\n\n'
            + '\n\n'.join(excerpts) + '\n\nQUESTION: ' + question)


def cmd_profile_import(args):
    source=Path(args.file).expanduser().resolve(strict=True)
    if not source.is_file() or source.stat().st_size>128*1024:
        raise ValueError('Import a regular UTF-8 Markdown file no larger than 128 KiB')
    content=source.read_text(encoding='utf-8')
    destination=DATA/'context'/'private_profile.md'
    destination.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    destination.parent.chmod(0o700)
    if destination.exists() and not args.replace:
        raise ValueError(f'{destination} already exists; use --replace after reviewing your private profile')
    if destination.is_symlink():
        raise ValueError('Refusing to replace a symlink')
    if destination.exists():
        backup=destination.with_name('private_profile.backup-'+dt.datetime.now().strftime('%Y%m%d-%H%M%S')+'.md')
        if backup.exists():
            raise ValueError('Backup collision')
        shutil.copy2(destination,backup)
        backup.chmod(0o600)
        print(f'Previous profile backed up to {backup}')
    temp=destination.with_name('private_profile.md.tmp')
    with temp.open('w',encoding='utf-8') as fp:
        os.chmod(temp,0o600)
        fp.write(content)
    temp.replace(destination)
    print(f'Private profile imported at {destination} (mode 0600).')
    print(f'Optional local semantic index: nbai index "{destination.parent}"')
    print('WARNING: do not commit or share this private profile, and remember that MCP tool results are visible to the MCP client.')


def cmd_search(args):
    matches=search_local(' '.join(args.query), args.model, args.limit)
    if args.json:
        print(json.dumps(matches, indent=2))
    else:
        for m in matches:
            if 'error' in m:
                print(m['error']); continue
            print(f"\n{m['path']} [chunk {m['chunk']}, similarity {m['score']:.3f}]\n{m['snippet'][:700]}\n")


def mcp_tools():
    s={'type':'object','properties':{'prompt':{'type':'string','description':'Question or task. Send only non-secret text.'},'model':{'type':'string','description':'Optional locally installed model name.'}},'required':['prompt']}
    return [
        {'name':'local_fast','description':'Fast inference with an installed local Ollama model; responses are visible to the MCP client. Never invokes Ollama cloud models.', 'inputSchema':s},
        {'name':'local_code','description':'Local code analysis and review. MCP client receives the response. Does not execute code.', 'inputSchema':s},
        {'name':'local_reason','description':'Local deeper reasoning; MCP client receives the response.', 'inputSchema':s},
        {'name':'local_models','description':'List models available to the local Ollama server, with cloud tagged separately.', 'inputSchema':{'type':'object','properties':{}}},
        {'name':'local_search','description':'Opt-in semantic search of a user-created local project index; excerpts are shared with the MCP client. Requires NBAI_MCP_SEARCH_ENABLED=1.', 'inputSchema':{'type':'object','properties':{'query':{'type':'string'},'limit':{'type':'integer','minimum':1,'maximum':10}},'required':['query']}},
        {'name':'local_docs_search','description':'Search the shared AnythingLLM document library and return exact sourced passages, using no cloud model. Prefer this before web research on covered topics. Passages are visible to the MCP client.', 'inputSchema':{'type':'object','properties':{'query':{'type':'string','description':'Non-personal search text.'},'workspace':{'type':'string'},'limit':{'type':'integer','minimum':1,'maximum':10}},'required':['query']}},
        {'name':'local_docs_ask','description':'Answer from the shared document library with a local Ollama model, citing sources and refusing when documents do not cover it. Verify figures with local_docs_search.', 'inputSchema':{'type':'object','properties':{'question':{'type':'string'},'workspace':{'type':'string'}},'required':['question']}},
    ]


def mcp_call(name, args):
    if not isinstance(args,dict):
        raise ValueError('Arguments must be an object')
    if name in ('local_fast','local_code','local_reason'):
        prompt = args.get('prompt','')
        if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>30000:
            raise ValueError('prompt must be a non-empty string up to 30000 characters')
        role={'local_fast':'fast','local_code':'code','local_reason':'reason'}[name]
        model=args.get('model',role)
        if not isinstance(model,str):
            raise ValueError('model must be a string')
        out=answer_text(chat(model,prompt, num_ctx=8192 if role=='code' else 4096, timeout=300))
        return {'content':[{'type':'text','text':out}]}
    if name=='local_models':
        return {'content':[{'type':'text','text':json.dumps([{'name':m.get('name'),'size':m.get('size'),'is_cloud':m.get('name','').endswith(':cloud')} for m in models()])}]}
    if name=='local_search':
        if os.environ.get('NBAI_MCP_SEARCH_ENABLED') != '1':
            raise ValueError('MCP search disabled to protect private indexed files. Explicitly opt in by setting NBAI_MCP_SEARCH_ENABLED=1 in the MCP server environment.')
        query=args.get('query','')
        if not isinstance(query,str) or not query.strip() or len(query)>3000:
            raise ValueError('query must be a nonempty string <=3000 characters')
        lim=args.get('limit',5)
        if not isinstance(lim,int) or not 1<=lim<=10:
            raise ValueError('limit must be integer 1..10')
        return {'content':[{'type':'text','text':json.dumps(search_local(query,limit=lim))}]}
    if name in ('local_docs_search','local_docs_ask'):
        text=args.get('query' if name=='local_docs_search' else 'question','')
        if not isinstance(text,str) or not text.strip() or len(text)>3000:
            raise ValueError('query must be a nonempty string <=3000 characters')
        workspace=docs_workspace(args)
        if name=='local_docs_ask':
            return {'content':[{'type':'text','text':json.dumps(docs_ask(text,workspace))}]}
        lim=args.get('limit',8)
        if not isinstance(lim,int) or not 1<=lim<=10:
            raise ValueError('limit must be integer 1..10')
        return {'content':[{'type':'text','text':json.dumps(docs_search(text,workspace,lim))}]}
    raise ValueError(f'Unknown tool: {name}')


def cmd_mcp(_args):
    """MCP stdio newline-delimited JSON-RPC. Absolutely no stdout outside JSON-RPC."""
    require_local()
    for line in sys.stdin:
        try:
            req=json.loads(line)
            if not isinstance(req,dict):
                continue
            mid=req.get('id')
            method=req.get('method','')
            params=req.get('params') or {}
            if not isinstance(params,dict):
                params={}
            if method=='initialize':
                requested=params.get('protocolVersion','2025-03-26')
                version=requested if requested in ('2024-11-05','2025-03-26','2025-06-18','2025-11-25') else '2025-06-18'
                result={'protocolVersion':version,'capabilities':{'tools':{'listChanged':False}},'serverInfo':{'name':'nightbreed-local-ai','version':VERSION}}
            elif method=='tools/list':
                result={'tools':mcp_tools()}
            elif method=='tools/call':
                try:
                    result=mcp_call(params.get('name'),params.get('arguments') or {})
                except Exception as exc:
                    result={'content':[{'type':'text','text':str(exc)}],'isError':True}
            elif method=='ping':
                result={}
            elif method.startswith('notifications/'):
                continue
            else:
                if mid is not None:
                    print(json.dumps({'jsonrpc':'2.0','id':mid,'error':{'code':-32601,'message':'Method not found'}},separators=(',',':')), flush=True)
                continue
            if mid is not None:
                print(json.dumps({'jsonrpc':'2.0','id':mid,'result':result},separators=(',',':')), flush=True)
        except Exception as exc:
            log(f'MCP request failed: {exc}')


def cmd_mcp_install(args):
    path=Path(args.config).expanduser() if args.config else Path.home()/'.gemini/config/mcp_config.json'
    if path.exists():
        if path.is_symlink():
            raise ValueError('Refusing to modify symlinked MCP config')
        data=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data,dict):
            raise ValueError('Existing MCP configuration is not a JSON object')
    else:
        data={}
    servers=data.setdefault('mcpServers',{})
    if not isinstance(servers,dict):
        raise ValueError('mcpServers is not an object')
    entry={'command':sys.executable,'args':[str(Path(__file__).resolve()),'mcp']}
    if args.name in servers:
        if servers[args.name]==entry:
            print(f'MCP entry {args.name} already installed, no changes made.')
            return
        raise ValueError(f'Name {args.name} already exists; refusing overwrite. Existing servers are preserved.')
    servers[args.name]=entry
    if args.dry_run:
        print(json.dumps({args.name:entry},indent=2))
        print(f'Would merge into {path} (no changes written)')
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup=path.with_name(path.name+'.backup-'+dt.datetime.now().strftime('%Y%m%d-%H%M%S'))
        if backup.exists():
            raise ValueError('Backup filename already exists, retry later')
        shutil.copy2(path,backup)
        backup.chmod(0o600)
        print(f'Backup: {backup}')
    tmp=path.with_name(path.name+'.nbai.tmp')
    with tmp.open('w',encoding='utf-8') as fp:
        os.chmod(tmp,0o600)
        json.dump(data,fp,indent=2)
        fp.write('\n')
    tmp.replace(path)
    print(f'Merged MCP entry {args.name} into {path}. Refresh MCP servers in Antigravity.')


def cmd_profile(args):
    profiles={
        'balanced': {'OLLAMA_HOST':'127.0.0.1:11434','OLLAMA_CONTEXT_LENGTH':'4096','OLLAMA_NUM_PARALLEL':'1','OLLAMA_MAX_LOADED_MODELS':'1','OLLAMA_FLASH_ATTENTION':'1','OLLAMA_KV_CACHE_TYPE':'q8_0','OLLAMA_KEEP_ALIVE':'5m'},
        'coding': {'OLLAMA_HOST':'127.0.0.1:11434','OLLAMA_CONTEXT_LENGTH':'8192','OLLAMA_NUM_PARALLEL':'1','OLLAMA_MAX_LOADED_MODELS':'1','OLLAMA_FLASH_ATTENTION':'1','OLLAMA_KV_CACHE_TYPE':'q8_0','OLLAMA_KEEP_ALIVE':'15m'},
        'low-memory': {'OLLAMA_HOST':'127.0.0.1:11434','OLLAMA_CONTEXT_LENGTH':'2048','OLLAMA_NUM_PARALLEL':'1','OLLAMA_MAX_LOADED_MODELS':'1','OLLAMA_FLASH_ATTENTION':'1','OLLAMA_KEEP_ALIVE':'2m'},
    }
    env=profiles[args.name]
    print(f'SUGGESTED {args.name} environment settings (preview only; nothing modified):\n')
    for k,v in env.items():
        print(f'{k}={v}')
    print('\nFor systemd user service, place overrides in ~/.config/systemd/user/ollama.service.d/90-nbai.conf after reviewing hardware benchmarks.')
    print('Do not modify the current working service until you have established a performance baseline. q8_0 requires Flash Attention support.')
    print('On non-systemd distributions, set these environment variables in the launch environment of `ollama serve`.')


def cmd_unload(args):
    model=local_model(args.model)
    response=api('/api/generate',{'model':model,'keep_alive':0,'stream':False},timeout=90)
    print(f'Unloaded {model}: {response.get("done",False)}')


def main(argv=None):
    p=argparse.ArgumentParser(prog='nbai', description='Local-first Ollama toolkit; does not replace the existing Ollama installation.')
    p.add_argument('--version',action='version',version=VERSION)
    sub=p.add_subparsers(dest='cmd',required=True)
    s=sub.add_parser('status',help='List installed and loaded models'); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_status)
    s=sub.add_parser('doctor',help='Inspect API, model and GPU prerequisites'); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_doctor)
    s=sub.add_parser('ask',help='Ask a local model (fast/code/reason or literal model name)'); s.add_argument('prompt',nargs='*'); s.add_argument('--grounded',action='store_true',help='Use local project index excerpts before answering'); s.add_argument('--embed-model',default='embeddinggemma'); s.add_argument('-m','--model',default='fast'); s.add_argument('-f','--file'); s.add_argument('-o','--output'); s.add_argument('--system'); s.add_argument('--ctx',type=int); s.add_argument('--temperature',type=float); s.add_argument('--keep-alive',default='5m'); s.add_argument('--timeout',type=int,default=300); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_ask)
    s=sub.add_parser('bench',help='Compare same prompt across local models'); s.add_argument('--models',default='llama3.2:3b,qwen2.5-coder:7b,deepseek-r1:8b'); s.add_argument('--prompt',default='Explain in four sentences why indexing a source code project is useful.'); s.add_argument('--runs',type=int,choices=range(1,6),metavar='{1..5}',default=1); s.add_argument('--ctx',type=int,default=4096); s.add_argument('--unload',action='store_true',help='Unload model after each benchmark (cold test)'); s.add_argument('--timeout',type=int,default=300); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_bench)
    s=sub.add_parser('index',help='Index a specifically selected project using local embeddings'); s.add_argument('path'); s.add_argument('--model',default='embeddinggemma'); s.add_argument('--max-files',type=int,default=500); s.add_argument('--max-bytes',type=int,default=300000); s.add_argument('--max-chunks-per-file',type=int,default=80); s.add_argument('-v','--verbose',action='store_true'); s.set_defaults(func=cmd_index)
    s=sub.add_parser('profile-import',help='Privately import your Antigravity context Markdown (never included in this distributable)'); s.add_argument('file'); s.add_argument('--replace',action='store_true'); s.set_defaults(func=cmd_profile_import)
    s=sub.add_parser('search',help='Semantic search on your existing private local index'); s.add_argument('query',nargs='+'); s.add_argument('--model',default='embeddinggemma'); s.add_argument('--limit',type=int,default=5); s.add_argument('--json',action='store_true'); s.set_defaults(func=cmd_search)
    s=sub.add_parser('unload',help='Unload a local model from memory'); s.add_argument('model'); s.set_defaults(func=cmd_unload)
    s=sub.add_parser('mcp',help='Run an MCP stdio server for Antigravity or another MCP client'); s.set_defaults(func=cmd_mcp)
    s=sub.add_parser('mcp-install',help='Back up and merge an additive MCP server entry into Antigravity'); s.add_argument('--name',default='nightbreed-local-ai'); s.add_argument('--config'); s.add_argument('--dry-run',action='store_true'); s.set_defaults(func=cmd_mcp_install)
    s=sub.add_parser('profile',help='Preview optimization environments (never applies changes)'); s.add_argument('name',choices=['balanced','coding','low-memory'],default='balanced',nargs='?'); s.set_defaults(func=cmd_profile)
    args=p.parse_args(argv)
    try:
        return args.func(args) or 0
    except (ValueError,RuntimeError,sqlite3.Error,OSError) as exc:
        log('Error:',exc)
        return 1


if __name__=='__main__':
    sys.exit(main())
