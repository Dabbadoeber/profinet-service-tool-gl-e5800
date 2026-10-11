#!/bin/sh
set -eu
cd "$(dirname "$0")"
[ "$(id -u)" = 0 ] || { echo 'Run as root'; exit 1; }
[ -e /dev/fb0 ] && [ -e /dev/input/event0 ] || { echo 'GL-E5800 touchscreen not found'; exit 1; }
command -v opkg >/dev/null || { echo 'OpenWrt opkg required'; exit 1; }
[ -e /etc/init.d/gl_screen ] || { echo 'Stock GL.iNet screen service missing'; exit 1; }
echo 'PROFINET Service Tool installer (GL-E5800)'
echo 'Use on authorized industrial networks only.'
for existing in /root/dashboard/dashboard.py /root/mudi_profinet.py /etc/init.d/profinet /etc/init.d/citydash /etc/init.d/homebutton; do
    [ ! -e "$existing" ] || { echo "Existing installation: $existing"; echo 'Installer refuses to overwrite existing files. Back up and use a clean test device.'; exit 1; }
done
printf 'LAN IP of router [10.10.0.1]: '; read host || true
host=${host:-10.10.0.1}
case "$host" in *[!0-9.]*|'') echo 'Invalid IPv4 address'; exit 1;; esac
printf 'PROFINET Ethernet interface [eth0]: '; read iface || true
iface=${iface:-eth0}
case "$iface" in *[!a-zA-Z0-9_.:-]*|'') echo 'Invalid interface name'; exit 1;; esac
[ -d "/sys/class/net/$iface" ] || { echo "Interface $iface not found"; exit 1; }
echo 'Installing Python dependencies via opkg...'
opkg update
opkg install python3 python3-psutil || { echo 'Could not install Python dependencies'; exit 1; }
if ! python3 -c 'from PIL import Image,ImageDraw,ImageFont' 2>/dev/null; then
    opkg install --nodeps python3-pillow || { echo 'Could not install Pillow'; exit 1; }
fi
python3 -c 'import psutil; from PIL import Image'
mkdir -p /root/dashboard /opt/profinet-service/vendor
cp -R vendor/pnio_dcp /opt/profinet-service/vendor/
cp src/server.py /root/mudi_profinet.py
cp src/dashboard.py /root/dashboard/dashboard.py
for name in button_watch.py toggle.sh run.sh screen_sleep.sh; do cp "src/$name" "/root/dashboard/$name"; done
for name in profinet citydash homebutton; do cp "services/$name" "/etc/init.d/$name"; chmod 755 "/etc/init.d/$name"; done
chmod 755 /root/dashboard/*.sh
printf "PNIO_HOST='%s'\nPNIO_IFACE='%s'\nPNIO_PORT='8088'\n" "$host" "$iface" > /etc/profinet-service.conf
printf '%s\n' "$host" > /etc/profinet-service-host
python3 -m py_compile /root/mudi_profinet.py /root/dashboard/dashboard.py
PYTHONPATH=/opt/profinet-service/vendor python3 -c 'import pnio_dcp,psutil; from PIL import Image'
/etc/init.d/profinet enable
/etc/init.d/profinet start
/etc/init.d/homebutton enable
/etc/init.d/homebutton start
printf '\nInstalled. Web UI: http://%s:8088\n' "$host"
echo 'Touchscreen remains STOCK. To enable: /root/dashboard/toggle.sh on'
echo 'Backup your router configuration before upgrading firmware.'
