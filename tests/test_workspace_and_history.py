from __future__ import annotations
import csv, io, json, sys, tempfile, threading, unittest, urllib.error, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from ladder_climb.history import export_history, history_payload
from ladder_climb.schema import ValidationError, load_board
from ladder_climb.server import make_server
from ladder_climb.store import archive_campaign, board_lock, claim_rung, initialize, list_models, paths_for, review_rung, upsert_rung
TRACK={'id':'speed','label':'Speed','unit':'tok/s','baseline':100,'target':500,'direction':'higher'}
def make(root:Path,model='alpha'):
 return initialize(root,model.title(),'workspace test',[TRACK],model=model,model_name=model.title(),hardware='test')
class WorkspaceTests(unittest.TestCase):
 def setUp(self): self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);make(self.root);make(self.root,'beta')
 def tearDown(self):self.temp.cleanup()
 def test_independent_model_lock_and_timeout(self):
  with board_lock(paths_for(self.root,'alpha'),.1):
   result=upsert_rung(self.root,model='beta',track='speed',rung_id='B-1',value=1,status='testing',lock_timeout=.2)
   self.assertEqual(result['id'],'B-1')
   with self.assertRaises(TimeoutError):
    upsert_rung(self.root,model='alpha',track='speed',rung_id='A-1',value=1,status='testing',lock_timeout=.05)
 def test_duplicate_revision_terminal_timing_and_review(self):
  first=upsert_rung(self.root,model='alpha',track='speed',rung_id='A-1',value=0,status='testing')
  with self.assertRaises(ValidationError):upsert_rung(self.root,model='alpha',track='speed',rung_id='A-1',value=1,status='testing')
  done=upsert_rung(self.root,model='alpha',track='speed',rung_id='A-1',value=140,status='kept',gate='pass')
  with self.assertRaises(ValidationError):upsert_rung(self.root,model='alpha',track='speed',rung_id='A-1',value=150,status='kept',gate='pass')
  with self.assertRaises(ValidationError):review_rung(self.root,model='alpha',track='speed',rung_id='A-1',review='verified',expected_revision=99)
  reviewed=review_rung(self.root,model='alpha',track='speed',rung_id='A-1',review='verified',reviewer='tester',notes='exact',expected_revision=done['revision'])
  self.assertEqual(reviewed['ended_at'],done['ended_at']);self.assertEqual(reviewed['duration_s'],done['duration_s'])
 def test_claims_are_unique_and_archive_is_immutable(self):
  claims=[claim_rung(self.root,model='alpha',track='speed',prefix='W')['id'] for _ in range(3)]
  self.assertEqual(claims,['W-001','W-002','W-003'])
  manifest=archive_campaign(self.root,model='alpha',campaign='wave-1')
  self.assertEqual(manifest['campaign_id'],'wave-1')
  with self.assertRaises(ValidationError):archive_campaign(self.root,model='alpha',campaign='wave-1')
  with self.assertRaises(ValidationError):upsert_rung(self.root,model='alpha',campaign='wave-1',track='speed',rung_id='NO',value=1,status='testing')
 def test_history_filter_delta_and_formula_safe_exports(self):
  upsert_rung(self.root,model='alpha',track='speed',rung_id='SAFE',value=0,status='testing',summary='=2+2')
  upsert_rung(self.root,model='alpha',track='speed',rung_id='SAFE',value=140,status='kept',gate='pass')
  archive_campaign(self.root,model='alpha',campaign='old')
  data=history_payload(self.root,{'model':'alpha'});self.assertEqual(data['total'],2)
  kept=next(r for r in data['rows'] if r['status']=='kept');self.assertEqual(kept['delta_abs'],40);self.assertEqual(kept['delta_pct'],40)
  text,_=export_history(self.root,'csv',{'model':'alpha'});self.assertIn("'=2+2",text)
  body=list(csv.DictReader(io.StringIO(text.split('\n',1)[1])));self.assertEqual(len(body),2)
 def test_http_workspace_history_export_and_security(self):
  upsert_rung(self.root,model='alpha',track='speed',rung_id='WEB',value=0,status='testing')
  server=make_server(self.root,'127.0.0.1',0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  base=f'http://127.0.0.1:{server.server_address[1]}'
  try:
   for route in ['/api/workspace','/api/models/alpha/ladder.json','/api/models/alpha/campaigns','/api/history?model=alpha','/api/export?format=csv']:
    with urllib.request.urlopen(base+route,timeout=5) as response:
     self.assertEqual(response.status,200);self.assertIn("default-src 'self'",response.headers['Content-Security-Policy']);self.assertIsNone(response.headers['Access-Control-Allow-Origin']);response.read()
   with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(base+'/api/models/%2e%2e/ladder.json')
   self.assertEqual(caught.exception.code,404)
   with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(base+'/api/history?unknown=x')
   self.assertEqual(caught.exception.code,400)
  finally:server.shutdown();server.server_close();thread.join()
class CompatibilityTests(unittest.TestCase):
 def test_v1_field_aliases_and_initialize_race(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);root.joinpath('ladder.json').write_text(json.dumps({'model':'Legacy','hardware':'CPU','updated_at':'2026-01-01T00:00:00Z','tracks':{'speed':{'label':'Speed','baseline_tps':10,'rungs':[{'rung':'S0','metric_tps':12,'notes':'baseline alias','status':'kept','updated_at':'2026-01-01T00:00:00Z','duration_s':None}]}}}))
   board=load_board(root);r=board['tracks']['speed']['rungs'][0];self.assertEqual((r['id'],r['value'],r['summary']),('S0',12,'baseline alias'));self.assertEqual(board['campaign_id'],'legacy')
  with tempfile.TemporaryDirectory() as d:
   errors=[]
   def init():
    try:initialize(d,'Race','test',[TRACK])
    except ValidationError as exc:errors.append(str(exc))
   threads=[threading.Thread(target=init) for _ in range(2)];[t.start() for t in threads];[t.join() for t in threads]
   self.assertEqual(len(errors),1);self.assertEqual(load_board(d)['title'],'Race')
 def test_workspace_manifest_precedes_preserved_legacy_feed(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);initialize(root,'Legacy','compatibility',[TRACK]);make(root);make(root,'beta')
   self.assertEqual([m['id'] for m in list_models(root)],['alpha','beta'])
   self.assertEqual(load_board(root)['title'],'Legacy')
if __name__=='__main__':unittest.main()
