import { z } from 'zod';
import { api, ApiError, getWorkspaceOwner, sessionSchema, setSession } from './api';
import { offline, type Outbox } from './offline-store';

const ackSchema=z.object({results:z.array(z.object({client_id:z.string().nullable(),status:z.enum(['SYNCED','RETRY','CONFLICT']),
  server_id:z.number().int().positive().nullable().optional(),error:z.object({code:z.string(),message:z.string()}).nullable().optional()})).max(20)});
let running:Promise<void>|null=null,controller:AbortController|null=null,generation=0;
export function abortSync(){generation++;controller?.abort();}

export function syncOutbox(owner:number,manual=false){
  if(running)return running;
  const epoch=generation,request=new AbortController();controller=request;
  const sameWorkspace=()=>epoch===generation&&getWorkspaceOwner()===owner;
  const current=()=>sameWorkspace()&&!request.signal.aborted;
  async function work(){
    if(!current())return;
    let claimed:Outbox[]=[];
    try{
      // navigator.onLine is deliberately not treated as proof of API reachability.
      const reachabilityTimer=setTimeout(()=>request.abort(),5000);
      let me;
      try{me=sessionSchema.parse(await api('/auth/me',{signal:request.signal}));}finally{clearTimeout(reachabilityTimer);}
      if(me.user.id!==owner||!current())throw new Error('Sign in as this workspace owner before syncing.');
      setSession(me);
      if(typeof window!=='undefined')window.dispatchEvent(new CustomEvent('istay-session-ready',{detail:me.user}));
      for(let batches=0;batches<6&&current();batches++){
        claimed=await offline.claim(owner,manual);
        if(!claimed.length)break;
        const timer=setTimeout(()=>request.abort(),15000);
        try{
          if(!current())throw new Error('Account changed; original drafts retained.');
          const response=ackSchema.parse(await api('/inspections/batch-sync',{method:'POST',signal:request.signal,
            headers:{'X-Workspace-User':String(owner)},body:JSON.stringify({records:claimed.map(item=>JSON.parse(item.payloadJson))})}));
          if(!current())throw new Error('Account changed before acknowledgments were processed.');
          if(new Set(response.results.map(item=>item.client_id)).size!==response.results.length)throw new Error('Ambiguous server acknowledgments; retrying original UUIDs.');
          const results=new Map(response.results.map(item=>[item.client_id,item]));
          for(const item of claimed){
            const ack=results.get(item.clientId);
            if(ack?.status==='SYNCED'&&ack.server_id)await offline.acknowledge(owner,item.clientId,ack.server_id);
            else await offline.failure(owner,item.clientId,ack?.status==='CONFLICT'?'CONFLICT':'RETRY',ack?.error?.message??'No valid per-record acknowledgment; original UUID retained.');
          }
          claimed=[];
        }finally{clearTimeout(timer);}
      }
      if(current())await offline.setMetadata(owner,'sync_message','Server reachable. Per-record acknowledgments processed.');
    }catch(error){
      const message=error instanceof ApiError&&[401,403,409].includes(error.status)?'Sign in as the original employee to sync this workspace.':
        error instanceof Error?error.message:'Server unreachable. Drafts remain on this device.';
      for(const item of claimed)await offline.failure(owner,item.clientId,'RETRY',message);
      if(sameWorkspace()&&error instanceof ApiError&&[401,409].includes(error.status)&&typeof window!=='undefined')window.dispatchEvent(new CustomEvent('istay-session-unavailable',{detail:{owner}}));
      if(sameWorkspace())await offline.setMetadata(owner,'sync_message',message);
    }
  }
  const operation=async()=>{
    if(typeof navigator!=='undefined'&&navigator.locks)await navigator.locks.request(`istay-sync-${owner}`,{ifAvailable:true},async lock=>{if(lock)await work();});
    else await work();
  };
  running=operation().finally(()=>{running=null;if(controller===request)controller=null;});return running;
}
