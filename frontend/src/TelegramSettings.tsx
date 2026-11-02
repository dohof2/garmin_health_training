import {useEffect, useState} from 'react';
import {requestJson} from './request';

type Status={enabled:boolean;paired:boolean;bot_username:string|null;last_poll_at:string|null;last_error:string|null;pending:number;ambiguous_replies:number;pairing_pending:boolean;capabilities?:string;credential_access?:'pending'|'ready'|'blocked'};
type Pairing={url:string;expires_at:string};
const localAction={'Content-Type':'application/json','X-Garmin-Local-Action':'telegram-setup'};

export default function TelegramSettings({active,timezone}:{active:boolean;timezone:string}) {
  const [status,setStatus]=useState<Status|null>(null);
  const [pairing,setPairing]=useState<Pairing|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  useEffect(()=>{
    if(!active)return;
    let cancelled=false;
    const refresh=()=>requestJson<Status>('/api/telegram/status').then(s=>{if(!cancelled){setStatus(s);if(s.paired||!s.enabled)setPairing(null);}}).catch(e=>{if(!cancelled)setError(e.message);});
    void refresh();
    const timer=window.setInterval(()=>void refresh(),4000);
    return()=>{cancelled=true;window.clearInterval(timer);};
  },[active]);
  const connect=async()=>{
    setBusy(true);setError('');
    try{
      setPairing(await requestJson<Pairing>('/api/telegram/pairing',{method:'POST',headers:localAction,body:JSON.stringify({timezone})}));
      setStatus(await requestJson<Status>('/api/telegram/status'));
    }catch(e){setError(e instanceof Error?e.message:'Could not connect Telegram.');}
    finally{setBusy(false);}
  };
  const unlink=async()=>{
    setBusy(true);setError('');
    try{setStatus(await requestJson<Status>('/api/telegram/disable',{method:'POST',headers:localAction}));setPairing(null);}
    catch(e){setError(e instanceof Error?e.message:'Could not disable Telegram.');}
    finally{setBusy(false);}
  };
  const retryCredentials=async()=>{
    setBusy(true);setError('');
    try{setStatus(await requestJson<Status>('/api/telegram/retry-credentials',{method:'POST',headers:localAction}));}
    catch(e){setError(e instanceof Error?e.message:'Could not retry credential access.');}
    finally{setBusy(false);}
  };
  return <section id="telegram-settings" hidden={!active} className="settings-panel" aria-labelledby="telegram-title">
    <div className="settings-panel-heading"><div><span>Phone access</span><h3 id="telegram-title">Telegram</h3></div></div>
    <p>Ask questions and log meals through the app’s nutrition chat. Describe what you ate and the amounts; saved meals and calories appear in Nutrition. You can correct a recent food’s gram amount in the same conversation. Uses your selected AI provider.</p>
    <p>Plan and nutrition-target changes, charts, photos and voice still require the browser app.</p>
    <p>Messages and health answers pass through Telegram’s cloud. The Mac must be awake with this app running. Telegram history is saved locally, separately from your browser conversation.</p>
    <p role="status">{!status?'Loading Telegram connection…':status.paired?`Paired with @${status.bot_username}`:status.enabled?'Waiting for private pairing':'Disconnected'}</p>
    {status&&status.capabilities!=='text_questions_and_meal_logging'&&<p role="status">Restart the app to load Telegram meal logging. Your existing pairing will be kept.</p>}
    {status?.last_poll_at&&<p>Last Telegram check: {new Date(status.last_poll_at).toLocaleString()}</p>}
    {status?.last_error&&<p role="alert">{status.last_error}</p>}
    {status?.enabled&&status.credential_access==='blocked'&&<button type="button" disabled={busy} onClick={()=>void retryCredentials()}>Retry credential access</button>}
    {!!status?.ambiguous_replies&&<p role="alert">{status.ambiguous_replies} replies have uncertain delivery. Ask again if a reply did not arrive; they will not be resent automatically.</p>}
    {!status?.paired&&<button type="button" disabled={busy||!status} onClick={()=>void connect()}>{busy?'Connecting…':pairing?'Create a new pairing link':'Connect saved bot'}</button>}
    {status?.enabled&&<button type="button" disabled={busy} onClick={()=>void unlink()}>Disable and unlink</button>}
    {pairing&&<p><a href={pairing.url} target="_blank" rel="noreferrer">Open bot and tap Start to pair your account</a>. This private link expires at {new Date(pairing.expires_at).toLocaleTimeString()}. Keep it private.</p>}
    {error&&<p role="alert">{error}</p>}
  </section>;
}
