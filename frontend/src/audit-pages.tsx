import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { getWorkspaceOwner } from './api';
import { Capture, OfflinePreparation } from './offline-pages';
import { Badge, CheckList, ErrorMessage, HierarchyPicker, State, useAction, useApi,
  type Audit, type Employee, type Progress, type Site, type Target, type Telco, type Unit } from './ui';

export function text(target: Target, key: string) { return String(target.snapshot[key] ?? ''); }
function settings(data: FormData) {
  return {profile_version: 'mobile-v1', timeout_seconds: Number(data.get('timeout_seconds')),
    weak_download_mbps:Number(data.get('weak_download_mbps')),weak_upload_mbps:Number(data.get('weak_upload_mbps')),high_ping_ms:Number(data.get('high_ping_ms'))};
}
function ConfigFields({config}: {config?: Record<string, unknown>}) {
  return <fieldset><legend>Audit thresholds & test profile</legend><div className="grid3">
    <label>Weak download below (Mbps)<input name="weak_download_mbps" type="number" step="0.1" min={0} max={10000} defaultValue={Number(config?.weak_download_mbps??10)} required/></label>
    <label>Weak upload below (Mbps)<input name="weak_upload_mbps" type="number" step="0.1" min={0} max={10000} defaultValue={Number(config?.weak_upload_mbps??2)} required/></label>
    <label>High ping above (ms)<input name="high_ping_ms" type="number" step="0.1" min={0} max={100000} defaultValue={Number(config?.high_ping_ms??100)} required/></label></div>
    <label>Test timeout (seconds)<input name="timeout_seconds" type="number" min={10} max={120} defaultValue={Number(config?.timeout_seconds??60)} required/></label>
    <p className="muted">The mobile-v1 profile and these thresholds are frozen when this audit activates.</p></fieldset>;
}

export function AuditList({manage=false}: {manage?: boolean}) {
  const audits=useApi<Audit[]>('/audits'),sites=useApi<Site[]>('/sites'),action=useAction(),navigate=useNavigate();
  const [selected,setSelected]=useState<number[]>([]);
  return <><div className="page-title"><div><small>{manage?'MANAGEMENT':'FIELD WORK'}</small><h2>{manage?'Audit management':'My audits'}</h2></div><Badge>{audits.data?.length??0} audits</Badge></div>
    <State pending={audits.isPending} error={audits.error}/>
    {manage&&<details className="panel"><summary>Create an ad hoc audit</summary><form onSubmit={async e=>{e.preventDefault();const data=new FormData(e.currentTarget);
      const result=await action.run<Audit>('/audits',{title:data.get('title'),site_ids:selected,config:settings(data)});if(result)navigate(`/admin/audits/${result.id}`);}}>
      <label>Audit title<input name="title" required maxLength={200}/></label><fieldset><legend>Authorized sites</legend><CheckList items={sites.data?.filter(x=>x.active).map(x=>({id:x.id,label:x.code}))??[]} values={selected} onChange={setSelected}/></fieldset>
      <ConfigFields/><button disabled={action.pending||!selected.length}>Create draft</button><ErrorMessage error={action.error}/></form></details>}
    <div className="cards">{audits.data?.map(audit=><Link className="audit-card" key={audit.id} to={manage?`/admin/audits/${audit.id}`:`/app/audits/${audit.id}`}>
      <Badge>{audit.status}</Badge><h3>{audit.title}</h3><p>Created {new Date(audit.created_at).toLocaleDateString()}</p><span>{manage?'Configure & review':'View assigned rooms'} →</span></Link>)}</div>
    {audits.data?.length===0&&<section><h3>No audits available</h3><p>{manage?'Create a draft audit to select rooms, telcos and employees.':'Ask your manager to activate an audit and assign targets to your account.'}</p></section>}
  </>;
}

export function ProgressCards({value}: {value?: Progress}) {
  if(!value)return null;
  return <><div className="stats"><div><strong>{value.total}</strong><span>Targets</span></div><div><strong>{value.inspected}</strong><span>Inspected</span></div><div><strong>{value.pending}</strong><span>Pending</span></div><div><strong>{value.completion_percent}%</strong><span>Completion</span></div></div>
    <p className="muted">{value.tested} tested · {value.no_signal} no signal · {value.no_internet} no internet. {value.policy}</p></>;
}

export function AuditEditor() {
  const {id}=useParams(),audit=useApi<Audit>(`/audits/${id}`),targets=useApi<Target[]>(`/audits/${id}/targets`),progress=useApi<Progress>(`/audits/${id}/progress`);
  const users=useApi<Employee[]>('/users'),telcos=useApi<Telco[]>('/telcos'),action=useAction();
  const events=useApi<{id:number;action:string;created_at:string;details:Record<string,unknown>}[]>(`/audits/${id}/events`);
  const [units,setUnits]=useState<Unit[]>([]),[chosenTelcos,setChosenTelcos]=useState<number[]>([]),[employee,setEmployee]=useState(''),[chosenTargets,setChosenTargets]=useState<number[]>([]);
  const value=audit.data;
  if(!value)return <State pending={audit.isPending} error={audit.error}/>;
  const siteIds=Array.isArray(value.config_snapshot.site_ids)?value.config_snapshot.site_ids.map(Number):[];
  const canAssign=value.status!=='CLOSED';
  return <><Link to="/admin/audits">← Audit management</Link><div className="page-title"><h2>{value.title}</h2><Badge>{value.status}</Badge></div><Link to={`/admin/reports?audit=${id}`}>Coverage, results & Excel export →</Link>
    <ErrorMessage error={action.error}/><State error={targets.error||progress.error||users.error||telcos.error}/><ProgressCards value={progress.data}/>
    {value.status==='DRAFT'&&<><details className="panel"><summary>Edit draft configuration</summary><form onSubmit={e=>{e.preventDefault();const data=new FormData(e.currentTarget);void action.run(`/audits/${id}`,{title:data.get('title'),config:settings(data)},'PATCH');}}>
      <label>Title<input name="title" defaultValue={value.title} required/></label><ConfigFields config={value.config_snapshot}/><button disabled={action.pending}>Save draft</button></form></details>
      <section><h3>1. Select target units & telcos</h3><p>Add selected units from one floor at a time. Every active room becomes a separate target for each selected telco.</p>
        <HierarchyPicker siteIds={siteIds} onUnits={setUnits}/><fieldset><legend>Telcos</legend><CheckList items={telcos.data?.filter(x=>x.active).map(x=>({id:x.id,label:x.name}))??[]} values={chosenTelcos} onChange={setChosenTelcos}/></fieldset>
        <button disabled={action.pending||!units.length||!chosenTelcos.length} onClick={()=>void action.run(`/audits/${id}/targets`,{unit_ids:units.map(x=>x.id),telco_ids:chosenTelcos})}>Add targets from selected units</button></section></>}
    <section><h3>{value.status==='DRAFT'?'2. Assign targets':'Target assignments'}</h3><p>Choose an employee and the rooms assigned to them. Saving replaces that employee’s assignment for this audit.</p>
      <label>Employee<select value={employee} disabled={!canAssign} onChange={e=>{setEmployee(e.target.value);setChosenTargets(targets.data?.filter(x=>x.assigned_user_ids.includes(Number(e.target.value))).map(x=>x.id)??[]);}}><option value="">Choose employee</option>{users.data?.filter(x=>x.active).map(x=><option key={x.id} value={x.id}>{x.full_name} ({x.username})</option>)}</select></label>
      <div className="toolbar"><button className="secondary" disabled={!canAssign} onClick={()=>setChosenTargets(targets.data?.map(x=>x.id)??[])}>Select all</button><button className="secondary" disabled={!canAssign} onClick={()=>setChosenTargets([])}>Clear selection</button></div>
      <div className="target-list">{targets.data?.map(target=><label key={target.id} className="target-check"><input type="checkbox" disabled={!canAssign} checked={chosenTargets.includes(target.id)} onChange={e=>setChosenTargets(e.target.checked?[...chosenTargets,target.id]:chosenTargets.filter(x=>x!==target.id))}/>
        <span><strong>{text(target,'site')} / {text(target,'block')} / Floor {text(target,'floor')} / {text(target,'unit')}</strong><br/>{text(target,'room')} · {text(target,'telco')}<br/>
          <small>Assigned: {target.assigned_user_ids.map(uid=>users.data?.find(x=>x.id===uid)?.full_name??`User ${uid}`).join(', ')||'Nobody'}</small></span></label>)}</div>
      <button disabled={action.pending||!employee||!canAssign} onClick={()=>void action.run(`/audits/${id}/assignments`,{user_id:Number(employee),target_ids:chosenTargets})}>Save employee assignment</button>
      {!targets.data?.length&&<p>No targets selected yet.</p>}</section>
    {value.status==='DRAFT'&&<section><h3>3. Activate audit</h3><p>Every target must have an active, authorized assignee. Activation freezes the target list, room labels and configuration.</p><button disabled={action.pending} onClick={()=>void action.run(`/audits/${id}/activate`)}>Activate audit</button></section>}
    {['ACTIVE','COMPLETED','CLOSED'].includes(value.status)&&<section><h3>{value.status==='CLOSED'?'Reopen audit':'Close or reopen audit'}</h3><form onSubmit={e=>{e.preventDefault();const data=new FormData(e.currentTarget);void action.run(`/audits/${id}/${value.status==='CLOSED'?'reopen':'close'}`,{reason:data.get('reason')});}}>
      <label>Reason<textarea name="reason" rows={3} maxLength={4000} required={value.status==='CLOSED'||!!progress.data?.pending}/></label><button disabled={action.pending}>{value.status==='CLOSED'?'Reopen with recorded reason':'Close audit'}</button></form>
      {value.status==='COMPLETED'&&<p>To perform additional retests, reopen with a recorded reason.</p>}{value.closure_note&&<p>Closure note: {value.closure_note}</p>}</section>}
    {value.status==='COMPLETED'&&<section><h3>Record a manager-approved retest cycle</h3><form onSubmit={e=>{e.preventDefault();const data=new FormData(e.currentTarget);void action.run(`/audits/${id}/reopen`,{reason:data.get('reason')});}}><label>Reopen reason<input name="reason" required minLength={3}/></label><button disabled={action.pending}>Reopen audit</button></form></section>}
    <details className="panel"><summary>Audit event history</summary><State error={events.error}/><ol className="timeline">{events.data?.map(item=><li key={item.id}><strong>{item.action.replaceAll('_',' ')}</strong><br/><time>{new Date(item.created_at).toLocaleString()}</time>{item.details.reason?<p>{String(item.details.reason)}</p>:null}</li>)}</ol></details>
  </>;
}

export function MobileAudit() {
  const {id}=useParams(),audit=useApi<Audit>(`/audits/${id}`),targets=useApi<Target[]>(`/audits/${id}/targets`);
  const [site,setSite]=useState(''),[block,setBlock]=useState(''),[floor,setFloor]=useState('');
  const assigned=targets.data?.filter(x=>x.assigned_to_me)??[];
  const filtered=assigned.filter(x=>(!site||text(x,'site')===site)&&(!block||text(x,'block')===block)&&(!floor||text(x,'floor')===floor));
  const groups=new Map<string,Target[]>();
  filtered.forEach(target=>{const key=`${text(target,'site_id')}:${text(target,'block_id')}:${text(target,'floor_id')}:${text(target,'unit_id')}`;groups.set(key,[...(groups.get(key)??[]),target]);});
  const choices=(key:string,values:Target[])=>[...new Set(values.map(x=>text(x,key)))].sort();
  return <><Link to="/app">← My audits</Link><div className="page-title"><h2>{audit.data?.title??'Assigned rooms'}</h2><Badge>{audit.data?.status}</Badge></div><State pending={targets.isPending} error={audit.error||targets.error}/>
    <p>Navigate to your assigned unit, room and telco. The room list follows this audit’s saved layout.</p><div className="grid3">
      <label>Site<select value={site} onChange={e=>{setSite(e.target.value);setBlock('');setFloor('');}}><option value="">All assigned sites</option>{choices('site',assigned).map(x=><option key={x}>{x}</option>)}</select></label>
      <label>Block<select value={block} onChange={e=>{setBlock(e.target.value);setFloor('');}}><option value="">All blocks</option>{choices('block',assigned.filter(x=>!site||text(x,'site')===site)).map(x=><option key={x}>{x}</option>)}</select></label>
      <label>Floor<select value={floor} onChange={e=>setFloor(e.target.value)}><option value="">All floors</option>{choices('floor',assigned.filter(x=>(!site||text(x,'site')===site)&&(!block||text(x,'block')===block))).map(x=><option key={x}>{x}</option>)}</select></label></div>
    {getWorkspaceOwner()&&<OfflinePreparation auditId={Number(id)} owner={getWorkspaceOwner()!}/>}
    {[...groups].map(([key,values])=><section key={key}><small>{text(values[0],'site')} / {text(values[0],'block')} / FLOOR {text(values[0],'floor')}</small><h3>Unit {text(values[0],'unit')}</h3>
      {values.map(target=><Link className="room-link" to={`/app/targets/${target.id}`} key={target.id}><span>{text(target,'room')}<small>{text(target,'telco')}</small></span><span aria-hidden="true">→</span></Link>)}</section>)}
    {!targets.isPending&&!assigned.length&&<section><p>No targets are currently assigned to you in this audit.</p></section>}
  </>;
}

export function TargetDetails() {
  const {id}=useParams(),target=useApi<Target>(`/audit-targets/${id}`),value=target.data;
  if(!value)return <State pending={target.isPending} error={target.error}/>;
  return <><Link to={`/app/audits/${value.audit_id}`}>← Assigned rooms</Link><section><small>{text(value,'site')} / {text(value,'block')} / FLOOR {text(value,'floor')}</small>
    <h2>Unit {text(value,'unit')} · {text(value,'room')}</h2><Badge>{text(value,'telco')}</Badge><p>Telco and network generation are staff selected. A browser cannot verify the active SIM or enforce mobile data instead of Wi-Fi.</p>
    {!value.assigned_to_me&&<p>This target is not assigned to your account.</p>}</section>
    {value.assigned_to_me&&getWorkspaceOwner()&&<Capture key={value.id} target={value} owner={getWorkspaceOwner()!}/>}</>;
}
