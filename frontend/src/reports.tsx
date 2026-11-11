import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { getWorkspaceOwner } from './api';
import { ProgressCards } from './audit-pages';
import { Badge, ErrorMessage, State, useApi, type Audit, type Progress, type Target } from './ui';

type Counts={total:number;inspected:number;pending:number;tested:number;no_signal:number;no_internet:number;completion_percent:number;speedtest_success_percent:number|null;issue_percent_of_inspected:number|null};
type Result={target_id:number;site:string;block:string;floor:number;floor_id:number;unit:string;room:string;telco:string;outcome:string;inspection_id?:number;user_id?:number;download_mbps?:number;upload_mbps?:number;ping_ms?:number;remarks?:string;observed_at?:string;received_at?:string;clock_skew_flag?:boolean;weak_reasons?:string[]};
type Report={audit_id:number;title:string;status:string;generated_at:string;policy:string;averages_warning:string;config_snapshot:Record<string,unknown>;
  summary:Progress&Counts&{attempt_count:number};latest_results:Result[];all_attempts:Result[];weak_locations:Result[];
  coverage:(Counts&{site:string;block:string;floor:number;floor_id:number;weak_targets:number})[];
  telco_comparison:(Counts&{telco:string;sample_count:number;avg_download_mbps:number|null;avg_upload_mbps:number|null;avg_ping_ms:number|null;first_received_at:string|null;last_received_at:string|null})[]};
const number=(value:number|null|undefined)=>value==null?'—':value.toFixed(2);
const date=(value:string|null|undefined)=>value?new Date(value).toLocaleString():'—';

export function Dashboard(){
  const summary=useApi<{audit_count:number;summary:Progress;scope_note:string}>('/dashboard/summary');
  return <><small>MANAGEMENT</small><h2>Audit overview</h2><State pending={summary.isPending} error={summary.error}/>
    {summary.data&&<><p>{summary.data.audit_count} accessible audits</p><ProgressCards value={summary.data.summary}/><p className="muted">{summary.data.scope_note}</p></>}
    <div className="toolbar"><Link className="button" to="/admin/audits">Manage audits</Link><Link className="button" to="/admin/reports">Coverage & reports</Link></div>
    <section><h3>Review with context</h3><p>Compare telcos within the same audit and check tested counts, no-service outcomes and pending targets before using speed averages. Ratings use each audit’s frozen thresholds.</p></section></>;
}

function ResultTable({rows,history=false}:{rows:Result[];history?:boolean}){
  return <><p className="muted">Showing {Math.min(rows.length,500)} of {rows.length} records. Excel contains all rows in the selected scope.</p><div className="table-scroll"><table><thead><tr><th>Location / telco</th><th>Outcome</th><th>Down / up Mbps</th><th>Ping ms</th><th>Observed / received</th>{history&&<th>Employee / remarks</th>}</tr></thead><tbody>
    {rows.slice(0,500).map((row,index)=><tr key={`${row.target_id}-${row.inspection_id??index}`}><td><Link to={`/app/targets/${row.target_id}`}>{row.site} / {row.block} / {row.floor} / {row.unit} / {row.room}</Link><br/>{row.telco}</td>
      <td>{row.outcome.replaceAll('_',' ')}{row.weak_reasons&&<small>{row.weak_reasons.join(', ')}</small>}</td><td>{number(row.download_mbps)} / {number(row.upload_mbps)}</td><td>{number(row.ping_ms)}</td><td>{date(row.observed_at)}<small>{date(row.received_at)}{row.clock_skew_flag?' · Device clock skew':''}</small></td>{history&&<td>{row.user_id?`Employee ${row.user_id}`:'—'}<small>{row.remarks}</small></td>}</tr>)}
  </tbody></table></div>{rows.length===0&&<p>No records in this scope.</p>}</>;
}

export function ReportsPage(){
  const [params,setParams]=useSearchParams(),id=Number(params.get('audit')??0),audits=useApi<Audit[]>('/audits');
  const [site,setSite]=useState(''),[telco,setTelco]=useState(''),[floor,setFloor]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const targets=useApi<Target[]>(`/audits/${id}/targets`,!!id);
  const scope=new URLSearchParams({...site?{site_id:site}:{},...telco?{telco_id:telco}:{},...floor?{floor_id:floor}:{}}).toString();
  const data=useApi<Report>(`/audits/${id}/results${scope?'?'+scope:''}`,!!id),report=data.data;
  function options(key:string,label:string){return [...new Map((targets.data??[]).filter(value=>!site||String(value.snapshot.site_id)===site).map(value=>[String(value.snapshot[key]),String(value.snapshot[label])])).entries()];}
  async function download(){
    const owner=getWorkspaceOwner();setBusy(true);setError('');
    try{
      const response=await fetch(`/api/v1/audits/${id}/export.xlsx${scope?'?'+scope:''}`,{credentials:'same-origin',cache:'no-store',headers:{'X-Workspace-User':String(owner)}});
      if(!response.ok)throw new Error(response.status===413?'Narrow the report filters before exporting.':`Export failed (${response.status}). Check access and sign in again if needed.`);
      const blob=await response.blob();if(getWorkspaceOwner()!==owner)throw new Error('Account changed during download.');
      const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`istay-audit-${id}.xlsx`;link.click();setTimeout(()=>URL.revokeObjectURL(url),10000);
    }catch(err){setError(err instanceof Error?err.message:'Unable to export');}finally{setBusy(false);}
  }
  return <><small>MANAGEMENT</small><h2>Coverage & reports</h2><State error={audits.error}/><label>Audit<select value={id||''} onChange={e=>{setParams({audit:e.target.value});setSite('');setTelco('');setFloor('');}}><option value="">Choose an audit</option>{audits.data?.map(value=><option key={value.id} value={value.id}>{value.title} · {value.status}</option>)}</select></label>
    {!!id&&<><div className="grid3"><label>Site filter<select value={site} onChange={e=>{setSite(e.target.value);setFloor('');}}><option value="">All sites in audit</option>{[...new Map((targets.data??[]).map(value=>[String(value.snapshot.site_id),String(value.snapshot.site)])).entries()].map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
      <label>Telco filter<select value={telco} onChange={e=>setTelco(e.target.value)}><option value="">All telcos</option>{options('telco_id','telco').map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
      <label>Floor filter<select value={floor} onChange={e=>setFloor(e.target.value)}><option value="">All floors</option>{options('floor_id','floor').map(([value,label])=><option key={value} value={value}>Floor {label} (ID {value})</option>)}</select></label></div><State pending={data.isPending} error={data.error||targets.error}/></>}
    {report&&<><div className="page-title"><h3>{report.title}</h3><Badge>{report.status}</Badge></div><ProgressCards value={report.summary}/><p>{report.policy}</p><p className="notice">{report.averages_warning}</p><p className="muted">Generated {date(report.generated_at)} · Thresholds: download below {String(report.config_snapshot.weak_download_mbps)} Mbps, upload below {String(report.config_snapshot.weak_upload_mbps)} Mbps, ping above {String(report.config_snapshot.high_ping_ms)} ms.</p>
      <div className="toolbar"><button disabled={busy} onClick={download}>{busy?'Preparing Excel…':'Download Excel report'}</button><Link to={`/admin/audits/${id}`}>Review audit & assignments</Link></div><ErrorMessage error={error}/>
      <section><h3>Floor coverage</h3><p>Each tile shows inspection completion and weak/no-service outcomes. Pending targets are excluded from issue rates.</p><div className="floor-grid">{report.coverage.map(row=><div key={row.floor_id} className={`floor-tile ${row.weak_targets?'floor-weak':row.pending?'floor-pending':'floor-complete'}`}><strong>{row.site} / {row.block} / Floor {row.floor}</strong><p>{row.inspected} / {row.total} inspected · {row.completion_percent}%</p><p>{row.weak_targets} weak or no-service · {row.pending} pending</p><p>{row.tested} tested · {row.no_signal} no signal · {row.no_internet} no internet</p></div>)}</div></section>
      <section><h3>Telco comparison</h3><div className="table-scroll"><table><thead><tr><th>Telco</th><th>Inspected / total</th><th>Tested samples</th><th>No signal / no internet</th><th>Issue rate</th><th>Mean down / up Mbps</th><th>Mean ping ms</th><th>Server sample dates</th></tr></thead><tbody>{report.telco_comparison.map(row=><tr key={row.telco}><td>{row.telco}</td><td>{row.inspected} / {row.total}</td><td>{row.sample_count}</td><td>{row.no_signal} / {row.no_internet}</td><td>{number(row.issue_percent_of_inspected)}%</td><td>{number(row.avg_download_mbps)} / {number(row.avg_upload_mbps)}</td><td>{number(row.avg_ping_ms)}</td><td>{date(row.first_received_at)}<small>{date(row.last_received_at)}</small></td></tr>)}</tbody></table></div></section>
      <section><h3>Weak locations</h3><ResultTable rows={report.weak_locations}/></section><section><h3>Latest conclusive outcomes & pending targets</h3><ResultTable rows={report.latest_results}/></section><section><h3>All accepted attempts</h3><ResultTable rows={report.all_attempts} history/></section></>}
  </>;
}
