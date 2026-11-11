import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { api, getWorkspaceOwner, sessionSchema } from './api';
import { useLocal } from './offline-hooks';
import { activateOwner, offline, shellReady, type Identity, type InspectionPayload, type Outbox, type SpeedAttempt } from './offline-store';
import { cloudflareTest, type Progress, type Measurement } from './speedtest';
import { syncOutbox } from './sync';
import { Badge, ErrorMessage, useApi, type Audit, type Target } from './ui';

export const storageWarning='Clearing browser/site storage or uninstalling this app may destroy unsynced records. Offline data is not automatically encrypted; protect your phone and use shared devices online only.';
export function localPayload(item:Outbox):InspectionPayload|undefined{try{return JSON.parse(item.payloadJson);}catch{return undefined;}}

export function OfflinePreparation({auditId,owner}:{auditId:number;owner:number}){
  const local=useLocal(owner),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [personal,setPersonal]=useState(localStorage.getItem('istay-active-owner')===String(owner));
  const cached=local.audits.find(value=>value.audit.id===auditId),ready=!!cached&&!cached.accessRevoked&&['ACTIVE','COMPLETED'].includes(cached.audit.status)&&local.shell;
  async function download(){
    setBusy(true);setError('');
    try{
      const me=sessionSchema.parse(await api('/auth/me'));
      if(me.user.id!==owner||getWorkspaceOwner()!==owner)throw new Error('Account changed; sign in again before downloading.');
      const [audit,targets]=await Promise.all([api(`/audits/${auditId}`),api(`/audits/${auditId}/targets`)]);
      if(getWorkspaceOwner()!==owner)throw new Error('Account changed during download.');
      await offline.remember(me.user);await offline.cacheAudit(owner,audit as Audit,targets as Target[]);
      activateOwner(owner,personal);
      await offline.setMetadata(owner,'personal_device',personal);
      if(!await shellReady())setError('Assignments are saved on this device. The app shell is not cached yet: stay online and reload the installed/production app before relying on offline relaunch.');
    }catch(err){setError(err instanceof Error?err.message:'Unable to prepare offline assignments');}finally{setBusy(false);}
  }
  return <section><div className="page-title"><h3>Prepare for offline work</h3><Badge>{ready?'Offline Ready':cached?'Assignments cached':'Not prepared'}</Badge></div>
    <p>{cached?`Assignments downloaded ${new Date(cached.downloadedAt).toLocaleString()}`:'Download your assigned rooms while online before entering a no-service area.'}</p>
    <label className="check"><input type="checkbox" checked={personal} onChange={e=>setPersonal(e.target.checked)}/>This is my personal phone. Keep my offline workspace available after closing the app.</label>
    <p className="muted">On a shared device, leave this off and sign out when finished. {storageWarning}</p><button disabled={busy} onClick={download}>{busy?'Preparing…':'Download / refresh my assignments'}</button>
    <ErrorMessage error={error}/></section>;
}

export function SyncPage({identity}:{identity:Identity}){
  const owner=identity.id,local=useLocal(owner),[busy,setBusy]=useState(false),[error,setError]=useState(''),queryClient=useQueryClient();
  async function sync(){setBusy(true);try{await syncOutbox(owner,true);await queryClient.invalidateQueries();}finally{setBusy(false);}}
  return <><div className="page-title"><h2>Device records & sync</h2><Badge>{local.pending} pending</Badge></div>
    <div className="notice"><strong>Saved on device and saved on server are separate states.</strong><p>{storageWarning}</p></div>
    <div className="toolbar"><button disabled={busy} onClick={sync}>{busy?'Checking server…':'Sync now'}</button>
      <button className="secondary" disabled={busy||local.pending>0} onClick={async()=>{try{await offline.clearOwner(owner);await offline.remember(identity);}catch(err){setError(String(err));}}}>Clear synced records & downloaded assignments</button>
      <button className="secondary" onClick={async()=>{const granted=await navigator.storage?.persist?.();setError(granted?'Browser granted persistent storage. Clearing storage can still erase records.':'Persistent storage was not granted. Keep unsynced records backed by a completed server sync.');}}>Request persistent device storage</button></div>
    <p role="status">{local.message}</p><ErrorMessage error={error}/>
    {local.items.length===0&&<section><p>No inspection records are stored for your account on this device.</p></section>}
    {[...local.items].reverse().map(item=>{const payload=localPayload(item);return <section key={item.clientId}><div className="page-title"><h3>{String(item.targetSnapshot.unit??'')} · {String(item.targetSnapshot.room??'Room')}</h3><Badge>{item.syncStatus}</Badge></div>
      <p>{String(item.targetSnapshot.telco??'')} · {payload?.outcome.replaceAll('_',' ')??'Unreadable local record'} · {payload?.network_type}</p>
      <p>{payload?.remarks}</p><p className="muted">Saved on device {new Date(item.savedAt).toLocaleString()}{item.serverId?` · Server record ${item.serverId}`:''}</p>
      {item.error&&<p role="alert">{item.error}</p>}{item.syncStatus==='CONFLICT'&&<><p>Ask a manager to review audit closure, assignment and site access. This record’s original payload is retained.</p><button disabled={busy} onClick={async()=>{await offline.retryConflict(owner,item.clientId);await sync();}}>Retry after manager resolution</button></>}
      <details><summary>Record reference for support</summary><code>{item.clientId}</code></details></section>;})}
  </>;
}

export function Capture({target,owner}:{target:Target;owner:number}){
  const local=useLocal(owner),cached=local.audits.find(value=>value.audit.id===target.audit_id);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[saved,setSaved]=useState<string|null>(null),[sequence,setSequence]=useState(0);
  const [outcome,setOutcome]=useState<'NO_SIGNAL'|'NO_INTERNET'|'SKIPPED'>('NO_SIGNAL');
  const targets=useApi<Target[]>(`/audits/${target.audit_id}/targets`),assigned=targets.data?.filter(value=>value.assigned_to_me)??[];
  const position=assigned.findIndex(value=>value.id===target.id),next=assigned[position+1];
  const item=local.items.find(value=>value.clientId===saved);
  const liveAudit=useApi<Audit>(`/audits/${target.audit_id}`);
  const eligible=!!cached&&!cached.accessRevoked&&['ACTIVE','COMPLETED'].includes(liveAudit.data?.status??cached.audit.status)&&target.assigned_to_me;
  const form=useRef<HTMLFormElement>(null),running=useRef(false),alive=useRef(true),cancel=useRef<(()=>void)|null>(null);
  const [testing,setTesting]=useState(false),[progress,setProgress]=useState<Progress>({warnings:0});
  useEffect(()=>{alive.current=true;const stop=()=>cancel.current?.();window.addEventListener('pagehide',stop);return()=>{alive.current=false;stop();window.removeEventListener('pagehide',stop);};},[owner,target.id]);
  function basePayload(data:FormData):SpeedAttempt['base']{
    if(getWorkspaceOwner()!==owner)throw new Error('Account changed. Save again in the correct workspace.');
    return{client_id:crypto.randomUUID(),target_id:target.id,network_type:String(data.get('network_type')) as InspectionPayload['network_type'],
      mobile_data_confirmed:data.get('confirmed')==='on',device_label:String(data.get('device_label')??''),remarks:String(data.get('remarks')??''),observed_at:new Date().toISOString()};
  }
  async function startSpeed(){
    if(running.current||saved||busy||!eligible||!form.current)return;
    const data=new FormData(form.current);setError('');
    if(data.get('confirmed')!=='on'||data.get('data_consent')!=='on'){setError('Confirm the mobile-data SIM/Wi-Fi settings and accept test data usage before starting.');return;}
    running.current=true;setTesting(true);setProgress({warnings:0});let attempt:SpeedAttempt|undefined,interrupted=false;
    cancel.current=()=>{interrupted=true;};
    try{
      const timeout=Number(cached?.audit.config_snapshot.timeout_seconds??60);
      attempt=await offline.beginSpeedAttempt(owner,basePayload(data),timeout);
      let measurement:Measurement|null=null,failure='';
      try{
        const runner=await cloudflareTest(timeout,value=>{if(alive.current)setProgress(value);});
        cancel.current=()=>{interrupted=true;runner.cancel();};
        if(interrupted||!alive.current||getWorkspaceOwner()!==owner)runner.cancel('Page or account changed during the test.');
        measurement=await runner.promise;
      }catch(err){failure=err instanceof Error?err.message:'Speed test could not complete.';}
      const payload:InspectionPayload={...attempt.base,outcome:measurement?'TESTED':'SPEEDTEST_FAILED',measurement,
        remarks:failure?`${failure} ${attempt.base.remarks}`.slice(0,4000):attempt.base.remarks};
      await offline.finishSpeedAttempt(owner,attempt,payload);
      if(alive.current&&getWorkspaceOwner()===owner){setSaved(payload.client_id);if(failure)setError(`${failure} The failed attempt was saved on this device.`);void syncOutbox(owner);}
    }catch(err){if(alive.current)setError(`${err instanceof Error?err.message:'Local save failed.'} No server save is claimed. If interrupted test metadata was saved, the app will recover it as a failed attempt after its timeout.`);}
    finally{running.current=false;cancel.current=null;if(alive.current)setTesting(false);}
  }
  async function save(event:React.FormEvent<HTMLFormElement>){
    event.preventDefault();if(saved||busy||running.current||!eligible)return;setBusy(true);setError('');
    const data=new FormData(event.currentTarget);
    try{
      const payload:InspectionPayload={...basePayload(data),outcome,measurement:null};
      if(!payload.mobile_data_confirmed&&outcome!=='SKIPPED')throw new Error('Confirm Wi-Fi is off and the correct mobile-data SIM is selected.');
      await offline.save(owner,payload);setSaved(payload.client_id);void syncOutbox(owner);
    }catch(err){setError(err instanceof Error?err.message:'Unable to save on this device. No server save is claimed.');}finally{setBusy(false);}
  }
  return <><OfflinePreparation auditId={target.audit_id} owner={owner}/><section><h3>Record an inspection outcome</h3>
    {!cached&&<p>Download your assignment before recording an offline outcome.</p>}
    {cached&&!eligible&&<p role="alert">This cached assignment is closed or no longer authorized for capture. Existing device records remain available in the sync queue.</p>}
    <form ref={form} key={sequence} onSubmit={save}><fieldset disabled={busy||testing||!!saved||!eligible}>
      <label>Outcome<select value={outcome} onChange={e=>setOutcome(e.target.value as typeof outcome)}><option value="NO_SIGNAL">No signal — phone shows no mobile service</option><option value="NO_INTERNET">No internet — service present but unusable internet</option><option value="SKIPPED">Skipped — room inaccessible or another reason</option></select></label>
      <label className="check"><input name="confirmed" type="checkbox" required={outcome!=='SKIPPED'}/>Wi-Fi is OFF, mobile data is enabled and the correct SIM/telco is selected.</label>
      <label>Network generation — staff selected<select name="network_type"><option value="UNKNOWN">Unknown</option><option value="4G">4G</option><option value="4G+">4G+</option><option value="5G">5G</option></select></label>
      <label>Device label<input name="device_label" maxLength={200} placeholder="e.g. Samsung Galaxy A54"/></label><label>Remarks{outcome==='SKIPPED'?' (required)':''}<textarea name="remarks" maxLength={4000} rows={3} required={outcome==='SKIPPED'}/></label>
      <button>{busy?'Saving to device…':'Save outcome on this device'}</button>
      <hr/><h4>Internet speed test · Cloudflare</h4><p>The phone connects directly to Cloudflare. Staff must select the correct SIM and turn Wi-Fi off; the browser cannot verify the carrier or radio type.</p>
      <label className="check"><input type="checkbox" name="data_consent"/>I accept mobile-data usage: the configured test requests about 34.2 MB before overhead or retries. Actual usage can vary.</label>
      <p className="muted">Audit profile: mobile-v1 · timeout {String(cached?.audit.config_snapshot.timeout_seconds??60)} seconds. Partial, canceled or interrupted tests are retained as failed attempts with no numeric success result.</p>
      <button type="button" onClick={startSpeed}>Start Speed Test</button></fieldset></form>
    {testing&&<div className="notice" role="status"><strong>Measuring — keep this page open.</strong><p>Download {progress.download_mbps?.toFixed(2)??'…'} Mbps · Upload {progress.upload_mbps?.toFixed(2)??'…'} Mbps · Ping {progress.ping_ms?.toFixed(1)??'…'} ms</p><button className="secondary" onClick={()=>cancel.current?.()}>Cancel speed test</button></div>}
    <ErrorMessage error={error}/>
    {saved&&<div className={item?.syncStatus==='SYNCED'?'success':'notice'} role="status"><strong>{item?.syncStatus==='SYNCED'?'Server acknowledged this inspection.':'Saved on device.'}</strong><p>{item?.syncStatus==='SYNCED'?`Synced as server record ${item.serverId}.`:`${item?.syncStatus??'PENDING'} — no server save is claimed until acknowledgment.`}</p>
      {item&&localPayload(item)?.measurement&&<p>Download {localPayload(item)!.measurement!.download_mbps.toFixed(2)} Mbps · Upload {localPayload(item)!.measurement!.upload_mbps.toFixed(2)} Mbps · Ping {localPayload(item)!.measurement!.ping_ms.toFixed(1)} ms</p>}
      {item?.error&&<p>{item.error}</p>}<div className="toolbar"><button className="secondary" onClick={()=>{setSaved(null);setSequence(value=>value+1);}}>Record another attempt</button>{next?<Link className="button" to={`/app/targets/${next.id}`}>Next assigned room →</Link>:<Link to={`/app/audits/${target.audit_id}`}>Back to assigned rooms</Link>}<Link to="/app/sync">View sync queue</Link></div></div>}
    <p className="muted">No signal and no internet have no numeric speed values. A failed or skipped attempt does not erase a prior conclusive result.</p></section></>;
}
