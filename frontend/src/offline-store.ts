import { openDB, type DBSchema, type IDBPDatabase } from 'idb';
import type { components } from './api-schema';
import type { Audit, Target } from './ui';

export type Identity = components['schemas']['UserView'];
export type InspectionPayload = components['schemas']['InspectionPayload'];
export type SyncStatus = 'PENDING'|'SYNCING'|'SYNCED'|'RETRY'|'CONFLICT';
export type CachedAudit = {owner:number;version:1;audit:Audit;downloadedAt:string;accessRevoked?:boolean};
export type SpeedAttempt={base:Omit<InspectionPayload,'outcome'|'measurement'>;targetSnapshot:Target['snapshot'];expiresAt:number};
export type Outbox = {owner:number;version:1;clientId:string;payloadJson:string;targetSnapshot:Target['snapshot'];
  syncStatus:SyncStatus;retryCount:number;nextAttemptAt:number;savedAt:string;syncingAt?:number;serverId?:number;error?:string};
type CachedTarget = {owner:number;version:1;target:Target};
type Metadata = {owner:number;version:1;key:string;value:unknown};
interface OfflineDB extends DBSchema {
  audit_cache:{key:[number,number];value:CachedAudit;indexes:{owner:number}};
  target_cache:{key:[number,number];value:CachedTarget;indexes:{owner:number;audit:[number,number]}};
  outbox:{key:[number,string];value:Outbox;indexes:{owner:number}};
  sync_metadata:{key:[number,string];value:Metadata;indexes:{owner:number}};
}
function changed(owner:number) {
  if(typeof window!=='undefined')window.dispatchEvent(new CustomEvent('istay-storage-changed',{detail:{owner}}));
}

export class OfflineStore {
  private connection?:Promise<IDBPDatabase<OfflineDB>>;
  constructor(private name='istay-audit-v1'){}
  private db(){
    this.connection??=openDB<OfflineDB>(this.name,1,{upgrade(db){
      db.createObjectStore('audit_cache').createIndex('owner','owner');
      const targets=db.createObjectStore('target_cache');targets.createIndex('owner','owner');targets.createIndex('audit',['owner','target.audit_id']);
      db.createObjectStore('outbox').createIndex('owner','owner');db.createObjectStore('sync_metadata').createIndex('owner','owner');
    }});return this.connection;
  }
  async close(){(await this.connection)?.close();this.connection=undefined;}
  async metadata<T>(owner:number,key:string):Promise<T|undefined>{return (await (await this.db()).get('sync_metadata',[owner,key]))?.value as T|undefined;}
  async setMetadata(owner:number,key:string,value:unknown){await(await this.db()).put('sync_metadata',{owner,version:1,key,value},[owner,key]);changed(owner);}
  async remember(identity:Identity){await this.setMetadata(identity.id,'identity',identity);}
  async audit(owner:number,id:number){return (await this.db()).get('audit_cache',[owner,id]);}
  async audits(owner:number){return (await this.db()).getAllFromIndex('audit_cache','owner',owner);}
  async target(owner:number,id:number){return (await(await this.db()).get('target_cache',[owner,id]))?.target;}
  async targets(owner:number,auditId:number){return (await(await this.db()).getAllFromIndex('target_cache','audit',[owner,auditId])).map(value=>value.target);}
  async outbox(owner:number){return (await(await this.db()).getAllFromIndex('outbox','owner',owner)).sort((a,b)=>a.savedAt.localeCompare(b.savedAt));}
  async refreshKnownAudits(owner:number,audits:Audit[],completeList=false){
    const tx=(await this.db()).transaction('audit_cache','readwrite'),store=tx.objectStore('audit_cache');
    for(const cached of await store.index('owner').getAll(owner)){
      const audit=audits.find(value=>value.id===cached.audit.id);
      if(audit)await store.put({...cached,audit,accessRevoked:false},[owner,audit.id]);
      else if(completeList)await store.put({...cached,accessRevoked:true},[owner,cached.audit.id]);
    }
    await tx.done;changed(owner);
  }
  async refreshKnownTargets(owner:number,auditId:number,targets:Target[]){
    const tx=(await this.db()).transaction(['audit_cache','target_cache'],'readwrite');
    const cached=await tx.objectStore('audit_cache').get([owner,auditId]);
    if(cached){
      const assigned=targets.filter(value=>value.assigned_to_me&&value.assigned_user_ids.includes(owner));
      for(const key of await tx.objectStore('target_cache').index('audit').getAllKeys([owner,auditId]))await tx.objectStore('target_cache').delete(key);
      for(const target of assigned)await tx.objectStore('target_cache').put({owner,version:1,target},[owner,target.id]);
      await tx.objectStore('audit_cache').put({...cached,accessRevoked:!assigned.length},[owner,auditId]);
    }
    await tx.done;if(cached)changed(owner);
  }
  async cacheAudit(owner:number,audit:Audit,targets:Target[]){
    if(!['ACTIVE','COMPLETED'].includes(audit.status))throw new Error('Only active/completed assignments can be prepared for offline capture.');
    const assigned=targets.filter(value=>value.assigned_to_me&&value.assigned_user_ids.includes(owner));
    if(!assigned.length)throw new Error('No targets are assigned to your account.');
    const db=await this.db(),tx=db.transaction(['audit_cache','target_cache'],'readwrite');
    const old=await tx.objectStore('target_cache').index('audit').getAllKeys([owner,audit.id]);
    for(const key of old)await tx.objectStore('target_cache').delete(key);
    for(const target of assigned)await tx.objectStore('target_cache').put({owner,version:1,target},[owner,target.id]);
    const cached:CachedAudit={owner,version:1,audit,downloadedAt:new Date().toISOString()};
    await tx.objectStore('audit_cache').put(cached,[owner,audit.id]);await tx.done;changed(owner);return cached;
  }
  async save(owner:number,payload:InspectionPayload):Promise<Outbox>{
    const db=await this.db(),tx=db.transaction(['audit_cache','target_cache','outbox'],'readwrite');
    const target=(await tx.objectStore('target_cache').get([owner,payload.target_id]))?.target;
    if(!target?.assigned_to_me||!target.assigned_user_ids.includes(owner)){tx.abort();await tx.done.catch(()=>{});throw new Error('Download your assigned audit before saving an offline inspection.');}
    const audit=await tx.objectStore('audit_cache').get([owner,target.audit_id]);
    if(!audit||audit.version!==1||audit.accessRevoked||!['ACTIVE','COMPLETED'].includes(audit.audit.status)){tx.abort();await tx.done.catch(()=>{});throw new Error('No active cached assignment is available.');}
    if(await tx.objectStore('outbox').get([owner,payload.client_id])){tx.abort();await tx.done.catch(()=>{});throw new Error('This client UUID already exists; retries must use the original stored payload.');}
    const item:Outbox={owner,version:1,clientId:payload.client_id,payloadJson:JSON.stringify(payload),targetSnapshot:target.snapshot,
      syncStatus:'PENDING',retryCount:0,nextAttemptAt:0,savedAt:new Date().toISOString()};
    await tx.objectStore('outbox').add(item,[owner,item.clientId]);await tx.done;changed(owner);return item;
  }
  async beginSpeedAttempt(owner:number,base:SpeedAttempt['base'],timeoutSeconds:number){
    const tx=(await this.db()).transaction(['audit_cache','target_cache','sync_metadata'],'readwrite');
    const target=(await tx.objectStore('target_cache').get([owner,base.target_id]))?.target;
    const audit=target?await tx.objectStore('audit_cache').get([owner,target.audit_id]):undefined;
    const running=(await tx.objectStore('sync_metadata').index('owner').getAll(owner)).filter(value=>value.key.startsWith('speedtest:')&&value.value) as (Metadata&{value:SpeedAttempt})[];
    if(!target?.assigned_to_me||!target.assigned_user_ids.includes(owner)||!audit||audit.accessRevoked||!['ACTIVE','COMPLETED'].includes(audit.audit.status)||running.some(value=>value.value.base.target_id===base.target_id&&value.value.expiresAt>Date.now())){
      tx.abort();await tx.done.catch(()=>{});throw new Error('Download an active assignment and finish/cancel any running test for this room.');
    }
    const attempt:SpeedAttempt={base,targetSnapshot:target.snapshot,expiresAt:Date.now()+timeoutSeconds*1000+30000};
    await tx.objectStore('sync_metadata').put({owner,version:1,key:`speedtest:${base.client_id}`,value:attempt},[owner,`speedtest:${base.client_id}`]);
    await tx.done;changed(owner);return attempt;
  }
  async speedAttempts(owner:number){return(await(await this.db()).getAllFromIndex('sync_metadata','owner',owner)).filter(value=>value.key.startsWith('speedtest:')&&value.value).map(value=>value.value as SpeedAttempt);}
  async finishSpeedAttempt(owner:number,attempt:SpeedAttempt,payload:InspectionPayload){
    const tx=(await this.db()).transaction(['outbox','sync_metadata'],'readwrite'),store=tx.objectStore('outbox');
    const marker=await tx.objectStore('sync_metadata').get([owner,`speedtest:${attempt.base.client_id}`]);
    let item=await store.get([owner,attempt.base.client_id]);
    if(!item){
      if(!marker?.value||payload.client_id!==attempt.base.client_id||payload.target_id!==attempt.base.target_id){tx.abort();await tx.done.catch(()=>{});throw new Error('Original test attempt metadata is missing or mismatched.');}
      item={owner,version:1,clientId:payload.client_id,payloadJson:JSON.stringify(payload),targetSnapshot:attempt.targetSnapshot,
        syncStatus:'PENDING',retryCount:0,nextAttemptAt:0,savedAt:new Date().toISOString()};
      await store.add(item,[owner,item.clientId]);
    }
    await tx.objectStore('sync_metadata').delete([owner,`speedtest:${attempt.base.client_id}`]);await tx.done;changed(owner);return item;
  }
  async claim(owner:number,manual=false,now=Date.now()){
    const tx=(await this.db()).transaction('outbox','readwrite'),store=tx.objectStore('outbox');
    const values=await store.index('owner').getAll(owner),claimed:Outbox[]=[];
    for(const value of values){
      const stale=value.syncStatus==='SYNCING'&&now-(value.syncingAt??0)>120000;
      if(claimed.length<20&&(stale||['PENDING','RETRY'].includes(value.syncStatus))&&(manual||value.nextAttemptAt<=now)){
        const item={...value,syncStatus:'SYNCING' as const,syncingAt:now};await store.put(item,[owner,item.clientId]);claimed.push(item);
      }
    }
    await tx.done;if(claimed.length)changed(owner);return claimed;
  }
  async acknowledge(owner:number,clientId:string,serverId:number){
    if(!Number.isInteger(serverId)||serverId<1)throw new Error('A valid server acknowledgment is required.');
    const tx=(await this.db()).transaction('outbox','readwrite'),store=tx.objectStore('outbox'),value=await store.get([owner,clientId]);
    if(value){await store.put({...value,syncStatus:'SYNCED',serverId,error:undefined,syncingAt:undefined},[owner,clientId]);}
    await tx.done;changed(owner);
  }
  async failure(owner:number,clientId:string,status:'RETRY'|'CONFLICT',error:string){
    const tx=(await this.db()).transaction('outbox','readwrite'),store=tx.objectStore('outbox'),value=await store.get([owner,clientId]);
    if(value&&value.syncStatus!=='SYNCED'){
      const retryCount=value.retryCount+1;
      await store.put({...value,syncStatus:status,retryCount,error,syncingAt:undefined,
        nextAttemptAt:Date.now()+Math.min(300000,1000*2**Math.min(retryCount,10))},[owner,clientId]);
    }
    await tx.done;changed(owner);
  }
  async retryConflict(owner:number,clientId:string){
    const tx=(await this.db()).transaction('outbox','readwrite'),store=tx.objectStore('outbox'),value=await store.get([owner,clientId]);
    if(value?.syncStatus==='CONFLICT')await store.put({...value,syncStatus:'RETRY',nextAttemptAt:0},[owner,clientId]);
    await tx.done;changed(owner);
  }
  async clearOwner(owner:number){
    const tx=(await this.db()).transaction(['audit_cache','target_cache','outbox','sync_metadata'],'readwrite');
    const activeTests=(await tx.objectStore('sync_metadata').index('owner').getAll(owner)).some(value=>value.key.startsWith('speedtest:')&&value.value);
    if(activeTests||(await tx.objectStore('outbox').index('owner').getAll(owner)).some(value=>value.syncStatus!=='SYNCED')){
      tx.abort();await tx.done.catch(()=>{});throw new Error('Sync or resolve pending records before clearing this workspace.');
    }
    for(const name of ['audit_cache','target_cache','outbox','sync_metadata'] as const){
      const store=tx.objectStore(name);for(const key of await store.index('owner').getAllKeys(owner))await store.delete(key as never);
    }
    await tx.done;changed(owner);
  }
}
export const offline=new OfflineStore();

export function activeOwner(){
  const value=sessionStorage.getItem('istay-active-owner')??localStorage.getItem('istay-active-owner');
  return value&&Number.isInteger(Number(value))&&Number(value)>0?Number(value):null;
}
export function activateOwner(owner:number,personalDevice:boolean){
  sessionStorage.setItem('istay-active-owner',String(owner));
  if(personalDevice)localStorage.setItem('istay-active-owner',String(owner));else localStorage.removeItem('istay-active-owner');
  localStorage.removeItem('istay-workspace-locked');
}
export function lockWorkspace(){sessionStorage.removeItem('istay-active-owner');localStorage.removeItem('istay-active-owner');localStorage.setItem('istay-workspace-locked','true');}

export async function shellReady(){
  if(!('serviceWorker'in navigator)||!navigator.serviceWorker.controller)return false;
  const registration=await navigator.serviceWorker.getRegistration();if(!registration?.active)return false;
  const assets=['/index.html','/icon-192.png',...Array.from(document.querySelectorAll<HTMLScriptElement>('script[src]')).map(value=>new URL(value.src).pathname),
    ...Array.from(document.querySelectorAll<HTMLLinkElement>('link[rel="stylesheet"]')).map(value=>new URL(value.href).pathname)];
  for(const path of assets)if(!await caches.match(new Request(new URL(path,location.origin)),{ignoreSearch:true}))return false;
  return true;
}
