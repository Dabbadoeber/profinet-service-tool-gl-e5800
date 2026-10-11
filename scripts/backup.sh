#!/bin/sh
set -eu
out="${1:-/tmp/profinet-service-backup.tar.gz}"
set --
for path in /root/dashboard /root/mudi_profinet.py /root/profinet_last_scan.json /etc/init.d/profinet /etc/init.d/citydash /etc/init.d/homebutton /etc/profinet-service.conf /etc/profinet-service-host /opt/profinet-service/vendor; do
    [ ! -e "$path" ] || set -- "$@" "$path"
done
[ "$#" -gt 0 ] || { echo 'Nothing to back up'; exit 1; }
tar -czf "$out" "$@"
echo "Saved: $out (download it from the router before rebooting)"
