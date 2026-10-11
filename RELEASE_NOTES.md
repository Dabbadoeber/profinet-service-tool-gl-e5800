# PROFINET Service Tool — v0.1.0 RC2

Community release candidate for GL.iNet Mudi 7 (GL-E5800), OpenWrt 23.05.4.

## Features
- PROFINET DCP discovery on the locally connected Ethernet network
- Station name, IP address, mask, gateway, MAC and device family display
- Identify/blink start and stop (120-second limit)
- Change PROFINET station name and IPv4 settings with confirmation
- Web UI (TCP 8088), touchscreen with ABC/123 keyboard
- Last-scan cache shared between web and touchscreen
- Switch between stock GL.iNet and custom touchscreen UI

## Important
- **Release candidate only:** generic installer has not been verified on a factory-reset Mudi 7.
- **Security:** no built-in web authentication or TLS. Never expose TCP 8088 to the public internet. Use a trusted service LAN or secured VPN.
- DCP is Ethernet Layer 2 and cannot discover devices through a routed WireGuard tunnel. The router performs DCP operations locally.
- Network configuration writes can interrupt PLC or production equipment. Only use on authorized equipment.
- Back up router configuration and custom files before installing or upgrading firmware.
- Preserve upstream licenses and attribution for reused components. Project-level licensing is pending rights review.

## Test checklist
- [ ] Clean installation on GL-E5800
- [ ] Web scan, blink, name and network writes on test hardware
- [ ] Touchscreen, ABC/123 keyboard, stock UI switching
- [ ] Reboot, backup, uninstall, firmware upgrade recovery
- [ ] Verify interface binding and firewall rules

The complete installation ZIP should be attached to a GitHub prerelease after reviewing its contents and verifying redistribution rights.