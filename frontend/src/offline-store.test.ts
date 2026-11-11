import 'fake-indexeddb/auto';
import { deleteDB } from 'idb';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { OfflineStore, type InspectionPayload } from './offline-store';
import type { Audit, Target } from './ui';
import { recoverInterrupted } from './attempts';

const audit:Audit={id:1,title:'Test audit',status:'ACTIVE',created_at:'2026-11-11T00:00:00Z',activated_at:'2026-11-11T00:00:00Z',closed_at:null,closure_note:null,config_snapshot:{site_ids:[1]}};
function target(owner:number):Target{return{id:1,audit_id:1,location_id:1,telco_id:1,snapshot:{room:'Bedroom 1',telco:'Test carrier'},assigned_to_me:true,assigned_user_ids:[owner]};}
function payload():InspectionPayload{return{client_id:crypto.randomUUID(),target_id:1,outcome:'NO_SIGNAL',network_type:'UNKNOWN',mobile_data_confirmed:true,device_label:'Test device',observed_at:'2026-11-11T00:00:00Z',remarks:'No service',measurement:null};}
let store:OfflineStore,name:string;
beforeEach(()=>{name='offline-test-'+crypto.randomUUID();store=new OfflineStore(name);});
afterEach(async()=>{await store.close();await deleteDB(name);});

describe('user-scoped offline transactions',()=>{
  it('remembers known closure/revocation without deleting earlier offline drafts',async()=>{
    await store.cacheAudit(1,audit,[target(1)]);const draft=await store.save(1,payload());
    await store.refreshKnownAudits(1,[{...audit,status:'CLOSED'}]);
    await expect(store.save(1,payload())).rejects.toThrow('active cached');
    await store.refreshKnownAudits(1,[audit]);await store.refreshKnownTargets(1,1,[]);
    await expect(store.save(1,payload())).rejects.toThrow('Download');
    expect((await store.audit(1,1))?.accessRevoked).toBe(true);
    expect((await store.outbox(1))[0].clientId).toBe(draft.clientId);
    await store.refreshKnownAudits(1,[],true);expect((await store.audit(1,1))?.accessRevoked).toBe(true);
  });
  it('persists a running speed attempt, prevents duplicates/cleanup and recovers an interruption exactly once',async()=>{
    await store.cacheAudit(1,audit,[target(1)]);const {outcome:_,measurement:__,...base}=payload();
    const attempt=await store.beginSpeedAttempt(1,base,10);
    await expect(store.beginSpeedAttempt(1,{...base,client_id:crypto.randomUUID()},10)).rejects.toThrow('running test');
    await expect(store.clearOwner(1)).rejects.toThrow('pending');expect(await store.speedAttempts(2)).toEqual([]);
    await recoverInterrupted(1,store,attempt.expiresAt-1);expect(await store.outbox(1)).toEqual([]);
    await recoverInterrupted(1,store,attempt.expiresAt+1);await recoverInterrupted(1,store,attempt.expiresAt+2);
    const records=await store.outbox(1);expect(records).toHaveLength(1);expect(records[0].clientId).toBe(base.client_id);
    expect(JSON.parse(records[0].payloadJson)).toMatchObject({outcome:'SPEEDTEST_FAILED',measurement:null});expect(await store.speedAttempts(1)).toEqual([]);
  });
  it('retains a finished speed attempt after later closure and rejects mismatched target metadata',async()=>{
    await store.cacheAudit(1,audit,[target(1)]);const {outcome:_,measurement:__,...base}=payload();
    const attempt=await store.beginSpeedAttempt(1,base,10);await store.refreshKnownAudits(1,[{...audit,status:'CLOSED'}]);
    await expect(store.finishSpeedAttempt(1,attempt,{...base,target_id:999,outcome:'SPEEDTEST_FAILED',measurement:null})).rejects.toThrow('mismatched');
    await store.finishSpeedAttempt(1,attempt,{...base,outcome:'SPEEDTEST_FAILED',measurement:null});
    await store.finishSpeedAttempt(1,attempt,{...base,outcome:'NO_SIGNAL',measurement:null});
    expect(JSON.parse((await store.outbox(1))[0].payloadJson).outcome).toBe('SPEEDTEST_FAILED');
  });
  it('persists before returning and never exposes another owner’s cache/outbox',async()=>{
    await store.cacheAudit(1,audit,[target(1)]);const original=payload();const item=await store.save(1,original);
    expect(item.syncStatus).toBe('PENDING');expect(JSON.parse((await store.outbox(1))[0].payloadJson)).toEqual(original);
    expect(await store.target(2,1)).toBeUndefined();expect(await store.outbox(2)).toEqual([]);expect(await store.audits(2)).toEqual([]);
    await expect(store.save(2,payload())).rejects.toThrow('Download');expect(await store.outbox(2)).toEqual([]);
  });
  it('requires an authorized cached target and rejects overwriting a UUID',async()=>{
    await expect(store.save(1,payload())).rejects.toThrow('Download');await store.cacheAudit(1,audit,[target(1)]);
    const original=payload();await store.save(1,original);await expect(store.save(1,{...original,remarks:'changed'})).rejects.toThrow('UUID');
    expect((await store.outbox(1))[0].payloadJson).toBe(JSON.stringify(original));
  });
  it('claims at most 20 records atomically across concurrent sync attempts',async()=>{
    await store.cacheAudit(1,audit,[target(1)]);for(let n=0;n<25;n++)await store.save(1,payload());
    const [first,second]=await Promise.all([store.claim(1),store.claim(1)]);
    expect(first.length).toBe(20);expect(second.length).toBe(5);expect(new Set([...first,...second].map(value=>value.clientId)).size).toBe(25);
  });
  it('retains the identical payload across timeout/retry/conflict and requires an ACK',async()=>{
    await store.cacheAudit(1,audit,[target(1)]);const original=await store.save(1,payload());await store.claim(1);
    await store.failure(1,original.clientId,'RETRY','timeout');expect((await store.outbox(1))[0].payloadJson).toBe(original.payloadJson);
    expect(await store.claim(1)).toHaveLength(0);expect(await store.claim(1,true)).toHaveLength(1);
    await store.failure(1,original.clientId,'CONFLICT','Audit closed');expect(await store.claim(1,true)).toHaveLength(0);
    await store.retryConflict(1,original.clientId);expect(await store.claim(1,true)).toHaveLength(1);
    await expect(store.acknowledge(1,original.clientId,0)).rejects.toThrow('acknowledgment');
    await store.acknowledge(1,original.clientId,42);await store.failure(1,original.clientId,'RETRY','late timeout');
    const saved=(await store.outbox(1))[0];expect(saved.syncStatus).toBe('SYNCED');expect(saved.serverId).toBe(42);expect(saved.payloadJson).toBe(original.payloadJson);
  });
  it('recovers a syncing record after interruption using the same UUID',async()=>{
    await store.cacheAudit(1,audit,[target(1)]);const item=await store.save(1,payload());await store.claim(1,false,1000);
    expect(await store.claim(1,true,2000)).toHaveLength(0);const retry=await store.claim(1,true,121001);
    expect(retry[0].clientId).toBe(item.clientId);expect(retry[0].payloadJson).toBe(item.payloadJson);
  });
  it('blocks cleanup of unsynced data and clears only the acknowledged owner',async()=>{
    await store.cacheAudit(1,audit,[target(1)]);await store.cacheAudit(2,audit,[target(2)]);
    const one=await store.save(1,payload());await store.save(2,payload());await expect(store.clearOwner(1)).rejects.toThrow('pending');
    await store.acknowledge(1,one.clientId,1);await store.clearOwner(1);expect(await store.outbox(1)).toEqual([]);
    expect(await store.outbox(2)).toHaveLength(1);expect(await store.targets(2,1)).toHaveLength(1);
  });
});
