import { useState } from 'react';
import { CheckList, defaultRooms, ErrorMessage, parseRooms, State, useAction, useApi,
  type Block, type Employee, type Floor, type Room, type Site, type Telco, type Template, type Unit } from './ui';

export function SitesPage() {
  const sites = useApi<Site[]>('/sites'); const action = useAction();
  return <><h2>Sites</h2><p>Sites are configuration data. Deactivation preserves historical records.</p><State pending={sites.isPending} error={sites.error}/>
    <section><h3>Add site</h3><form onSubmit={async e => {e.preventDefault(); const form=e.currentTarget, data=new FormData(form);
      if(await action.run('/sites',{code:data.get('code'),name:data.get('name')}) !== undefined) form.reset();}}>
      <div className="grid2"><label>Code<input name="code" required maxLength={40}/></label><label>Name<input name="name" required maxLength={200}/></label></div><button disabled={action.pending}>Add site</button></form></section>
    {sites.data?.map(site => <section key={site.id}><form onSubmit={e => {e.preventDefault(); const data=new FormData(e.currentTarget); void action.run(`/sites/${site.id}`,{code:data.get('code'),name:data.get('name'),active:data.get('active')==='on'},'PATCH');}}>
      <div className="grid2"><label>Code<input name="code" defaultValue={site.code} required/></label><label>Name<input name="name" defaultValue={site.name} required/></label></div>
      <label className="check"><input type="checkbox" name="active" defaultChecked={site.active}/>Active</label><button disabled={action.pending}>Save site</button></form></section>)}<ErrorMessage error={action.error}/></>;
}

export function UnitsPage() {
  const sites=useApi<Site[]>('/sites'), templates=useApi<Template[]>('/room-templates');
  const [site,setSite]=useState(''), [block,setBlock]=useState(''), [floor,setFloor]=useState(''), [unit,setUnit]=useState('');
  const [selected,setSelected]=useState<number[]>([]), [template,setTemplate]=useState('');
  const blocks=useApi<Block[]>(`/sites/${site}/blocks`,!!site), floors=useApi<Floor[]>(`/blocks/${block}/floors`,!!block);
  const units=useApi<Unit[]>(`/floors/${floor}/units`,!!floor), rooms=useApi<Room[]>(`/units/${unit}/locations`,!!unit);
  const action=useAction();
  function simpleForm(path: string, field: string, parent: object) {
    return async (event: React.FormEvent<HTMLFormElement>) => {event.preventDefault(); const form=event.currentTarget, data=new FormData(form);
      const value=field==='floor_no'?Number(data.get(field)):data.get(field);
      const result=await action.run<{id: number}>(path,{...parent,[field]:value});
      if(result) {form.reset(); if(field==='code')setBlock(String(result.id)); else setFloor(String(result.id));}
    };
  }
  return <><h2>Units & room layouts</h2><p>Each unit has its own room list. Editing it preserves activated audit snapshots.</p><ErrorMessage error={action.error}/>
    <section><div className="grid3"><label>Site<select value={site} onChange={e=>{setSite(e.target.value);setBlock('');setFloor('');setUnit('');setSelected([]);}}><option value="">Choose site</option>{sites.data?.filter(x=>x.active).map(x=><option key={x.id} value={x.id}>{x.code}</option>)}</select></label>
      <label>Block<select value={block} onChange={e=>{setBlock(e.target.value);setFloor('');setUnit('');setSelected([]);}}><option value="">Choose block</option>{blocks.data?.map(x=><option key={x.id} value={x.id}>{x.code}</option>)}</select></label>
      <label>Floor<select value={floor} onChange={e=>{setFloor(e.target.value);setUnit('');setSelected([]);}}><option value="">Choose floor</option>{floors.data?.map(x=><option key={x.id} value={x.id}>{x.floor_no}</option>)}</select></label></div>
      <State error={sites.error||blocks.error||floors.error||units.error||rooms.error}/>
      <div className="grid2">{site&&<form onSubmit={simpleForm('/blocks','code',{site_id:Number(site)})}><label>New block code<input name="code" required maxLength={40}/></label><button disabled={action.pending}>Add block</button></form>}
        {block&&<form onSubmit={simpleForm('/floors','floor_no',{block_id:Number(block)})}><label>New floor number<input name="floor_no" type="number" required min={-20} max={200}/></label><button disabled={action.pending}>Add floor</button></form>}</div></section>
    {floor&&<><section><h3>Add a unit</h3><form onSubmit={async e=>{e.preventDefault();const form=e.currentTarget,data=new FormData(form);try{
      const result=await action.run<Unit>('/units',{floor_id:Number(floor),unit_no:data.get('unit_no'),locations:parseRooms(String(data.get('rooms')))});
      if(result){setUnit(String(result.id));form.reset();}}catch(err){action.setError(String(err));}}}>
      <label>Unit number<input name="unit_no" required maxLength={80}/></label><label>Room list — one code | name per line<textarea name="rooms" rows={5} defaultValue={defaultRooms} required/></label><button disabled={action.pending}>Create unit and rooms</button></form></section>
      <section><h3>Units on this floor</h3><div className="grid2"><label>Edit unit<select value={unit} onChange={e=>setUnit(e.target.value)}><option value="">Choose unit</option>{units.data?.map(x=><option key={x.id} value={x.id}>{x.unit_no}{x.active?'':' (inactive)'}</option>)}</select></label></div>
      <h4>Apply a room template to selected units</h4><CheckList items={units.data?.map(x=>({id:x.id,label:x.unit_no}))??[]} values={selected} onChange={setSelected}/>
      <label>Template<select value={template} onChange={e=>setTemplate(e.target.value)}><option value="">Choose template</option>{templates.data?.map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
      <button disabled={action.pending||!template||!selected.length} onClick={()=>void action.run(`/room-templates/${template}/apply`,{unit_ids:selected})}>Apply layout</button>
      <p className="muted">Rooms absent from the template become inactive. Existing room IDs and activated audit history are preserved.</p></section></>}
    {unit&&<section><h3>Rooms in unit {units.data?.find(x=>String(x.id)===unit)?.unit_no}</h3>{rooms.data?.map(room=><form key={room.id} className="room-edit" onSubmit={e=>{e.preventDefault();const data=new FormData(e.currentTarget);
      void action.run(`/locations/${room.id}`,{code:data.get('code'),name:data.get('name'),sort_order:room.sort_order,active:data.get('active')==='on'},'PATCH');}}>
      <div className="grid2"><label>Code<input name="code" defaultValue={room.code} required/></label><label>Name<input name="name" defaultValue={room.name} required/></label></div>
      <label className="check"><input name="active" type="checkbox" defaultChecked={room.active}/>Active</label><button disabled={action.pending}>Save room</button></form>)}
      <h4>Add custom space</h4><form onSubmit={async e=>{e.preventDefault();const form=e.currentTarget,data=new FormData(form);if(await action.run(`/units/${unit}/locations`,{code:data.get('code'),name:data.get('name'),sort_order:rooms.data?.length??0})!==undefined)form.reset();}}>
        <div className="grid2"><label>Code<input name="code" required/></label><label>Name<input name="name" required/></label></div><button disabled={action.pending}>Add space</button></form></section>}
  </>;
}

export function TemplatesPage() {
  const templates=useApi<Template[]>('/room-templates'),action=useAction();
  const [editing,setEditing]=useState<Template|null>(null);
  return <><h2>Room templates</h2><p>Create reusable layouts, then apply them to units in Units & room layouts.</p><State error={templates.error}/>
    <section key={editing?.id??'new'}><h3>{editing?'Edit template':'New template'}</h3><form onSubmit={async e=>{e.preventDefault();const data=new FormData(e.currentTarget);try{
      const result=await action.run(editing?`/room-templates/${editing.id}`:'/room-templates',{name:data.get('name'),items:parseRooms(String(data.get('rooms')))},editing?'PATCH':'POST');
      if(result!==undefined)setEditing(null);}catch(err){action.setError(String(err));}}}>
      <label>Name<input name="name" defaultValue={editing?.name??''} required/></label><label>Rooms — code | name<textarea name="rooms" rows={5} defaultValue={editing?editing.items.map(x=>`${x.code} | ${x.name}`).join('\n'):defaultRooms} required/></label>
      <button disabled={action.pending}>Save template</button>{editing&&<button type="button" className="secondary" onClick={()=>setEditing(null)}>Cancel edit</button>}</form></section>
    {templates.data?.map(value=><section key={value.id}><h3>{value.name}</h3><p>{value.items.map(x=>x.name).join(' · ')}</p><button className="secondary" onClick={()=>setEditing(value)}>Edit template</button>{' '}
      <button className="danger" disabled={action.pending} onClick={()=>{if(confirm('Delete this template? Existing unit layouts and audit history are retained.'))void action.run(`/room-templates/${value.id}`,undefined,'DELETE');}}>Delete template</button></section>)}<ErrorMessage error={action.error}/></>;
}

export function TelcosPage() {
  const telcos=useApi<Telco[]>('/telcos'),action=useAction();
  return <><h2>Telcos</h2><section><form onSubmit={async e=>{e.preventDefault();const form=e.currentTarget,data=new FormData(form);if(await action.run('/telcos',{name:data.get('name')})!==undefined)form.reset();}}>
    <label>New telco name<input name="name" required maxLength={200}/></label><button disabled={action.pending}>Add telco</button></form></section><State error={telcos.error}/>
    {telcos.data?.map(value=><section key={value.id}><form onSubmit={e=>{e.preventDefault();const data=new FormData(e.currentTarget);void action.run(`/telcos/${value.id}`,{name:data.get('name'),active:data.get('active')==='on'},'PATCH');}}>
      <label>Name<input name="name" defaultValue={value.name} required/></label><label className="check"><input type="checkbox" name="active" defaultChecked={value.active}/>Active for new targets</label><button disabled={action.pending}>Save telco</button></form></section>)}<ErrorMessage error={action.error}/></>;
}

export function UsersPage() {
  const users=useApi<Employee[]>('/users'),sites=useApi<Site[]>('/sites'),action=useAction(); const [chosen,setChosen]=useState<number[]>([]);
  return <><h2>Employee accounts</h2><p>Give each employee an individual account and only the sites they need. Permission changes revoke their current sessions.</p>
    <section><h3>Create employee</h3><form onSubmit={async e=>{e.preventDefault();const form=e.currentTarget,data=new FormData(form);
      if(await action.run('/users',{username:data.get('username'),full_name:data.get('full_name'),password:data.get('password'),role:data.get('role'),site_ids:chosen})!==undefined){form.reset();setChosen([]);}}}>
      <div className="grid2"><label>Username<input name="username" autoComplete="off" pattern="[a-z0-9][a-z0-9._-]{2,79}" required/></label><label>Full name<input name="full_name" required/></label></div>
      <label>Initial password<input name="password" type="password" autoComplete="new-password" minLength={14} maxLength={256} required/></label>
      <label>Role<select name="role" defaultValue="AUDITOR"><option>AUDITOR</option><option>MANAGER</option><option>ADMIN</option></select></label>
      <fieldset><legend>Permitted sites</legend><CheckList items={sites.data?.filter(x=>x.active).map(x=>({id:x.id,label:x.code}))??[]} values={chosen} onChange={setChosen}/></fieldset><button disabled={action.pending}>Create account</button></form></section>
    <State error={users.error||sites.error}/>{users.data?.map(value=><EmployeeEditor key={value.id} value={value} sites={sites.data??[]}/>)}<ErrorMessage error={action.error}/></>;
}
function EmployeeEditor({value,sites}: {value: Employee; sites: Site[]}) {
  const [chosen,setChosen]=useState(value.site_ids),action=useAction();
  return <section><h3>{value.username}</h3><form onSubmit={e=>{e.preventDefault();const data=new FormData(e.currentTarget);void action.run(`/users/${value.id}`,{full_name:data.get('full_name'),role:data.get('role'),active:data.get('active')==='on',site_ids:chosen},'PATCH');}}>
    <label>Full name<input name="full_name" defaultValue={value.full_name} required/></label><label>Role<select name="role" defaultValue={value.role}><option>AUDITOR</option><option>MANAGER</option><option>ADMIN</option></select></label>
    <label className="check"><input type="checkbox" name="active" defaultChecked={value.active}/>Active</label><CheckList items={sites.filter(x=>x.active).map(x=>({id:x.id,label:x.code}))} values={chosen} onChange={setChosen}/>
    <button disabled={action.pending}>Save account access</button></form><ErrorMessage error={action.error}/></section>;
}
