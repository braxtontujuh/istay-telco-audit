import 'fake-indexeddb/auto';
import { deleteDB } from 'idb';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { setSession, setWorkspaceOwner } from './api';
import { offline, type InspectionPayload } from './offline-store';
import { abortSync, syncOutbox } from './sync';
import type { Audit, Target } from './ui';

const audit:Audit={id:1,title:'Test',status:'ACTIVE',created_at:'2026-11-11T00:00:00Z',activated_at:null,closed_at:null,closure_note:null,config_snapshot:{}};
const target:Target={id:1,audit_id:1,location_id:1,telco_id:1,snapshot:{room:'Room'},assigned_to_me:true,assigned_user_ids:[1]};
function item():InspectionPayload{return{client_id:crypto.randomUUID(),target_id:1,outcome:'NO_INTERNET',network_type:'4G',mobile_data_confirmed:true,device_label:'Test device',remarks:'No usable internet',observed_at:'2026-11-11T00:00:00Z',measurement:null};}
function me(id=1){return Response.json({user:{id,username:'test.user',full_name:'Test',role:'AUDITOR'},csrf_token:'memory-only-csrf'});}
beforeEach(async()=>{setWorkspaceOwner(1);await offline.cacheAudit(1,audit,[target]);});
afterEach(async()=>{abortSync();setWorkspaceOwner(null);setSession(null);vi.restoreAllMocks();await offline.close();await deleteDB('istay-audit-v1');});

it('processes independent per-record ACKs without marking conflicts synced',async()=>{
  const first=await offline.save(1,item()),second=await offline.save(1,item());
  vi.spyOn(globalThis,'fetch').mockImplementation(async(input,options)=>{
    if(String(input).endsWith('/auth/me'))return me();
    expect((options?.headers as Record<string,string>)['X-Workspace-User']).toBe('1');
    return Response.json({results:[{client_id:first.clientId,status:'SYNCED',server_id:9},{client_id:second.clientId,status:'CONFLICT',error:{code:'AUDIT_CLOSED',message:'Audit closed'}}]});
  });
  await syncOutbox(1,true);const values=await offline.outbox(1);
  expect(values.find(x=>x.clientId===first.clientId)?.syncStatus).toBe('SYNCED');expect(values.find(x=>x.clientId===second.clientId)?.syncStatus).toBe('CONFLICT');
});
it('keeps the original UUID/payload on network failure and retries without duplication',async()=>{
  const draft=await offline.save(1,item());let fail=true;
  vi.spyOn(globalThis,'fetch').mockImplementation(async(input,options)=>{
    if(String(input).endsWith('/auth/me'))return me();
    const sent=JSON.parse(String(options?.body)).records[0];expect(sent.client_id).toBe(draft.clientId);
    if(fail)throw new TypeError('Connection lost after server may have committed');
    return Response.json({results:[{client_id:draft.clientId,status:'SYNCED',server_id:12}]});
  });
  await syncOutbox(1,true);expect((await offline.outbox(1))[0].syncStatus).toBe('RETRY');
  fail=false;await syncOutbox(1,true);const saved=(await offline.outbox(1))[0];expect(saved.syncStatus).toBe('SYNCED');expect(saved.payloadJson).toBe(draft.payloadJson);
});
it('does not send an old workspace outbox under another account',async()=>{
  await offline.save(1,item());const fetch=vi.spyOn(globalThis,'fetch').mockResolvedValue(me(2));
  await syncOutbox(1,true);expect(fetch).toHaveBeenCalledTimes(1);expect((await offline.outbox(1))[0].syncStatus).toBe('PENDING');expect(await offline.outbox(2)).toEqual([]);
});
it('does not consume ACKs after the workspace changes during an in-flight request',async()=>{
  const draft=await offline.save(1,item());vi.spyOn(globalThis,'fetch').mockImplementation(async input=>{
    if(String(input).endsWith('/auth/me'))return me();setWorkspaceOwner(2);return Response.json({results:[{client_id:draft.clientId,status:'SYNCED',server_id:15}]});
  });
  await syncOutbox(1,true);expect((await offline.outbox(1))[0].syncStatus).toBe('RETRY');expect(await offline.outbox(2)).toEqual([]);
});
it('never treats a missing server record ID as acknowledged',async()=>{
  const draft=await offline.save(1,item());vi.spyOn(globalThis,'fetch').mockImplementation(async input=>String(input).endsWith('/auth/me')?me():Response.json({results:[{client_id:draft.clientId,status:'SYNCED'}]}));
  await syncOutbox(1,true);expect((await offline.outbox(1))[0].syncStatus).toBe('RETRY');
});
