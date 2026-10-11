#!/usr/bin/env python3
"""GL-E5800 PROFINET service touchscreen V1.1.4, built for GL-E5800 RGB565 framebuffer.
Preview: python3 dashboard.py --preview /tmp/profinet-preview.png
Live: managed by the existing citydash run.sh/toggle.sh; do not run alongside gl_screen.
"""
import json, os, signal, struct, sys, threading, time, urllib.request, subprocess, re, ipaddress, unicodedata, traceback
from PIL import Image, ImageDraw, ImageFont

W,H=240,320
FB='/dev/fb0'; TOUCH='/dev/input/event0'; API='http://' + (open('/etc/profinet-service-host').read().strip() if os.path.exists('/etc/profinet-service-host') else '10.10.0.1') + ':8088'
SWITCH_REQUEST_FILE='/tmp/dashboard_ui_switch_request'
BG=(11,18,32); PANEL=(27,39,58); FG=(234,240,248); DIM=(148,164,185)
BLUE=(55,158,235); GREEN=(55,199,132); RED=(235,96,98)
FONT_DIR='/etc/gl_screen/language/ttf'
stop=False; view='home'; devices=[]; selected=0; page=0; blink_token=None; busy=False; message=''; health={}; scan_started=0
lock=threading.Lock(); framebuffer=None; last_touch=None; switch_confirm=False
fields={}; keyboard_mode='abc'; edit_field=''; edit_value=''; edit_origin=''; confirm_action=''; confirm_data={}; confirm_lines=[]
LOG='/tmp/profinet_touchscreen.log'

def log_event(message):
    try:
        with open(LOG,'a',encoding='utf-8') as out:
            out.write(time.strftime('%Y-%m-%d %H:%M:%S ')+str(message)+'\n')
    except OSError:pass

def f(size=15):
    for name in ('default_medium','default','DejaVuSans'):
        p=f'{FONT_DIR}/{name}.ttf'
        if os.path.isfile(p):
            try:return ImageFont.truetype(p,size)
            except Exception:pass
    return ImageFont.load_default()

def text(d,xy,s,size=15,color=FG):
    d.text(xy,str(s),font=f(size),fill=color)

def button(d,rect,label,color=PANEL):
    # Narrow keyboard keys need a smaller corner radius (Pillow constraint).
    key_width = rect[2] - rect[0]
    key_height = rect[3] - rect[1]
    radius = max(0, min(10, (key_width - 1) // 2, (key_height - 1) // 2))
    # GL-E5800 Pillow can reject rounded corners on narrow keys.
    # Use plain rectangles for narrow keyboard keys, with a safe fallback.
    if key_width < 34:
        d.rectangle(rect, fill=color)
    else:
        try:
            d.rounded_rectangle(rect,radius=radius,fill=color)
        except ValueError:
            d.rectangle(rect,fill=color)
    font=f(16); bb=d.textbbox((0,0),label,font=font)
    x=(rect[0]+rect[2]-(bb[2]-bb[0]))/2
    y=(rect[1]+rect[3]-(bb[3]-bb[1]))/2-bb[1]
    d.text((x,y),label,font=font,fill=FG)

def shorten(s,n=25):
    s=str(s or '-')
    return s if len(s)<=n else s[:n-1]+'…'

def render():
    with lock:
        v=view; ds=list(devices); idx=selected; pg=page; token=blink_token; b=busy; msg=message; h=dict(health); started=scan_started
    img=Image.new('RGB',(W,H),BG); d=ImageDraw.Draw(img)
    d.rectangle((0,0,W,45),fill=(18,29,47))
    text(d,(12,11),'PROFINET SERVICE',16)
    text(d,(180,29),'V1.1.4',10,DIM)
    if v!='home':
        button(d,(8,51,68,83),'BACK')
        text(d,(78,57),{'profinet':'PROFINET','network':'NETWORK','vpn':'WIREGUARD','system':'SYSTEM','devices':'DEVICES','device':'DEVICE','name':'SET NAME','network_edit':'SET IP','keyboard':'EDIT VALUE','confirm':'CONFIRM'}.get(v,v),15,BLUE)
    if v=='home':
        button(d,(10,65,230,125),'PROFINET',BLUE)
        button(d,(10,135,230,185),'NETWORK')
        button(d,(10,195,230,245),'WIREGUARD')
        button(d,(10,255,230,305),'SYSTEM')
    elif v=='profinet':
        button(d,(12,101,228,160),'SCAN DEVICES',BLUE if not b else PANEL)
        text(d,(18,177),'Scanning...' if b else f'{len(ds)} device(s) (last scan)',14)
        if b: text(d,(18,204),f'{time.monotonic()-started:.1f} s',19,BLUE)
        button(d,(12,244,228,297),'VIEW DEVICES')
    elif v=='devices':
        if not ds:text(d,(15,115),'No devices. Run scan first.',13,DIM)
        for i,dev in enumerate(ds[pg*4:pg*4+4]):
            y=94+i*43
            button(d,(8,y,232,y+37),shorten(dev.get('name') or dev.get('ip') or dev.get('mac'),23),PANEL)
        if len(ds)>4:
            button(d,(8,274,110,309),'PREV')
            button(d,(130,274,232,309),'NEXT')
            text(d,(112,282),str(pg+1),12,DIM)
    elif v=='device':
        if ds and idx<len(ds):
            dev=ds[idx]
            text(d,(10,103),shorten(dev.get('name'),28),15)
            text(d,(10,135),'IP: '+shorten(dev.get('ip'),24),13,DIM)
            text(d,(10,162),'MAC: '+shorten(dev.get('mac'),22),12,DIM)
            button(d,(12,186,228,228),'STOP BLINK' if token else 'START BLINK',RED if token else BLUE)
            button(d,(12,235,113,287),'SET NAME')
            button(d,(126,235,228,287),'SET IP')
        else:text(d,(12,108),'No device selected',14)
    elif v=='name':
        text(d,(12,97),'PROFINET Device Name',13,DIM)
        button(d,(10,122,230,170),shorten(fields.get('name',''),24))
        text(d,(12,185),'Converted on SEND',12,DIM)
        button(d,(10,238,230,294),'SET NAME',BLUE)
    elif v=='network_edit':
        for i,(key,label) in enumerate((('ip','IP ADDRESS'),('mask','SUBNET MASK'),('gateway','GATEWAY'))):
            y=92+i*58
            text(d,(12,y),label,11,DIM)
            button(d,(10,y+15,230,y+51),fields.get(key,'0.0.0.0'))
        button(d,(10,274,230,312),'SET NETWORK',BLUE)
    elif v=='keyboard':
        text(d,(9,90),edit_field.upper(),12,DIM)
        d.rounded_rectangle((7,109,233,145),radius=5,fill=PANEL)
        text(d,(11,117),shorten(edit_value,29),14)
        if edit_field=='name':
            keys = (list('abcdefghijklmnopqrstuvwxy') if keyboard_mode=='abc'
                    else list('z0123456789.-_@'))
            for j,ch in enumerate(keys):
                col=j%5; row_i=j//5
                x=5+col*47; y=150+row_i*25
                button(d,(x,y,x+43,y+23),ch)
            button(d,(5,278,78,315),'ABC' if keyboard_mode=='123' else '123',BLUE)
            button(d,(82,278,155,315),'DEL')
            button(d,(159,278,235,315),'DONE',GREEN)
            text(d,(8,136),'BACK: cancel  |  123: more',10,DIM)
        else:
            rows=('123','456','789','.0<')
            for row_i,keys in enumerate(rows):
                n=len(keys); width=232/n; y=153+row_i*31
                for j,ch in enumerate(keys):
                    x=4+j*width
                    button(d,(int(x),y,int(x+width-2),y+28),ch)
            button(d,(5,280,78,315),'DEL')
            button(d,(82,280,155,315),'CANCEL')
            button(d,(159,280,235,315),'DONE',BLUE)
    elif v=='confirm':
        text(d,(12,94),'Write to device?',17)
        for i,line in enumerate(confirm_lines[:5]):
            text(d,(10,125+i*26),shorten(line,31),12,DIM)
        button(d,(8,255,113,307),'CANCEL')
        button(d,(125,255,232,307),'WRITE',RED)
    elif v in ('network','vpn','system'):
        rows=({'network':[('Internet', 'ONLINE' if h.get('internet_online') else 'OFFLINE'),('Ethernet','LINK' if h.get('ethernet_connected') else 'NO LINK'),('Interface',h.get('interface','-'))],
               'vpn':[('WireGuard','CONNECTED' if h.get('vpn_connected') else 'NOT CONNECTED'),('Interface',h.get('vpn_interface','-')),('Handshake',str(h.get('vpn_handshake_age_s') or '-')+' s')],
               'system':[('PROFINET API','ONLINE' if h else 'OFFLINE'),('Service IP',API.split('/')[2].split(':')[0]),('Web UI',API.split('//')[1])]})[v]
        for i,(label,value) in enumerate(rows):
            y=104+i*64; text(d,(12,y),label,13,DIM);text(d,(12,y+20),shorten(value,27),17)
    if switch_confirm:
        d.rectangle((7,80,233,250),fill=(36,49,67),outline=BLUE,width=2)
        text(d,(25,101),'GL.iNet dashboard?',17)
        text(d,(23,138),'Terug naar origineel?',13,DIM)
        button(d,(18,184,110,231),'CANCEL')
        button(d,(128,184,222,231),'SWITCH',BLUE)
    if msg and not switch_confirm:
        d.rectangle((0,300,240,320),fill=(30,49,69))
        text(d,(8,303),shorten(msg,34),11)
    return img

def rgb565(img):
    raw=img.tobytes(); out=bytearray(W*H*2)
    for i in range(0,len(raw),3):
        r,g,b=raw[i:i+3]; val=((r>>3)<<11)|((g>>2)<<5)|(b>>3)
        j=(i//3)*2;out[j]=val&255;out[j+1]=val>>8
    return out

def draw_live(img):
    global framebuffer
    if framebuffer is None: framebuffer=open(FB,'r+b',buffering=0)
    framebuffer.seek(0); framebuffer.write(rgb565(img))

def api(path,action=None,data=None,timeout=16):
    payload=None if action is None else json.dumps(dict({'action':action},**(data or {}))).encode()
    req=urllib.request.Request(API+path,data=payload,headers={'Content-Type':'application/json'} if payload else {})
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.load(r)

def refresh_health():
    global health
    try:
        result=api('/health',timeout=4)
        with lock:health=result
    except Exception:pass

def restore_devices():
    global devices, message
    try:
        saved=api('/devices',timeout=5)
        latest=saved.get('devices',[])
        if isinstance(latest,list):
            with lock:
                devices=latest
                message=f'{len(latest)} saved device(s)' if latest else ''
    except Exception as exc:
        log_event('Last scan restore failed: '+str(exc))

def do_scan():
    global devices,busy,message,scan_started,page
    with lock:busy=True;devices=[];page=0;message='Scanning Ethernet...';scan_started=time.monotonic()
    try:
        result=api('/api','scan',timeout=18)
        with lock:devices=result.get('devices',[]);message=f'{len(devices)} device(s) found'
    except Exception as e:
        with lock:message='Scan failed: '+str(e)[:18]
    finally:
        with lock:busy=False

def do_blink(mac):
    global busy,message,blink_token
    with lock:
        if busy:return
        busy=True
        current=blink_token
        message='Stopping blink...' if current else 'Starting blink...'
    try:
        if current:
            result=api('/api','blink_stop',{'token':current},timeout=8)
            with lock:blink_token=None;message='Blink stopped'
        else:
            result=api('/api','blink_start',{'mac':mac},timeout=8)
            with lock:blink_token=result['token'];message='Blink active (max 120s)'
    except Exception as e:
        with lock:message='Blink error: '+str(e)[:25]
    finally:
        with lock:busy=False

def poll_blink():
    global blink_token,message
    with lock:token=blink_token
    if not token:return
    try:
        result=api('/blink_status',timeout=3)
        if not result.get('active') or result.get('token')!=token:
            with lock:
                if blink_token==token:
                    blink_token=None;message='Blink finished'
    except Exception:pass

def normalize_name(value):
    value=unicodedata.normalize('NFKD',value.strip().lower())
    value=''.join(c for c in value if not unicodedata.combining(c))
    value=re.sub(r'[^a-z0-9.-]+','-',value)
    value=re.sub(r'-+','-',value)
    return '.'.join(x for x in (part.strip('-') for part in value.split('.')) if x)

def check_name(value):
    if not value or len(value)>240 or not re.fullmatch(r'[a-z0-9.-]+',value):return False
    parts=value.split('.')
    return (value[0].isalpha() and all(0<len(p)<=63 and not p.startswith('-') and not p.endswith('-') for p in parts)
            and not re.match(r'^port-[0-9]{3}(?:$|[-.])',value)
            and not re.fullmatch(r'(?:[0-9]{1,3}\.){3}[0-9]{1,3}',value))

def prepare_write(action):
    global view,confirm_action,confirm_data,confirm_lines,message
    with lock:
        if not devices or selected>=len(devices):return
        mac=devices[selected].get('mac','')
        if action=='name':
            name=normalize_name(fields.get('name',''))
            if not check_name(name):message='Invalid PROFINET name';return
            fields['name']=name
            data={'mac':mac,'name':name}
            lines=['MAC: '+mac,'Name: '+name]
        else:
            data={'mac':mac,**{k:fields.get(k,'').strip() for k in ('ip','mask','gateway')}}
            try:
                ip=ipaddress.IPv4Address(data['ip']); mask=ipaddress.IPv4Address(data['mask']); gw=ipaddress.IPv4Address(data['gateway'])
                net=ipaddress.IPv4Network(f'{ip}/{mask}',strict=False)
                if ip not in net.hosts() or (int(gw) and (gw not in net or gw in (net.network_address,net.broadcast_address))):raise ValueError()
            except (ValueError,ipaddress.AddressValueError):message='Invalid IP / mask / gateway';return
            lines=['MAC: '+mac,'IP: '+data['ip'],'Mask: '+data['mask'],'GW: '+data['gateway']]
        confirm_action=action;confirm_data=data;confirm_lines=lines;view='confirm'

def do_write(action,data):
    global busy,message,view
    with lock:busy=True;message='Writing...'
    try:
        result=api('/api',action,data,timeout=12)
        with lock:message='Write OK - rescan';view='device'
    except Exception as e:
        with lock:message='Write error: '+str(e)[:24];view='device'
    finally:
        with lock:busy=False

def tap(x,y):
    global view,selected,message,page,switch_confirm,edit_field,edit_value,edit_origin,fields,keyboard_mode
    if not (0 <= x < W and 0 <= y < H):
        log_event(f'Ignored out-of-range touch: x={x}, y={y}')
        return
    with lock:
        if switch_confirm:
            if 184<=y<=235:
                if x>=120:
                    switch_confirm=False
                    threading.Thread(target=lambda: subprocess.run(['/root/dashboard/toggle.sh','off']),daemon=True).start()
                else:
                    switch_confirm=False
            return
        if busy:return
        v=view
        if blink_token and not (v=='device' and 186<=y<=228):
            message='Stop blink first';return
        if v!='home' and y<88:
            if v=='keyboard':view=edit_origin
            elif v=='confirm':view='name' if confirm_action=='name' else 'network_edit'
            elif v in ('name','network_edit'):view='device'
            else:view='profinet' if v in ('devices','device') else 'home'
            return
        if v=='home':
            if 65<=y<=125:
                view='profinet'
                threading.Thread(target=restore_devices,daemon=True).start()
            elif 135<=y<=185:view='network'
            elif 195<=y<=245:view='vpn'
            elif 255<=y<=305:view='system'
        elif v=='profinet':
            if 101<=y<=160:threading.Thread(target=do_scan,daemon=True).start()
            elif 244<=y<=297:view='devices'
        elif v=='devices':
            if 274<=y<=309 and len(devices)>4:
                if x<120:page=max(0,page-1)
                else:page=min((len(devices)-1)//4,page+1)
            elif 94<=y<266:
                n=page*4+(y-94)//43
                if n<len(devices):selected=n;view='device'
        elif v=='device' and selected<len(devices):
            if 186<=y<=228:
                mac=devices[selected].get('mac')
                if mac:threading.Thread(target=do_blink,args=(mac,),daemon=True).start()
            elif 235<=y<=287:
                d=devices[selected]
                fields={'name':d.get('name') or '', 'ip':d.get('ip') or '0.0.0.0',
                        'mask':d.get('mask') or '255.255.255.0', 'gateway':d.get('gateway') or '0.0.0.0'}
                view='name' if x<120 else 'network_edit'
        elif v=='name':
            if 122<=y<=170:
                edit_field='name';edit_value=fields.get('name','');edit_origin='name';keyboard_mode='abc';view='keyboard'
                log_event(f'Name keyboard opened at x={x}, y={y}')
            elif 238<=y<=294:
                threading.Thread(target=prepare_write,args=('name',),daemon=True).start()
        elif v=='network_edit':
            if 274<=y<=312:
                threading.Thread(target=prepare_write,args=('network',),daemon=True).start()
            elif 92<=y<266:
                row=(y-92)//58
                if row<3 and y>=92+row*58+15:
                    edit_field=('ip','mask','gateway')[row];edit_value=fields[edit_field];edit_origin='network_edit';view='keyboard'
        elif v=='keyboard':
            if edit_field=='name':
                if 278<=y<=315:
                    if x<80:keyboard_mode='123' if keyboard_mode=='abc' else 'abc'
                    elif x<158:edit_value=edit_value[:-1]
                    else:fields[edit_field]=edit_value;view=edit_origin
                elif 150<=y<275:
                    row=(y-150)//25; col=(x-5)//47
                    if 0<=col<5:
                        keys=(list('abcdefghijklmnopqrstuvwxy') if keyboard_mode=='abc'
                              else list('z0123456789.-_@'))
                        i=row*5+col
                        if i<len(keys) and len(edit_value)<240:edit_value+=keys[i]
            else:
                if 280<=y<=315:
                    if x<80:edit_value=edit_value[:-1]
                    elif x<158:view=edit_origin
                    else:fields[edit_field]=edit_value;view=edit_origin
                elif 153<=y<277:
                    rows=('123','456','789','.0<')
                    row=(y-153)//31
                    if row<len(rows):
                        keys=rows[row];col=min(len(keys)-1,int((x-4)/(232/len(keys))))
                        if 0<=col<len(keys):
                            ch=keys[col]
                            if ch=='<':edit_value=edit_value[:-1]
                            elif len(edit_value)<240:edit_value+=ch
        elif v=='confirm' and 255<=y<=307:
            if x<120:view='name' if confirm_action=='name' else 'network_edit'
            else:
                action=confirm_action;data=dict(confirm_data)
                view='device'
                threading.Thread(target=do_write,args=(action,data),daemon=True).start()

def touch_loop():
    # Linux input_event: timestamp (2 longs), type, code, value.
    # Process a complete contact at release and ignore incomplete coordinates.
    fmt='qqHHi'; size=struct.calcsize(fmt)
    x=y=None; active=False; slot=0; down_at=0
    try:
        with open(TOUCH,'rb',buffering=0) as dev:
            while not stop:
                data=dev.read(size)
                if len(data)!=size:continue
                _,_,typ,code,val=struct.unpack(fmt,data)
                if typ!=3:continue
                if code==47:
                    slot=val
                    continue
                if slot!=0:continue
                if code==57:
                    if val==-1:
                        if active and x is not None and y is not None:
                            try:tap(x,y)
                            except Exception:
                                log_event('Touch handler error: '+traceback.format_exc())
                        active=False;x=y=None
                    else:
                        active=True;x=y=None;down_at=time.monotonic()
                elif active and code==53:x=val
                elif active and code==54:y=val
    except Exception:
        log_event('Touch loop stopped: '+traceback.format_exc())
        print('Touch error; see '+LOG,file=sys.stderr)

def sig(*_):
    global stop
    stop=True

def main():
    if len(sys.argv)>1 and sys.argv[1]=='--preview':
        path=sys.argv[2] if len(sys.argv)>2 else '/tmp/profinet-preview.png'
        render().save(path);print('Preview:',path);return
    signal.signal(signal.SIGTERM,sig);signal.signal(signal.SIGINT,sig)
    log_event('PROFINET touchscreen V1.1.4 starting')
    restore_devices()
    threading.Thread(target=touch_loop,daemon=True).start()
    last_health=0;last_blink=0;last_switch_check=0
    while not stop:
        if time.monotonic()-last_switch_check>0.3:
            last_switch_check=time.monotonic()
            if os.path.exists(SWITCH_REQUEST_FILE):
                try:os.unlink(SWITCH_REQUEST_FILE)
                except OSError:pass
                with lock:
                    global switch_confirm
                    switch_confirm=True
        if time.monotonic()-last_health>5:
            threading.Thread(target=refresh_health,daemon=True).start();last_health=time.monotonic()
        if time.monotonic()-last_blink>2:
            threading.Thread(target=poll_blink,daemon=True).start();last_blink=time.monotonic()
        try:
            draw_live(render())
        except Exception:
            log_event('Render error: '+traceback.format_exc())
            raise
        time.sleep(.15)
    if framebuffer:framebuffer.close()

if __name__=='__main__':main()
