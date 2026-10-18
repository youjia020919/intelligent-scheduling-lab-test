from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import contextlib, io, json, os, sys, tempfile, traceback, importlib.util, shutil
ROOT=Path(__file__).resolve().parent
REPO=ROOT/'COOPA'
PAGE=ROOT/'index.html'
RUNS=Path(tempfile.gettempdir())/'scheduling_lab_coopa_runs'; RUNS.mkdir(parents=True,exist_ok=True)
NEEDED=['smolagents','instructor','litellm','ortools','pymoo','pyomo']
class Handler(BaseHTTPRequestHandler):
 def send(self,code,obj):
  body=json.dumps(obj,ensure_ascii=False,default=str).encode('utf-8');self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def do_GET(self):
  if urlparse(self.path).path=='/api/paper-extra':
   try:
    from paper_extra_solver import solve,DEFAULTS
    case=parse_qs(urlparse(self.path).query).get('case',[''])[0]
    if parse_qs(urlparse(self.path).query).get('defaults',[''])[0]=='1':
     if case not in DEFAULTS:raise ValueError('未知场景')
     self.send(200,{'case':case,'config':DEFAULTS[case]})
    else:self.send(200,solve(case))
   except ValueError as exc:self.send(400,{'error':str(exc)})
   except Exception as exc:self.send(500,{'error':str(exc)})
   return
  if urlparse(self.path).path=='/api/coopa/status':
   missing=[x for x in NEEDED if importlib.util.find_spec(x) is None]
   self.send(200,{'ready':not missing and bool(os.environ.get('OPENAI_API_KEY') or os.environ.get('OPENROUTER_API_KEY')) and (bool(shutil.which('glpsol')) or importlib.util.find_spec('highspy') is not None),'missing_packages':missing,'model_key_configured':bool(os.environ.get('OPENAI_API_KEY') or os.environ.get('OPENROUTER_API_KEY')),'repository_present':REPO.exists(),'glpk_available':bool(shutil.which('glpsol')),'highs_available':importlib.util.find_spec('highspy') is not None,'ipopt_available':bool(shutil.which('ipopt'))});return
  if urlparse(self.path).path in ['/','/index.html']:
   data=PAGE.read_bytes();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
  self.send(404,{'error':'Not found'})
 def do_POST(self):
  if urlparse(self.path).path=='/api/staff-flex':
   try:
    from staff_flex_solver import solve
    size=int(self.headers.get('Content-Length','0'))
    if size<1 or size>30000:raise ValueError('参数大小不符合要求')
    self.send(200,solve(json.loads(self.rfile.read(size))))
   except (ValueError,KeyError,TypeError) as exc:self.send(400,{'error':str(exc)})
   except Exception as exc:self.send(500,{'error':str(exc)})
   return
  if urlparse(self.path).path=='/api/paper-extra':
   try:
    from paper_extra_solver import solve
    size=int(self.headers.get('Content-Length','0'))
    if size<1 or size>20000:raise ValueError('参数大小不符合要求')
    data=json.loads(self.rfile.read(size))
    self.send(200,solve(str(data.get('case','')),data.get('config')))
   except (ValueError,KeyError,TypeError) as exc:self.send(400,{'error':str(exc)})
   except Exception as exc:self.send(500,{'error':str(exc)})
   return
  if urlparse(self.path).path!='/api/coopa/solve':self.send(404,{'error':'Not found'});return
  try:
   size=int(self.headers.get('Content-Length','0'))
   if size<1 or size>100000:self.send(400,{'error':'输入大小不符合要求'});return
   data=json.loads(self.rfile.read(size));problem=str(data.get('problem','')).strip();model=str(data.get('model','gpt-4.1')).strip()
   if len(problem)<20 or len(problem)>20000 or not model or len(model)>100:self.send(400,{'error':'请提供 20–20000 字的问题描述和模型名称'});return
   missing=[x for x in NEEDED if importlib.util.find_spec(x) is None]
   if missing or not (shutil.which('glpsol') or importlib.util.find_spec('highspy')) or not (os.environ.get('OPENAI_API_KEY') or os.environ.get('OPENROUTER_API_KEY')):self.send(503,{'error':'COOPA 尚未就绪','missing_packages':missing,'model_key_configured':bool(os.environ.get('OPENAI_API_KEY') or os.environ.get('OPENROUTER_API_KEY')),'glpk_available':bool(shutil.which('glpsol')),'highs_available':importlib.util.find_spec('highspy') is not None});return
   sys.path.insert(0,str(REPO));from apps.operations_research.or_agents.iterative_formulation import extract_formulation_with_refinement
   from apps.operations_research.formulation_utils import format_formulation_prompt
   from apps.operations_research.run import create_manager_agent
   folder=Path(tempfile.mkdtemp(prefix='run_',dir=RUNS));buf=io.StringIO()
   with contextlib.redirect_stdout(buf),contextlib.redirect_stderr(buf):
    formulation,evaluation,n=extract_formulation_with_refinement(problem_text=problem,max_iterations=3,formulation_model=model,evaluation_model=model,verbose=True)
    manager=create_manager_agent(model_id=model,working_directory=str(folder))
    result=manager.run(format_formulation_prompt(formulation),reset=True)
   (folder/'run.log').write_text(buf.getvalue(),encoding='utf8');(folder/'formulation.json').write_text(json.dumps(formulation.model_dump(),ensure_ascii=False,indent=2),encoding='utf8')
   self.send(200,{'result':str(result),'iterations':n,'formulation':formulation.model_dump(),'evaluation':evaluation.model_dump(),'run_id':folder.name})
  except Exception as exc:
   message=str(exc)
   if 'no credits remaining' in message.lower() or 'credit_balance_exhausted' in message.lower():
    self.send(402,{'error':'模型 API 账户没有可用额度。请检查 OpenAI API 账单与余额；额度更新后再试。也可先使用网页中的本地排程场景。'})
   else:
    self.send(500,{'error':message,'traceback':traceback.format_exc()[-3000:]})
if __name__=='__main__':
 port=int(os.environ.get('PORT','8765'))
 server=ThreadingHTTPServer(('0.0.0.0',port),Handler)
 print(f'Listening on port {port}',flush=True)
 server.serve_forever()
