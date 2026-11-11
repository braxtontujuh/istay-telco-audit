import { useEffect, useState } from 'react';
import { ApiError } from './api';
import { offline, shellReady, type CachedAudit, type Outbox } from './offline-store';
import { syncOutbox } from './sync';
import { recoverInterrupted } from './attempts';

export async function offlineFallback(path:string,owner:number,error:unknown):Promise<unknown>{
  if(error instanceof ApiError&&error.status!==401)return undefined;
  if(path==='/audits')return(await offline.audits(owner)).filter(value=>!value.accessRevoked).map(value=>value.audit);
  let match=path.match(/^\/audits\/(\d+)$/);
  if(match)return(await offline.audit(owner,Number(match[1])))?.audit;
  match=path.match(/^\/audits\/(\d+)\/targets$/);
  if(match&&await offline.audit(owner,Number(match[1])))return offline.targets(owner,Number(match[1]));
  match=path.match(/^\/audit-targets\/(\d+)$/);
  if(match)return offline.target(owner,Number(match[1]));
  return undefined;
}

export function useLocal(owner:number){
  const [state,setState]=useState<{owner:number;items:Outbox[];audits:CachedAudit[];shell:boolean;message:string}>({owner,items:[],audits:[],shell:false,message:''});
  useEffect(()=>{
    let stopped=false;
    async function refresh(){
      try{const [items,audits,shell,message]=await Promise.all([offline.outbox(owner),offline.audits(owner),shellReady(),offline.metadata<string>(owner,'sync_message')]);
        if(!stopped)setState({owner,items,audits,shell,message:message??''});}catch(error){if(!stopped)setState({owner,items:[],audits:[],shell:false,message:`Local storage unavailable: ${String(error)}`});}
    }
    void refresh();window.addEventListener('istay-storage-changed',refresh);navigator.serviceWorker?.addEventListener('controllerchange',refresh);
    return()=>{stopped=true;window.removeEventListener('istay-storage-changed',refresh);navigator.serviceWorker?.removeEventListener('controllerchange',refresh);};
  },[owner]);
  const value=state.owner===owner?state:{owner,items:[],audits:[],shell:false,message:''};
  return {...value,pending:value.items.filter(item=>item.syncStatus!=='SYNCED').length};
}

export function useSyncLifecycle(owner:number){
  useEffect(()=>{
    const run=()=>{if(document.visibilityState==='visible')void recoverInterrupted(owner).then(()=>syncOutbox(owner)).catch(()=>{/* Local storage errors are displayed by useLocal; never claim a save. */});};
    run();window.addEventListener('online',run);window.addEventListener('focus',run);document.addEventListener('visibilitychange',run);
    const timer=setInterval(run,60000);
    return()=>{clearInterval(timer);window.removeEventListener('online',run);window.removeEventListener('focus',run);document.removeEventListener('visibilitychange',run);};
  },[owner]);
}
