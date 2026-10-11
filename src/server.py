#!/usr/bin/env python3
"""PROFINET DCP local service UI V1.1.0. Authorized industrial networks only."""
import os
import json
import re
import ipaddress
import uuid
import threading
import time
import socket
import subprocess
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlsplit
from pnio_dcp import DCP

HOST = os.getenv('PNIO_HOST', '10.10.0.1')
PORT = int(os.getenv('PNIO_PORT', '8088'))
IFACE = os.getenv('PNIO_IFACE', 'eth0')
SCAN_TIMEOUT = float(os.getenv('PNIO_SCAN_TIMEOUT', '15'))
lock = threading.Lock()
CACHE_FILE = '/root/profinet_last_scan.json'
cache_guard = threading.Lock()

def read_scan_cache():
    try:
        with cache_guard, open(CACHE_FILE, 'r', encoding='utf-8') as handle:
            data = json.load(handle)
        if isinstance(data, dict) and isinstance(data.get('devices'), list):
            return {'devices': data['devices'], 'scanned_at': data.get('scanned_at')}
    except (OSError, ValueError, TypeError):
        pass
    return {'devices': [], 'scanned_at': None}

def write_scan_cache(devices):
    payload = {'devices': devices, 'scanned_at': int(time.time()) if devices is not None else None}
    tmp = CACHE_FILE + '.tmp'
    with cache_guard:
        with open(tmp, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle)
        os.replace(tmp, CACHE_FILE)

blink_guard = threading.Lock()
blink_state = {"token": None, "mac": None, "stop": None, "until": 0.0, "error": None}

def blink_worker(token, mac, stop):
    try:
        while not stop.is_set():
            with blink_guard:
                if blink_state["token"] != token or time.monotonic() >= blink_state["until"]:
                    break
            with lock:
                DCP(HOST).blink(mac)
            stop.wait(1.0)
    except Exception as exc:
        print(f"Blink error: {exc}", flush=True)
        with blink_guard:
            if blink_state["token"] == token:
                blink_state["error"] = str(exc)
    finally:
        with blink_guard:
            if blink_state["token"] == token:
                blink_state["token"] = None
                blink_state["mac"] = None
                blink_state["stop"] = None


mac_re = re.compile(r'^(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$')
name_re = re.compile(r'^[a-z0-9](?:[a-z0-9.-]{0,238}[a-z0-9])?$')

HTML = r'''<!doctype html>
<html lang="nl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PROFINET Service Tool V1.0.0</title><style>
:root{color-scheme:dark}body{font:16px system-ui,sans-serif;background:#111827;color:#f9fafb;max-width:720px;margin:20px auto;padding:14px}
section{background:#1f2937;padding:18px;border-radius:12px;margin:15px 0}input,select,button{box-sizing:border-box;width:100%;padding:12px;margin:5px 0 12px;border-radius:8px;border:1px solid #64748b;font:inherit}
input,select{background:#111827;color:white}button{background:#2563eb;color:white;cursor:pointer;border:0}button:disabled{opacity:.55;cursor:wait}
label{display:block}small,.muted{color:#aeb8c7}h1{font-size:23px}.status{white-space:pre-wrap;padding:10px 0;min-height:1.5em}.line{display:flex;justify-content:space-between;gap:12px;align-items:center}.clock{font-variant-numeric:tabular-nums;font-size:23px;font-weight:700}
.devices{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px;margin:14px 0}.device-card{background:#111827;border:2px solid #374151;border-radius:10px;padding:13px;cursor:pointer;overflow-wrap:anywhere}.device-card.active{border-color:#38bdf8;background:#172c40}.device-card strong{display:block;font-size:17px;margin-bottom:5px}.device-card small{display:block;line-height:1.65}.track{height:9px;background:#374151;border-radius:9px;overflow:hidden;margin:9px 0}.bar{height:100%;width:0;background:#38bdf8;transition:width .1s linear}.ok{color:#86efac}.bad{color:#fca5a5}
</style></head><body><h1>PROFINET Service Tool <span style="font-size:14px;color:#aeb8c7;font-weight:500">V1.0.0</span></h1><small>GL-E5800 · DCP op lokaal Ethernet · Alleen voor bevoegde service</small>
<section><h3>Netwerkstatus</h3><div class="line"><strong>Internet</strong><span id="internet">Controleren...</span></div><div class="line"><strong>WireGuard VPN</strong><span id="vpn">Controleren...</span></div><small id="vpninfo"></small><hr style="border:0;border-top:1px solid #374151;margin:14px 0"><div class="line"><strong>Ethernet</strong><span id="link">Controleren...</span></div><small id="iface"></small>
<button id="scanbtn" onclick="scan()">Scan Devices</button>
<div class="line"><strong id="scanlabel">Gereed om te scannen</strong><span class="clock" id="clock">0.0 s</span></div>
<div class="track"><div class="bar" id="bar"></div></div><small id="scandetail">Nog geen scan uitgevoerd.</small>
<h3>Gevonden apparaten <span id="devicecount" class="muted">(0)</span></h3><div id="devicecards" class="devices"><small class="muted">Nog geen apparaten gescand.</small></div><label for="device">Geselecteerd apparaat</label><select id="device" onchange="choose()"><option>Geen apparaten gescand</option></select><small id="info"></small></section>
<section><h3>Blink LED</h3><button id="blinkbtn" onclick="toggleBlink()">Start Blink</button><small>Start/Stop zoals PRONETA · automatische stop na maximaal 2 minuten</small><div class="status" id="status" role="status">Gereed. Eerst scannen.</div></section>
<section><h3>Set Name</h3><label for="name">PROFINET Device Name</label><input id="name" autocomplete="off" autocapitalize="none" spellcheck="false"><small>Bij Set Name worden hoofdletters omgezet naar kleine letters.</small><button onclick="writeValue('name')">Set Name</button></section>
<section><h3>Set Network</h3><label for="ip">IP-adres</label><input id="ip" inputmode="decimal"><label for="mask">Subnetmasker</label><input id="mask" inputmode="decimal"><label for="gateway">Gateway (0.0.0.0 indien niet gebruikt)</label><input id="gateway" inputmode="decimal"><button onclick="writeValue('network')">Set Network</button></section>

<script>
let devices=[],busy=false,blinkToken=null;
const $=id=>document.getElementById(id);
async function req(action,data={},signal){const r=await fetch('/api',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,...data}),signal});let j;try{j=await r.json()}catch(e){throw Error('Ongeldig antwoord van webserver (HTTP '+r.status+')')}if(!r.ok)throw Error(j.error||'HTTP '+r.status);return j}
async function restoreDevices(){
 try {
  const response=await fetch('/devices',{cache:'no-store'});
  if(!response.ok)throw Error('HTTP '+response.status);
  const saved=await response.json();
  devices=Array.isArray(saved.devices)?saved.devices:[];
  $('device').replaceChildren();
  for(const d of devices){const o=document.createElement('option');o.textContent=(d.name||'(naamloos)')+' · '+(d.ip||'-')+' · '+d.mac;$('device').append(o)}
  if(devices.length){choose();$('scanlabel').textContent='Laatste scan (bewaard)';$('scandetail').textContent=devices.length+' apparaten · controleer bereikbaarheid voor wijzigen';}
  else{$('device').innerHTML='<option>Geen apparaten gevonden</option>';renderDevices()}
 }catch(e){$('scandetail').textContent='Laatste scan laden mislukt: '+e.message}
}
function chosen(){return devices[$('device').selectedIndex]}
function renderDevices(){let cards=$('devicecards');cards.replaceChildren();$('devicecount').textContent='('+devices.length+')';if(!devices.length){let msg=document.createElement('small');msg.className='muted';msg.textContent='Geen apparaten gevonden.';cards.append(msg);return}devices.forEach((d,i)=>{let card=document.createElement('div');card.className='device-card'+(i===$('device').selectedIndex?' active':'');card.setAttribute('role','button');card.tabIndex=0;let title=document.createElement('strong');title.textContent=d.name||'(naamloos)';card.append(title);for(let value of ['Type: '+(d.family||'Onbekend'),'IP: '+(d.ip||'-'),'MAC: '+d.mac]){let line=document.createElement('small');line.textContent=value;card.append(line)}card.onclick=()=>selectDevice(i);card.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();selectDevice(i)}};cards.append(card)})}
function selectDevice(i){if(blinkToken){$('status').textContent='Stop eerst Blink voordat je een ander apparaat kiest.';return}$('device').selectedIndex=i;choose()}
function choose(){if(blinkToken){$('status').textContent='Stop eerst Blink voordat je een ander apparaat kiest.';return}let d=chosen();if(!d)return;$('name').value=d.name||'';$('ip').value=d.ip||'';$('mask').value=d.mask||'';$('gateway').value=d.gateway||'';$('info').textContent=d.mac+' · '+(d.family||'');renderDevices()}
async function refreshLink(){try{let r=await fetch('/health',{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);let j=await r.json();$('link').textContent=j.ethernet_connected?'Verbonden':'Geen kabel / geen link';$('link').className=j.ethernet_connected?'ok':'bad';$('iface').textContent='Interface: '+j.interface+' · '+(j.ethernet_connected?'Link actief':'Link niet actief');$('internet').textContent=j.internet_online?'Online':'Offline / onbekend';$('internet').className=j.internet_online?'ok':'bad';$('vpn').textContent=j.vpn_connected?'Verbonden':(j.vpn_configured?'Niet verbonden':'Niet ingesteld / niet actief');$('vpn').className=j.vpn_connected?'ok':'bad';$('vpninfo').textContent=j.vpn_interface?('Interface: '+j.vpn_interface+(j.vpn_handshake_age_s!==null?' · handshake '+j.vpn_handshake_age_s+' s geleden':'')):''}catch(e){$('link').textContent='Status onbekend';$('link').className='bad';$('internet').textContent='Onbekend';$('vpn').textContent='Onbekend'}}
async function scan(){if(busy||blinkToken){$('status').textContent='Stop eerst Blink voordat je opnieuw scant.';return}busy=true;$('scanbtn').disabled=true;devices=[];$('device').innerHTML='<option>Scannen...</option>';$('devicecards').replaceChildren();$('devicecount').textContent='(0)';$('info').textContent='';$('scanlabel').textContent='Scannen...';$('scandetail').textContent='Zoeken naar PROFINET-apparaten';$('status').textContent='DCP Identify gestart';$('bar').style.width='0%';
const start=performance.now(),timeout=15000,controller=new AbortController();let deadline=setTimeout(()=>controller.abort(),timeout);let ticker=setInterval(()=>{let s=(performance.now()-start)/1000;$('clock').textContent=s.toFixed(1)+' s';$('bar').style.width=Math.min(100,s/(timeout/1000)*100)+'%'},100);
try{let r=await req('scan',{},controller.signal);devices=r.devices||[];$('device').innerHTML='';for(let d of devices){let o=document.createElement('option');o.textContent=(d.name||'(naamloos)')+' · '+(d.ip||'-')+' · '+d.mac;$('device').append(o)}if(!devices.length){$('device').innerHTML='<option>Geen apparaten gevonden</option>';$('info').textContent='';renderDevices()}else choose();$('scanlabel').textContent='Scan voltooid';$('scandetail').textContent=devices.length+' apparaat/apparaten gevonden';$('status').textContent='Scan succesvol afgerond'}
catch(e){$('scanlabel').textContent='Scan mislukt';$('scandetail').textContent=e.name==='AbortError'?'Timeout na 15 seconden':('Fout: '+e.message);$('device').innerHTML='<option>Geen scanresultaten</option>';renderDevices();$('status').textContent=$('scandetail').textContent}
finally{clearTimeout(deadline);clearInterval(ticker);let s=(performance.now()-start)/1000;$('clock').textContent=s.toFixed(1)+' s';$('bar').style.width=Math.min(100,s/(timeout/1000)*100)+'%';$('scanbtn').disabled=false;busy=false;refreshLink()}}
async function toggleBlink(){
 if(blinkToken){let token=blinkToken;try{let r=await req('blink_stop',{token});$('status').textContent=r.message}catch(e){$('status').textContent='Stop mislukt: '+e.message}finally{blinkToken=null;$('blinkbtn').textContent='Start Blink'}return}
 if(busy){$('status').textContent='Wacht tot de scan klaar is';return}
 let d=chosen();if(!d){$('status').textContent='Scan en selecteer eerst een apparaat';return}
 try{let r=await req('blink_start',{mac:d.mac});blinkToken=r.token;$('blinkbtn').textContent='Stop Blink';$('status').textContent='Blink actief voor '+d.name+' ('+d.mac+')'}catch(e){$('status').textContent='Blink fout: '+e.message}
}
async function pollBlink(){if(!blinkToken)return;try{let r=await fetch('/blink_status',{cache:'no-store'});let j=await r.json();if(!j.active||j.token!==blinkToken){blinkToken=null;$('blinkbtn').textContent='Start Blink';$('status').textContent=j.error?'Blink fout: '+j.error:'Blink gestopt'}}catch(e){}}
function normalizeProfinetName(value){
 let name=value.trim().toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g,'');
 name=name.replace(/[^a-z0-9.-]+/g,'-').replace(/-+/g,'-');
 name=name.split('.').map(part=>part.replace(/^-+|-+$/g,'')).filter(Boolean).join('.');
 return name;
}
async function writeValue(action){if(busy||blinkToken){$('status').textContent='Stop eerst Blink of wacht op de scan';return}let d=chosen();if(!d){alert('Scan en selecteer eerst een apparaat');return}let data={mac:d.mac};if(action==='name'){data.name=normalizeProfinetName($('name').value);if(!data.name||data.name.length>240||data.name.split('.').some(x=>x.length>63)||!/^[a-z]/.test(data.name)||/^port-[0-9]{3}(?:$|[-.])/.test(data.name)||/^\d{1,3}(?:\.\d{1,3}){3}$/.test(data.name)){$('status').textContent='Naam kan niet automatisch naar een geldige PROFINET-naam worden omgezet. Controleer beginletter, lengte en gereserveerde namen.';return;}$('name').value=data.name;}if(action==='network')Object.assign(data,{ip:$('ip').value.trim(),mask:$('mask').value.trim(),gateway:$('gateway').value.trim()});let summary=action==='name'?'Naam: '+data.name:`IP: ${data.ip}\nMask: ${data.mask}\nGateway: ${data.gateway}`;if(!confirm('Apparaat: '+d.mac+'\n'+summary+'\n\nDoorgaan?'))return;$('status').textContent='Uitvoeren...';try{let r=await req(action,data);$('status').textContent=r.message+'\nScan opnieuw om instellingen te controleren.'}catch(e){$('status').textContent='Fout: '+e.message}}
restoreDevices();refreshLink();setInterval(refreshLink,5000);setInterval(pollBlink,1000);
</script></body></html>'''

def validate_network(data):
    ip = ipaddress.IPv4Address(data['ip'])
    mask = ipaddress.IPv4Address(data['mask'])
    gw = ipaddress.IPv4Address(data['gateway'])
    net = ipaddress.IPv4Network(f'{ip}/{mask}', strict=False)
    if ip.is_multicast or ip.is_unspecified or ip.is_loopback or ip not in net.hosts():
        raise ValueError('Ongeldig host-IP')
    if int(gw) and (gw not in net or gw in (net.network_address, net.broadcast_address)):
        raise ValueError('Gateway moet binnen subnet vallen (of 0.0.0.0)')
    return [str(ip), str(mask), str(gw)]

def ethernet_connected():
    try:
        with open(f'/sys/class/net/{IFACE}/carrier', encoding='ascii') as f:
            return f.read().strip() == '1'
    except (OSError, ValueError):
        return False

# Statuscontroles met cache: voorkom dat elke browserpoll een nieuwe netwerkcheck start.
_health_lock = threading.Lock()
_health_cache = {'at': 0.0, 'data': {}}

def network_health():
    now = time.monotonic()
    with _health_lock:
        if now - _health_cache['at'] < 4:
            return dict(_health_cache['data'])
        online = False
        try:
            # Een TCP-verbinding test bereikbaarheid zonder ICMP-afhankelijkheid.
            with socket.create_connection(('1.1.1.1', 443), timeout=1.2):
                online = True
        except OSError:
            pass
        vpn_configured = False
        vpn_connected = False
        vpn_interface = ''
        age = None
        try:
            result = subprocess.run(['wg', 'show', 'all', 'latest-handshakes'],
                                    capture_output=True, text=True, timeout=1.5, check=False)
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    fields = line.split()
                    if len(fields) < 3:
                        continue
                    vpn_configured = True
                    iface, _, stamp = fields[:3]
                    if not vpn_interface:
                        vpn_interface = iface
                    try:
                        ts = int(stamp)
                        if ts > 0:
                            seconds = max(0, int(time.time()) - ts)
                            if age is None or seconds < age:
                                age, vpn_interface = seconds, iface
                            if seconds <= 180:
                                vpn_connected = True
                    except ValueError:
                        continue
        except (OSError, subprocess.TimeoutExpired):
            pass
        data = {'interface': IFACE, 'ethernet_connected': ethernet_connected(),
                'internet_online': online, 'vpn_configured': vpn_configured,
                'vpn_connected': vpn_connected, 'vpn_interface': vpn_interface,
                'vpn_handshake_age_s': age}
        _health_cache.update(at=time.monotonic(), data=data)
        return dict(data)

class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, data, ctype='application/json'):
        raw = data.encode() if isinstance(data, str) else json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', ctype + '; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/':
            self.send_json(200, HTML, 'text/html')
        elif path == '/devices':
            self.send_json(200, read_scan_cache())
        elif path == '/health':
            self.send_json(200, network_health())
        elif path == '/blink_status':
            with blink_guard:
                self.send_json(200, {'active': blink_state['token'] is not None, 'token': blink_state['token'], 'error': blink_state['error']})
        else:
            self.send_json(404, {'error': 'Niet gevonden'})

    def do_POST(self):
        if urlsplit(self.path).path != '/api':
            return self.send_json(404, {'error': 'Niet gevonden'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length < 1 or length > 4096:
                raise ValueError('Ongeldige aanvraaglengte')
            data = json.loads(self.rfile.read(length))
            action = data.get('action')
            if action not in ('scan', 'name', 'network', 'blink_start', 'blink_stop'):
                raise ValueError('Onbekende actie')
            if action == 'blink_stop':
                token = data.get('token')
                with blink_guard:
                    if token != blink_state['token'] or not token:
                        raise ValueError('Blink sessie niet meer actief')
                    blink_state['stop'].set()
                    blink_state['token'] = None
                    blink_state['mac'] = None
                return self.send_json(200, {'message': 'Blink gestopt; apparaat stopt volgens eigen LED-timer'})
            if action == 'blink_start':
                mac = data.get('mac', '')
                if not mac_re.fullmatch(mac):
                    raise ValueError('Ongeldig MAC-adres')
                with blink_guard:
                    if blink_state['token'] is not None:
                        raise ValueError('Er is al een Blink-sessie actief')
                    token = uuid.uuid4().hex
                    stop = threading.Event()
                    blink_state.update(token=token, mac=mac, stop=stop, until=time.monotonic()+120, error=None)
                threading.Thread(target=blink_worker, args=(token, mac, stop), daemon=True).start()
                return self.send_json(200, {'token': token, 'message': 'Blink gestart'})
            with lock:
                dcp = DCP(HOST)
                if action == 'scan':
                    write_scan_cache([])  # Old results disappear when a NEW scan begins.
                    started = time.monotonic()
                    devices = [{'mac': d.MAC, 'name': d.name_of_station, 'ip': d.IP,
                                'mask': d.netmask, 'gateway': d.gateway, 'family': d.family}
                               for d in dcp.identify_all()]
                    write_scan_cache(devices)
                    print(f'DCP scan completed in {time.monotonic()-started:.2f}s: {len(devices)} devices', flush=True)
                    return self.send_json(200, {'devices': devices})
                mac = data.get('mac', '')
                if not mac_re.fullmatch(mac):
                    raise ValueError('Ongeldig MAC-adres')
                if action == 'name':
                    name = data.get('name', '').strip().lower()
                    if (len(name) > 240 or not name_re.fullmatch(name) or not name[0].isalpha() or any(not x or len(x) > 63 or x.startswith('-') or x.endswith('-') for x in name.split('.')) or re.match(r'^port-[0-9]{3}(?:$|[-.])', name) or re.fullmatch(r'(?:[0-9]{1,3}\.){3}[0-9]{1,3}', name)):
                        raise ValueError('Ongeldige PROFINET-naam')
                    result = dcp.set_name_of_station(mac, name)
                elif action == 'network':
                    result = dcp.set_ip_address(mac, validate_network(data))
            self.send_json(200, {'message': f'{action}: opdracht uitgevoerd; antwoord: {result!s}'})
        except Exception as exc:
            print(f'DCP request error: {exc}', flush=True)
            try:
                self.send_json(400, {'error': str(exc)})
            except (BrokenPipeError, ConnectionResetError):
                pass

if __name__ == '__main__':
    print(f'PROFINET UI: http://{HOST}:{PORT} (HTTP; trusted LAN only)', flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
