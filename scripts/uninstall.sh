#!/bin/sh
set -eu
[ "$(id -u)" = 0 ] || exit 1
printf 'Remove PROFINET Service Tool and restore stock screen? [y/N] '; read ans
[ "$ans" = y ] || exit 0
[ ! -x /root/dashboard/toggle.sh ] || /root/dashboard/toggle.sh off || true
for svc in profinet homebutton citydash; do /etc/init.d/$svc stop 2>/dev/null || true; /etc/init.d/$svc disable 2>/dev/null || true; done
rm -f /etc/init.d/profinet /etc/init.d/homebutton /etc/init.d/citydash /root/mudi_profinet.py /etc/profinet-service.conf /etc/profinet-service-host
rm -rf /root/dashboard /opt/profinet-service/vendor
echo 'Uninstalled. Scan history kept at /root/profinet_last_scan.json; remove manually if desired.'
