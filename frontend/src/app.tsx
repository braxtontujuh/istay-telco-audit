import { useEffect, useState } from 'react';
import { Link, Navigate, NavLink, Route, Routes } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useRegisterSW } from 'virtual:pwa-register/react';
import { api, sessionSchema, setSession, setWorkspaceOwner, type Session } from './api';
import { AuditEditor, AuditList, MobileAudit, TargetDetails } from './audit-pages';
import { SitesPage, UnitsPage, TemplatesPage, TelcosPage, UsersPage } from './configuration';
import { activeOwner, activateOwner, lockWorkspace, offline, type Identity } from './offline-store';
import { useLocal, useSyncLifecycle } from './offline-hooks';
import { SyncPage } from './offline-pages';
import { abortSync } from './sync';
import { ErrorMessage } from './ui';
import { Dashboard, ReportsPage } from './reports';

export default function App(){
  const client=useQueryClient(),[identity,updateIdentity]=useState<Identity|null>(null),[live,setLive]=useState(false),[loginMode,setLoginMode]=useState(false);
  const [checking,setChecking]=useState(true),[error,setError]=useState(''),[pending,setPending]=useState(false);
  const {needRefresh:[needRefresh],updateServiceWorker}=useRegisterSW();
  async function authenticated(session:Session,personal:boolean){
    abortSync();await client.cancelQueries();client.clear();setWorkspaceOwner(session.user.id);setSession(session);
    activateOwner(session.user.id,personal);updateIdentity(session.user);setLive(true);setLoginMode(false);
    try{await offline.remember(session.user);}catch{setError('Signed in online, but device storage is unavailable. Offline work is not ready.');}
  }
  useEffect(()=>{
    let stopped=false;const request=new AbortController(),timeout=setTimeout(()=>request.abort(),5000);
    async function restore(){
      if(localStorage.getItem('istay-workspace-locked')==='true'){setChecking(false);return;}
      const owner=activeOwner();setWorkspaceOwner(owner);
      try{const session=sessionSchema.parse(await api('/auth/me',{signal:request.signal}));if(!stopped)await authenticated(session,localStorage.getItem('istay-active-owner')===String(session.user.id));}
      catch{if(owner){const cached=await offline.metadata<Identity>(owner,'identity').catch(()=>undefined);if(cached&&!stopped){setSession(null);setWorkspaceOwner(owner);updateIdentity(cached);setLive(false);}}}
      finally{clearTimeout(timeout);if(!stopped)setChecking(false);}
    }
    void restore();return()=>{stopped=true;clearTimeout(timeout);request.abort();};
  },[]);
  useEffect(()=>{
    function ready(event:Event){const user=(event as CustomEvent<Identity>).detail;if(user?.id===identity?.id){updateIdentity(user);setLive(true);}}
    function unavailable(event:Event){if((event as CustomEvent<{owner:number}>).detail.owner===identity?.id)setLive(false);}
    window.addEventListener('istay-session-ready',ready);window.addEventListener('istay-session-unavailable',unavailable);
    return()=>{window.removeEventListener('istay-session-ready',ready);window.removeEventListener('istay-session-unavailable',unavailable);};
  },[identity?.id]);
  async function login(event:React.FormEvent<HTMLFormElement>){
    event.preventDefault();setPending(true);setError('');abortSync();const data=new FormData(event.currentTarget);
    try{const parsed=sessionSchema.parse(await api('/auth/login',{method:'POST',body:JSON.stringify({username:data.get('username'),password:data.get('password')})}));
      await authenticated(parsed,data.get('personal')==='on');
    }catch(err){setError(err instanceof Error?err.message:'Unable to sign in');}finally{setPending(false);}
  }
  async function logout(){
    if(!identity)return;setPending(true);setError('');
    try{
      if((await offline.outbox(identity.id)).some(item=>item.syncStatus!=='SYNCED')||(await offline.speedAttempts(identity.id)).length)throw new Error('Unsynced records or a running speed test remain. Finish/cancel the test and sync or resolve records before signing out. You can lock this workspace without deleting drafts.');
      abortSync();await api('/auth/logout',{method:'POST'});setSession(null);setLive(false);await offline.clearOwner(identity.id);
      lockWorkspace();await client.cancelQueries();client.clear();setWorkspaceOwner(null);updateIdentity(null);
    }catch(err){setError(err instanceof Error?err.message:'Could not complete server sign-out. Local drafts were retained.');}finally{setPending(false);}
  }
  async function lock(){abortSync();setSession(null);setWorkspaceOwner(null);lockWorkspace();await client.cancelQueries();client.clear();setLive(false);updateIdentity(null);setLoginMode(false);setError('Workspace locked locally. Drafts were retained; reconnect and sign in as their owner to resume.');}
  function signIn(){abortSync();setLoginMode(true);setLive(false);setError('');}
  return <><div className="topbar"><header><Link className="brand" to="/app"><img src="/icon.svg" alt="" width="40" height="40"/><span><small>I-STAY OPERATIONS</small><strong>Telco Audit</strong></span></Link>
    {identity&&<div className="account"><span>{identity.full_name}<small>{identity.role}</small></span><button className="secondary" disabled={pending} onClick={logout}>Sign out</button><button className="secondary" onClick={lock}>Lock</button></div>}</header></div>
    <main><ErrorMessage error={error}/>{checking?<p role="status">Opening your workspace…</p>:!identity||loginMode?<div className="login-layout"><div><small>MOBILE DATA INSPECTION</small><h1>Every room.<br/>A clearer connection.</h1><p>Inspect mobile SIM-based internet performance and keep no-service records on your device until the server confirms synchronization.</p><p className="muted">Shared devices should be used online only. Never share an employee account.</p></div>
      <section><h2>Employee sign in</h2><form onSubmit={login}><label>Username<input name="username" autoComplete="username" required minLength={3} maxLength={80}/></label><label>Password<input name="password" type="password" autoComplete="current-password" required maxLength={256}/></label>
        <label className="check"><input name="personal" type="checkbox"/>Personal device: keep my downloaded workspace available after closing the app.</label><button disabled={pending}>{pending?'Signing in…':'Sign in'}</button></form>
        {identity&&<button className="secondary" onClick={()=>setLoginMode(false)}>Return to local workspace</button>}<p className="muted">Passwords and session secrets are never saved in the offline database.</p></section></div>:
      <Workspace key={identity.id} identity={identity} live={live} signIn={signIn} needRefresh={needRefresh} update={async()=>{
        if((await offline.outbox(identity.id)).some(value=>value.syncStatus!=='SYNCED')||(await offline.speedAttempts(identity.id)).length){setError('Finish/cancel speed tests and sync or resolve pending records before updating the app.');return;}
        await updateServiceWorker(true);
      }}/>}<footer>Mobile SIM-based internet performance · Staff-confirmed SIM and network details</footer></main></>;
}

function Workspace({identity,live,signIn,needRefresh,update}:{identity:Identity;live:boolean;signIn:()=>void;needRefresh:boolean;update:()=>Promise<void>}){
  const local=useLocal(identity.id),manage=live&&identity.role!=='AUDITOR',admin=live&&identity.role==='ADMIN';useSyncLifecycle(identity.id);
  return <><nav className="workspace-nav" aria-label="Main navigation"><NavLink to="/app" end>My audits</NavLink><NavLink to="/app/sync">Device sync ({local.pending})</NavLink><NavLink to="/app/history">My server history</NavLink>
    {manage&&<><NavLink to="/admin" end>Overview</NavLink><NavLink to="/admin/audits">Audit management</NavLink><NavLink to="/admin/reports">Reports</NavLink></>}{admin&&<><NavLink to="/admin/sites">Sites</NavLink><NavLink to="/admin/units">Units & rooms</NavLink><NavLink to="/admin/room-templates">Templates</NavLink><NavLink to="/admin/telcos">Telcos</NavLink><NavLink to="/admin/users">Employees</NavLink></>}</nav>
    {!live&&<div className="notice"><strong>Local drafts only — server sign-in is required for synchronization.</strong><p>Previously downloaded assignments can be recorded locally. The server will verify permissions and audit status when you reconnect.</p><button onClick={signIn}>Sign in to sync</button></div>}
    <div className="device-status"><span>{local.pending} records awaiting server acknowledgment</span><Link to="/app/sync">Review device queue →</Link></div>
    {needRefresh&&<aside>A new app version is ready. <button onClick={update}>Update after sync</button></aside>}
    <Routes><Route path="/app" element={<AuditList/>}/><Route path="/app/audits/:id" element={<MobileAudit/>}/><Route path="/app/audits/:id/units" element={<MobileAudit/>}/><Route path="/app/targets/:id" element={<TargetDetails/>}/><Route path="/app/sync" element={<SyncPage identity={identity}/>}/><Route path="/app/history" element={<ServerHistory/>}/>
      {manage&&<><Route path="/admin" element={<Dashboard/>}/><Route path="/admin/audits" element={<AuditList manage/>}/><Route path="/admin/audits/:id" element={<AuditEditor/>}/><Route path="/admin/reports" element={<ReportsPage/>}/><Route path="/admin/coverage" element={<ReportsPage/>}/></>}
      {admin&&<><Route path="/admin/sites" element={<SitesPage/>}/><Route path="/admin/units" element={<UnitsPage/>}/><Route path="/admin/room-templates" element={<TemplatesPage/>}/><Route path="/admin/telcos" element={<TelcosPage/>}/><Route path="/admin/users" element={<UsersPage/>}/></>}
      <Route path="*" element={<Navigate to="/app" replace/>}/></Routes></>;
}

import { State, useApi } from './ui';
function ServerHistory(){
  const records=useApi<{id:number;target_id:number;outcome:string;observed_at:string;received_at:string;remarks:string;clock_skew_flag:boolean}[]>('/inspections/mine');
  return <><h2>My accepted server history</h2><p>Latest 500 accepted records currently accessible to your account. For device-only drafts, use Device sync.</p><State pending={records.isPending} error={records.error}/>{records.data?.map(value=><section key={value.id}><Link to={`/app/targets/${value.target_id}`}>Target {value.target_id}</Link><h3>{value.outcome.replaceAll('_',' ')}</h3><p>{value.remarks}</p><p className="muted">Observed: {new Date(value.observed_at).toLocaleString()} · Server received: {new Date(value.received_at).toLocaleString()}</p>{value.clock_skew_flag&&<p className="notice">The device clock differs substantially from the server. Review the observation time.</p>}</section>)}</>;
}
