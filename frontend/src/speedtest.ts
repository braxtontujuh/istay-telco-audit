import type SpeedTest from '@cloudflare/speedtest';
import type { ConfigOptions, Results } from '@cloudflare/speedtest';
import type { InspectionPayload } from './offline-store';

export const SDK_VERSION='1.17.0';
export type Measurement=NonNullable<InspectionPayload['measurement']>;
type ReadResults=Pick<Results,'isFinished'|'raw'|'getDownloadBandwidth'|'getUploadBandwidth'|'getUnloadedLatency'|'getUnloadedJitter'|'getTotalDurationMs'>;
export type Engine=Pick<SpeedTest,'results'|'onFinish'|'onError'|'onResultsChange'|'play'|'pause'>;
export type Progress={download_mbps?:number;upload_mbps?:number;ping_ms?:number;warnings:number};

export function mobileProfile(timeoutSeconds:number):ConfigOptions{
  if(!Number.isInteger(timeoutSeconds)||timeoutSeconds<10||timeoutSeconds>120)throw new Error('Invalid audit test timeout.');
  return{autoStart:false,measurementTargets:['https://speed.cloudflare.com'],includeCredentials:false,
    authorizationToken:null,authorizationEnabled:false,logMeasurementApiUrl:null,logAimApiUrl:null,
    measureDownloadLoadedLatency:false,measureUploadLoadedLatency:false,abortRequestDuration:10000,
    abortTestDuration:timeoutSeconds*1000,bandwidthFinishRequestDuration:1000,
    measurements:[{type:'latency',numPackets:6},{type:'download',bytes:100000,count:1,bypassMinDuration:true},
      {type:'download',bytes:1000000,count:2},{type:'download',bytes:10000000,count:2},
      {type:'upload',bytes:100000,count:1,bypassMinDuration:true},{type:'upload',bytes:1000000,count:2},
      {type:'upload',bytes:5000000,count:2}]};
}
function finite(value:unknown):value is number{return typeof value==='number'&&Number.isFinite(value)&&value>=0;}
export function extractMeasurement(results:ReadResults,warnings=0):Measurement{
  if(!results.isFinished||results.raw.error||!['latency','download','upload'].every(key=>results.raw[key as 'latency'|'download'|'upload']?.finished))throw new Error('The speed test did not finish all required measurements.');
  const down=results.getDownloadBandwidth(),up=results.getUploadBandwidth(),ping=results.getUnloadedLatency(),jitter=results.getUnloadedJitter(),duration=results.getTotalDurationMs();
  if(!finite(down)||!finite(up)||!finite(ping)||!finite(duration)||duration<=0||duration>300000)throw new Error('Download, upload, latency or duration was missing or invalid.');
  if(jitter!=null&&!finite(jitter))throw new Error('Jitter was invalid.');
  return{download_mbps:down/1e6,upload_mbps:up/1e6,ping_ms:ping,jitter_ms:jitter??null,
    duration_ms:Math.max(1,Math.round(duration)),engine:'cloudflare',engine_version:SDK_VERSION,profile_version:'mobile-v1',
    raw_summary:{download_bps:down,upload_bps:up,unloaded_latency_ms:ping,jitter_ms:jitter??null,warning_count:warnings}};
}

export function runTest(factory:(config:ConfigOptions)=>Engine,timeoutSeconds:number,onProgress:(value:Progress)=>void=()=>{}){
  const engine=factory(mobileProfile(timeoutSeconds));let ended=false,warnings=0,timer:ReturnType<typeof setTimeout>;
  let rejectPromise:(error:Error)=>void=()=>{};
  function detach(){clearTimeout(timer);engine.onFinish=()=>{};engine.onError=()=>{};engine.onResultsChange=()=>{};}
  const promise=new Promise<Measurement>((resolve,reject)=>{
    rejectPromise=reject;
    engine.onError=()=>{warnings++;}; // SDK errors can be recoverable; final completeness/numbers decide success.
    engine.onResultsChange=()=>{
      if(ended)return;const down=engine.results.getDownloadBandwidth(),up=engine.results.getUploadBandwidth(),ping=engine.results.getUnloadedLatency();
      onProgress({download_mbps:finite(down)?down/1e6:undefined,upload_mbps:finite(up)?up/1e6:undefined,ping_ms:finite(ping)?ping:undefined,warnings});
    };
    engine.onFinish=results=>{if(ended)return;ended=true;detach();try{resolve(extractMeasurement(results,warnings));}catch(error){reject(error instanceof Error?error:new Error('Invalid final test results'));}};
    timer=setTimeout(()=>{if(ended)return;ended=true;detach();engine.pause();reject(new Error('Test timed out. No successful speed test was recorded.'));},timeoutSeconds*1000+100);
    try{engine.play();}catch(error){ended=true;detach();engine.pause();reject(error instanceof Error?error:new Error('Unable to start speed test'));}
  });
  return{promise,cancel(reason='Test canceled. No successful speed test was recorded.'){
    if(ended)return;ended=true;detach();engine.pause();rejectPromise(new Error(reason));
  }};
}
export async function cloudflareTest(timeoutSeconds:number,onProgress:(value:Progress)=>void){
  const {default:SpeedTest}=await import('@cloudflare/speedtest');return runTest(config=>new SpeedTest(config),timeoutSeconds,onProgress);
}
