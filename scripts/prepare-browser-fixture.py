"""Create disposable local browser acceptance accounts/data; never use employee databases."""
import json
import secrets
import subprocess
from pathlib import Path
from uuid import uuid4

import httpx

root=Path(__file__).resolve().parents[1]
docker=r'C:\Users\braxt\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe'
compose=[docker,'compose','-p','istay-browser-test','--env-file','.env.browser-test','-f','compose.dev.yml','-f','compose.browser-test.yml']
file=root/'.tools/browser-fixture.json'
if file.exists():
    raise SystemExit('Browser fixture credentials already exist; refusing to overwrite an active test fixture')
suffix=uuid4().hex[:8]
admin={'username':'browser_admin_'+suffix,'password':secrets.token_urlsafe(24)}
auditor={'username':'browser_auditor_'+suffix,'password':secrets.token_urlsafe(24)}
bootstrap='''
import json,sys
from sqlalchemy.orm import Session
from app.config import settings
from app.db import engine
from app.models import User
from app.security import hasher
assert settings().environment=='development' and settings().postgres_db=='istay_browser_test'
data=json.load(sys.stdin)
with Session(engine()) as db:
 db.add(User(username=data['username'],full_name='Browser Test Admin',role='ADMIN',password_hash=hasher.hash(data['password'])))
 db.commit()
'''
subprocess.run(compose+['exec','-T','api','python','-m','app.cli','seed'],cwd=root,check=True,capture_output=True)
subprocess.run(compose+['exec','-T','api','python','-c',bootstrap],cwd=root,check=True,text=True,input=json.dumps(admin),capture_output=True)
origin='http://localhost:8082'
with httpx.Client(base_url=origin,trust_env=False,timeout=15) as client:
    response=client.post('/api/v1/auth/login',json=admin,headers={'Origin':origin});response.raise_for_status()
    session=response.json();headers={'Origin':origin,'X-CSRF-Token':session['csrf_token'],'X-Workspace-User':str(session['user']['id'])}
    def post(path,payload):
        response=client.post('/api/v1'+path,json=payload,headers=headers);response.raise_for_status();return response.json()
    site=client.get('/api/v1/sites').json()[0]
    block=post('/blocks',{'site_id':site['id'],'code':'TEST-'+suffix})
    floor=post('/floors',{'block_id':block['id'],'floor_no':1})
    unit=post('/units',{'floor_id':floor['id'],'unit_no':'TEST-101','locations':[
        {'code':'L','name':'Living room','sort_order':0},{'code':'B1','name':'Bedroom 1','sort_order':1},{'code':'B2','name':'Bedroom 2','sort_order':2}]})
    employee=post('/users',auditor|{'full_name':'Browser Test Auditor','role':'AUDITOR','site_ids':[site['id']]})
    telco=client.get('/api/v1/telcos').json()[0]
    audit=post('/audits',{'title':'Offline browser acceptance '+suffix,'site_ids':[site['id']]})
    targets=post(f"/audits/{audit['id']}/targets",{'unit_ids':[unit['id']],'telco_ids':[telco['id']]})
    post(f"/audits/{audit['id']}/assignments",{'user_id':employee['id'],'target_ids':[value['id'] for value in targets]})
    post(f"/audits/{audit['id']}/activate",None)
    client.post('/api/v1/auth/logout',headers=headers).raise_for_status()
file.write_text(json.dumps({'origin':origin,'admin':admin,'auditor':auditor,'owner_id':employee['id'],'audit_id':audit['id'],
                           'target_ids':[value['id'] for value in targets]},indent=2),encoding='utf-8')
print('Prepared isolated browser fixture. Credentials stored only in ignored .tools/browser-fixture.json; not printed.')
