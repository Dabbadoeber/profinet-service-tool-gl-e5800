# profinet-service-tool-gl-e5800
Open-source PROFINET DCP service tool for GL.iNet Mudi 7

## Third-party software and credits

This project builds on open-source work. We thank the original authors and retain their copyright notices:

| Component | Author / project | Purpose | License / attribution |
| --- | --- | --- | --- |
| [pnio_dcp](https://pypi.org/project/pnio-dcp/) | Codewerk GmbH | PROFINET DCP Ethernet discovery and configuration | MIT; see `licenses/pnio-dcp-license.txt` in the source distribution |
| [gl-e5800-dashboard](https://github.com/robavionix/gl-e5800-dashboard) | robavionix | Original GL-E5800 touchscreen process/button handling and UI-switching concepts | MIT; see `licenses/GL-E5800-dashboard-MIT.txt` |
| [Pillow](https://python-pillow.github.io/) | Pillow contributors | Drawing the framebuffer touchscreen interface | Third-party dependency; see upstream license |
| [psutil](https://github.com/giampaolo/psutil) | psutil contributors | System status and metrics | Third-party dependency; see upstream license |
| [OpenWrt](https://openwrt.org/) | OpenWrt contributors | Underlying router operating system and package management | Various licenses; supplied by firmware, not redistributed here |
| [GL.iNet](https://www.gl-inet.com/) | GL.iNet | Mudi 7 hardware and stock firmware/screen application | Proprietary and open-source components as supplied by manufacturer; stock application not bundled |
| Python standard library | Python Software Foundation and contributors | HTTP server, networking and other utilities | Supplied by Python; not vendored here |

**Important:** listing a dependency is not a substitute for preserving its copyright/license text when distributing copied source. The source ZIP includes vendored `pnio_dcp` code and its MIT notice. Before adding more third-party source files or publishing a stable release, verify upstream license texts, copyright holders, and required notices. PROFINET and Siemens names are used descriptively; this project is not affiliated with or endorsed by Siemens, PROFIBUS & PROFINET International, or GL.iNet.
