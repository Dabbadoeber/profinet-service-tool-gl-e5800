# PROFINET Service Tool for GL.iNet Mudi 7 (GL-E5800)

Open-source-style **community release candidate**: local PROFINET DCP scanner and configuration UI for the GL.iNet Mudi 7 (GL-E5800), with a web interface and built-in 240×320 touchscreen.

> **Status:** packaged from a working, user-tested installation; **this new generic installer has not yet been tested on a freshly reset Mudi 7.** Do not publish as a stable release before testing the installation and recovery steps.

## Features

- Discover PROFINET devices using DCP on the local Ethernet interface
- Show station name, IP, subnet mask, gateway, MAC and device family
- Start/stop identify/blink LED (120-second safety limit)
- Change station name and IPv4 network settings with explicit confirmation
- Touchscreen keyboard with ABC/123 pages
- Shared last-scan cache between web and touchscreen (`/root/profinet_last_scan.json`), replaced when a new scan starts
- Switch between custom touchscreen and stock GL.iNet UI using the original power-button watcher
- Web UI at `http://<router-LAN-IP>:8088`

## Supported hardware

Tested by the original user on **GL.iNet Mudi 7 GL-E5800**, OpenWrt 23.05.4 / GL.iNet firmware 4.8.x, with the RGB565 `/dev/fb0` screen and `/dev/input/event0`. Other devices are **not supported** by the installer. DCP works only on the local Ethernet broadcast domain, not over a routed WireGuard tunnel. Remote users can access the web UI over a *properly secured* VPN and use the Mudi to issue local DCP operations.

## Before installing

1. Make a **router configuration backup** and keep SSH access available.
2. Download this repository as ZIP, unpack it on a computer, and copy the entire directory to the Mudi (for example `/root/profinet-service-tool`).
3. Confirm Ethernet interface and LAN IP. The defaults are `eth0` and `10.10.0.1`, which **may not match your router**.
4. Do **not** run the installer on an existing installation. It refuses to overwrite the dashboard, web server, or their service files. Use a separate clean test device for the first installation test.

## Installation (PuTTY / SSH)

```sh
cd /root/profinet-service-tool
sh install.sh
```

The installer uses `opkg` for Python/Pillow/psutil, bundles the `pnio_dcp` Python source (with its license), installs the web service and touchscreen, and starts the web service. It **does not activate the custom touchscreen automatically**.

```sh
/root/dashboard/toggle.sh on       # activate custom touchscreen
/root/dashboard/toggle.sh off      # restore original GL.iNet screen
/etc/init.d/profinet status
logread | grep -i profinet
```

Browse `http://<router-LAN-IP>:8088`. Use **Scan Devices** to discover devices, select one, then use **Blink**, **Set Name** or **Set Network**. Writing station names/IP addresses can disrupt an operating plant; test only on equipment you are authorized to administer, ideally a test PLC.

## Configuration

The installer writes `/etc/profinet-service.conf` with `PNIO_HOST`, `PNIO_IFACE` and `PNIO_PORT`, and `/etc/profinet-service-host` for the touchscreen API URL. After changing these, restart both services. The LAN address must exist on the Mudi; the DCP interface must be connected to the PLC network.

**Security:** this tool currently has **no built-in web authentication or TLS**. Do not expose TCP 8088 to the public internet. Use a trusted service LAN or VPN, and firewall the interface appropriately. The web API permits writing DCP network settings.

## Backup and firmware upgrade

```sh
sh scripts/backup.sh /tmp/profinet-service-backup.tar.gz
```

Download the archive from `/tmp` using WinSCP **before rebooting**. Also save the GL.iNet configuration separately. Firmware upgrades may remove extra Python packages and custom files. Keep this installation ZIP so you can reinstall. See [OpenWrt sysupgrade documentation](https://openwrt.org/docs/guide-user/installation/generic.sysupgrade).

## Uninstall

```sh
sh scripts/uninstall.sh
```

Restores the stock screen and removes the tool; scan history is intentionally left in place.

## Acknowledgements and licenses

- Touchscreen process management, button watcher and toggle scripts derive from [robavionix/gl-e5800-dashboard](https://github.com/robavionix/gl-e5800-dashboard), MIT licensed. See `licenses/GL-E5800-dashboard-MIT.txt`.
- DCP protocol implementation from `pnio_dcp` (Codewerk GmbH). See `licenses/pnio-dcp-license.txt`.
- The generic web UI and touchscreen application are provided as source in `src/`.

**Before publishing publicly:** confirm you own the rights to publish your application modifications and choose/add an appropriate top-level project license. Third-party attribution files must remain included. Contributions and hardware testing are welcome.

## Release checklist

- [ ] Test clean installation on a supported GL-E5800 with SSH access and a router configuration backup
- [ ] Verify the configured LAN IP is assigned and the selected DCP interface connects to the test network
- [ ] Verify web scan, saved scan, blink start/stop, set name, set network, and touch keyboard on a test PLC
- [ ] Verify screen switching and original GL.iNet PIN/auto-lock behavior
- [ ] Verify reboot persistence, backup and uninstall
- [ ] Review firewall rules: never publish port 8088 to WAN
- [ ] Confirm third-party licenses and add a project-level license after rights review
