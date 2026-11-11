import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, getWorkspaceOwner } from './api';
import { offlineFallback } from './offline-hooks';
import { offline } from './offline-store';
import type { components } from './api-schema';

export type Audit = components['schemas']['AuditView'];
export type Target = components['schemas']['TargetView'];
export type Progress = components['schemas']['ProgressView'];
export type Site = {id: number; code: string; name: string; active: boolean};
export type Block = {id: number; site_id: number; code: string};
export type Floor = {id: number; block_id: number; floor_no: number};
export type Unit = {id: number; floor_id: number; unit_no: string; active: boolean};
export type Room = {id: number; unit_id: number; code: string; name: string; active: boolean; sort_order: number};
export type Telco = {id: number; name: string; active: boolean};
export type Employee = {id: number; username: string; full_name: string; role: string; active: boolean; site_ids: number[]};
export type RoomInput = {code: string; name: string; sort_order: number};
export type Template = {id: number; name: string; items: RoomInput[]};

export function useApi<T>(path: string, enabled = true) {
  const owner=getWorkspaceOwner();
  return useQuery<T>({queryKey: [owner,path], queryFn: async({signal})=>{
    try{
      const value=await api(path,{signal});
      if(owner){
        if(path==='/audits')await offline.refreshKnownAudits(owner,value,true);
        else if(/^\/audits\/\d+$/.test(path))await offline.refreshKnownAudits(owner,[value]);
        else if(/^\/audits\/\d+\/targets$/.test(path))await offline.refreshKnownTargets(owner,Number(path.split('/')[2]),value);
      }
      return value;
    }catch(error){
      if(owner){const cached=await offlineFallback(path,owner,error);if(cached!==undefined)return cached as T;}
      throw error;
    }
  },enabled,networkMode:'always'});
}

export function useAction() {
  const queryClient = useQueryClient();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  async function run<T = unknown>(path: string, value?: unknown, method = 'POST'): Promise<T | undefined> {
    setPending(true); setError('');
    try {
      const result = await api(path, {method, ...(value === undefined ? {} : {body: JSON.stringify(value)})});
      await queryClient.invalidateQueries();
      return result;
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to save'); return undefined; }
    finally { setPending(false); }
  }
  return {run, pending, error, setError};
}

export function ErrorMessage({error}: {error: unknown}) {
  return error ? <p role="alert">{error instanceof Error ? error.message : String(error)}</p> : null;
}
export function State({pending, error}: {pending?: boolean; error: unknown}) {
  return <>{pending && <p role="status">Loading…</p>}<ErrorMessage error={error}/></>;
}
export function Badge({children}: {children: React.ReactNode}) { return <span className="badge">{children}</span>; }
export function CheckList({items, values, onChange}: {items: {id: number; label: string}[]; values: number[]; onChange: (value: number[]) => void}) {
  return <div className="checks">{items.map(item => <label key={item.id}><input type="checkbox" checked={values.includes(item.id)}
    onChange={event => onChange(event.target.checked ? [...values, item.id] : values.filter(id => id !== item.id))}/>{item.label}</label>)}</div>;
}
export function parseRooms(text: string): RoomInput[] {
  return text.split('\n').filter(line => line.trim()).map((line, index) => {
    const parts = line.split('|').map(value => value.trim());
    if (parts.length !== 2 || !parts[0] || !parts[1]) throw new Error('Use one room per line: code | room name');
    return {code: parts[0], name: parts[1], sort_order: index};
  });
}
export const defaultRooms = 'L | Living room\nB1 | Bedroom 1\nB2 | Bedroom 2';

export function HierarchyPicker({siteIds, onUnits}: {siteIds?: number[]; onUnits: (units: Unit[]) => void}) {
  const [site, setSite] = useState(''), [block, setBlock] = useState(''), [floor, setFloor] = useState('');
  const sites = useApi<Site[]>('/sites');
  const blocks = useApi<Block[]>(`/sites/${site}/blocks`, !!site);
  const floors = useApi<Floor[]>(`/blocks/${block}/floors`, !!block);
  const units = useApi<Unit[]>(`/floors/${floor}/units`, !!floor);
  const [chosen, setChosen] = useState<number[]>([]);
  function clearUnits() { setChosen([]); onUnits([]); }
  return <div>
    <div className="grid3">
      <label>Site<select value={site} onChange={e => {setSite(e.target.value); setBlock(''); setFloor(''); clearUnits();}}><option value="">Choose site</option>
        {sites.data?.filter(value => value.active && (!siteIds || siteIds.includes(value.id))).map(value => <option key={value.id} value={value.id}>{value.code}</option>)}</select></label>
      <label>Block<select value={block} disabled={!site} onChange={e => {setBlock(e.target.value); setFloor(''); clearUnits();}}><option value="">Choose block</option>{blocks.data?.map(value => <option key={value.id} value={value.id}>{value.code}</option>)}</select></label>
      <label>Floor<select value={floor} disabled={!block} onChange={e => {setFloor(e.target.value); clearUnits();}}><option value="">Choose floor</option>{floors.data?.map(value => <option key={value.id} value={value.id}>{value.floor_no}</option>)}</select></label>
    </div>
    <State error={sites.error || blocks.error || floors.error || units.error}/>
    {floor && <CheckList items={units.data?.filter(value => value.active).map(value => ({id: value.id, label: `Unit ${value.unit_no}`})) ?? []} values={chosen}
      onChange={values => {setChosen(values); onUnits(units.data?.filter(value => values.includes(value.id)) ?? []);}}/>}
  </div>;
}
