import { offline, type OfflineStore } from './offline-store';

export async function recoverInterrupted(owner:number,store:OfflineStore=offline,now=Date.now()){
  for(const attempt of await store.speedAttempts(owner)){
    if(attempt.expiresAt>now)continue;
    await store.finishSpeedAttempt(owner,attempt,{...attempt.base,outcome:'SPEEDTEST_FAILED',measurement:null,
      remarks:`Interrupted speed test; no completed measurements were saved. ${attempt.base.remarks}`.slice(0,4000)});
  }
}
