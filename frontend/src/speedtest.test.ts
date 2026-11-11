import { readFileSync } from 'node:fs';
import type { Results } from '@cloudflare/speedtest';
import { afterEach, expect, it, vi } from 'vitest';
import { extractMeasurement, mobileProfile, runTest, SDK_VERSION, type Engine } from './speedtest';

function result(){return{isFinished:true,raw:{totalDurationMs:19000,latency:{started:true,finished:true,results:{}},download:{started:true,finished:true,results:{}},upload:{started:true,finished:true,results:{}}},
  getDownloadBandwidth:()=>35800000,getUploadBandwidth:()=>12500000,getUnloadedLatency:()=>28.4,getUnloadedJitter:()=>null,getTotalDurationMs:()=>19000};}
function fakeEngine(){return{results:result() as unknown as Results,onFinish:()=>{},onError:()=>{},onResultsChange:()=>{},play:vi.fn(),pause:vi.fn()} as Engine;}
afterEach(()=>vi.useRealTimers());
it('pins the adapter version to the installed SDK and disables logging/credentials',()=>{
  const pkg=JSON.parse(readFileSync(new URL('../node_modules/@cloudflare/speedtest/package.json',import.meta.url),'utf8'));expect(pkg.version).toBe(SDK_VERSION);
  const config=mobileProfile(60);expect(config.autoStart).toBe(false);expect(config.logAimApiUrl).toBeNull();expect(config.logMeasurementApiUrl).toBeNull();expect(config.includeCredentials).toBe(false);
  expect(config.measurementTargets).toEqual(['https://speed.cloudflare.com']);
});
it('converts bits/second to Mbps and preserves absent jitter as null',()=>{
  const value=extractMeasurement(result());expect(value.download_mbps).toBe(35.8);expect(value.upload_mbps).toBe(12.5);expect(value.ping_ms).toBe(28.4);expect(value.jitter_ms).toBeNull();
});
it('rejects incomplete, missing, nonfinite and early-aborted results',()=>{
  expect(()=>extractMeasurement({...result(),isFinished:false})).toThrow('finish');
  expect(()=>extractMeasurement({...result(),getDownloadBandwidth:()=>undefined})).toThrow('missing');
  expect(()=>extractMeasurement({...result(),getUploadBandwidth:()=>NaN})).toThrow('invalid');
  expect(()=>extractMeasurement({...result(),raw:{...result().raw,error:'Test aborted'}})).toThrow('finish');
});
it('permits nonfatal SDK warnings only when final results are complete',async()=>{
  const engine=fakeEngine(),test=runTest(()=>engine,60);engine.onError('Temporary request error');engine.onFinish(engine.results);
  expect((await test.promise).raw_summary).toHaveProperty('warning_count',1);expect(engine.play).toHaveBeenCalledOnce();
});
it('cancels without allowing a later finish to become successful',async()=>{
  const engine=fakeEngine(),test=runTest(()=>engine,60);const assertion=expect(test.promise).rejects.toThrow('canceled');test.cancel();engine.onFinish(engine.results);await assertion;expect(engine.pause).toHaveBeenCalledOnce();
});
it('bounds the test duration and pauses the engine on timeout',async()=>{
  vi.useFakeTimers();const engine=fakeEngine(),test=runTest(()=>engine,10),assertion=expect(test.promise).rejects.toThrow('timed out');await vi.advanceTimersByTimeAsync(10100);await assertion;expect(engine.pause).toHaveBeenCalledOnce();
});
