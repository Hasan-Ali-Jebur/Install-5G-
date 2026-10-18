# Install 5G: Open5GS (Docker) + OCUDU gNB + USRP X310 + Google Pixel

A step-by-step guide to building a private **5G Standalone (SA)** testbed:

- **5G Core:** Open5GS running in Docker ([herlesupreeth/docker_open5gs](https://github.com/herlesupreeth/docker_open5gs))
- **RAN:** OCUDU gNB (built from source, split 8) on the host
- **Radio:** Ettus USRP X310 with 2 × UBX-40 daughterboards over 10 GbE
- **UE:** Google Pixel 9 Pro with a programmable sysmoISIM-SJA5 SIM

> 💻 **No hardware?** See the [ZMQ + simulated UE guide](zmq/README.md) to run the whole network on one PC.

> ⚠️ **Regulatory note.** Transmitting on cellular bands (e.g. n78) requires a licence (in the UK: Ofcom) or a shielded / cabled setup. Check with your lab before going on air.

---

## Contents

1. [Architecture](#1-architecture)
2. [Hardware and software](#2-hardware-and-software)
3. [Host preparation](#3-host-preparation)
4. [Open5GS 5G Core in Docker](#4-open5gs-5g-core-in-docker)
5. [How Docker networking connects everything](#5-how-docker-networking-connects-everything)
6. [UHD and the USRP X310](#6-uhd-and-the-usrp-x310)
7. [Build OCUDU](#7-build-ocudu)
8. [gNB configuration](#8-gnb-configuration)
9. [Program the SIM card](#9-program-the-sim-card)
10. [Add the subscriber to Open5GS](#10-add-the-subscriber-to-open5gs)
11. [Configure the Google Pixel](#11-configure-the-google-pixel)
12. [Run and stop the testbed](#12-run-and-stop-the-testbed)
13. [Verify and test connectivity](#13-verify-and-test-connectivity)
14. [Troubleshooting](#14-troubleshooting)
15. [References](#15-references)

---

## 1. Architecture

```
                         Internet
                            │
                  ┌─────────┴──────────┐
                  │ eno2 (internet)    │
   HOST           │ routing + NAT      │      eno1 ── SSH / WebUI from another PC
   (Ubuntu 22.04) │                    │
                  │ br-xxxx 172.22.0.1 │  ← Docker bridge (host = gateway)
                  └─────────┬──────────┘
          ┌──────────── Docker network 172.22.0.0/24 ─────────────┐
       ┌──┴──┐   ┌──┴──┐   ┌──┴──┐   ┌──┴──┐   ┌──┴──┐   ┌──┴───┐
       │ NRF │   │ AMF │   │ SMF │   │ UPF │   │ UDM │   │mongo │ ...
       │ .12 │   │ .10 │   │ .7  │   │ .8  │   │ .13 │   │ .2   │
       └─────┘   └──┬──┘   └─────┘   └──┬──┘   └─────┘   └──────┘
                    │ N2 (SCTP 38412)   │ N3 (GTP-U 2152)   ogstun 192.168.100.1 → N6 → NAT → internet
                    │                   │
               ┌────┴───────────────────┴────┐
               │ OCUDU gNB (runs on the host)│
               │ binds to 172.22.0.1         │
               └──────────────┬──────────────┘
                              │ 10 GbE (enp45s0f1 192.168.40.1, MTU 9000)
                       ┌──────┴──────┐
                       │ USRP X310   │ 192.168.40.2
                       │ RF A: TX/RX + RX2
                       └──────┬──────┘
                              │ radio (n78, 3410.1 MHz, 20 MHz TDD)
                         Google Pixel
```

**Key idea:** the core runs in containers on a private Docker bridge. The gNB runs on the host, which is plugged into that bridge as `172.22.0.1`, so it reaches the AMF (`172.22.0.10`) and UPF (`172.22.0.8`) directly, with no port publishing needed.

---

## 2. Hardware and software

| Item | Used in this guide |
|---|---|
| Host | Ubuntu 22.04, ≥ 8 CPU cores, ≥ 16 GB RAM |
| NICs | 1 × internet, 1 × SSH (optional), 1 × 10 GbE SFP+ for the X310 |
| SDR | USRP X310, 2 × UBX-40 (10 MHz–6 GHz, **40 MHz max analog bandwidth**) |
| Antennas | Rated for **3.3–3.8 GHz** (n78) |
| Clock | Internal; an external 10 MHz + PPS reference (OctoClock / CDA-2990) improves stability with phones |
| SIM | sysmocom sysmoISIM-SJA5 + data sheet (IMSI, Ki, OPc, ADM1) |
| SIM reader | Any PC/SC reader (e.g. HID OMNIKEY 6121) |
| Phone | Google Pixel 9 Pro (supports n78 SA) |
| Core | Open5GS via `docker_open5gs` |
| RAN | OCUDU gNB |
| Driver | UHD 4.8 (built from source); **must match the X310 FPGA image** |

---

## 3. Host preparation

### 3.1 Identify your interfaces

```bash
ip -br addr
```

Example used in this guide:

| Interface | IP | Purpose |
|---|---|---|
| `eno2` | your network IP | Internet uplink |
| `eno1` | `10.5.48.1/16` | Direct link to another PC (SSH, WebUI) |
| `enp45s0f1` | `192.168.40.1/24` | 10 GbE to the X310 |

### 3.2 X310 network port: MTU 9000 (persistent)

Find the NetworkManager connection for the X310 port, then set jumbo frames:

```bash
nmcli -f NAME,DEVICE con show
sudo nmcli con mod "USRP" 802-3-ethernet.mtu 9000   # use your connection name
sudo nmcli con up "USRP"
ip link show enp45s0f1 | grep mtu                    # expect mtu 9000
```

### 3.3 Kernel settings (persistent)

```bash
# IP forwarding (needed for UE internet access)
echo "net.ipv4.ip_forward=1" | sudo tee /etc/sysctl.d/99-open5gs.conf

# Socket buffers for the USRP
sudo tee /etc/sysctl.d/99-uhd.conf <<'EOF'
net.core.wmem_max=33554432
net.core.rmem_max=33554432
EOF

sudo sysctl --system
```

### 3.4 Firewall

```bash
sudo ufw disable
```

### 3.5 Clean up leftovers from earlier installs

A **native** Open5GS install leaves services and an `ogstun` interface on the host that conflict with the Docker core:

```bash
sudo systemctl stop 'open5gs-*'
sudo systemctl disable 'open5gs-*'
ip link show ogstun && sudo ip link del ogstun
```

Old Docker networks from other projects (srsRAN `docker_ran`, O-RAN SC RIC, …) can also be removed:

```bash
docker network ls
docker network prune
```

### 3.6 Install Docker

```bash
sudo apt update && sudo apt install -y git curl
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
docker --version && docker compose version
```

### 3.7 Make sure DNS works inside Docker

On many networks (university, corporate, some ISPs), public resolvers such as `8.8.8.8` are blocked. Docker containers can't use the host's local resolver (`127.0.0.53`), so they fall back to `8.8.8.8`, and `docker build` then fails with errors like `curl: (6) Could not resolve host`.

Test it:

```bash
getent hosts www.mongodb.org                          # host resolves?
docker run --rm busybox nslookup www.mongodb.org      # container resolves?
```

If the container fails, find your network's real DNS servers:

```bash
resolvectl status | grep -A2 "DNS Servers"
# or
nmcli dev show | grep -i "IP4.DNS"
```

Give them to Docker (merge the `dns` key by hand if `/etc/docker/daemon.json` already exists):

```bash
sudo tee /etc/docker/daemon.json <<'EOF'
{
  "dns": ["<DNS server 1>", "<DNS server 2>"]
}
EOF
sudo systemctl restart docker          # stops running containers
docker run --rm busybox nslookup www.mongodb.org
```

Quick alternative for a single build: `docker build --network host ...`.

---

## 4. Open5GS 5G Core in Docker

### 4.1 Clone and build from source

```bash
mkdir -p ~/5g && cd ~/5g
git clone https://github.com/herlesupreeth/docker_open5gs
cd docker_open5gs

cd base
docker build --no-cache --force-rm -t docker_open5gs .
cd ..
```

### 4.2 Configure `.env`

```bash
nano .env
```

Set at least:

```
MCC=001
MNC=01
TAC=1
DOCKER_HOST_IP=<one of your host IPs, e.g. 10.5.48.1>
UE_IPV4_INTERNET=192.168.100.0/24
SMF_DNS1=<DNS server reachable from your network>
SMF_DNS2=<DNS server reachable from your network>
```

> **DNS for the phone/UE:** use DNS servers that work on **your** network. Some networks block public resolvers like `8.8.8.8`. Find yours with `resolvectl status | grep -A2 "DNS Servers"`, and check one works with `dig @<server> google.com`. If public DNS works for you, `8.8.8.8` / `8.8.4.4` are fine.

`DOCKER_HOST_IP` defaults to a made-up address (`192.168.1.223`). Replace it with a real host IP. When the gNB runs on the same host, its value has little effect.

### 4.3 Set the DNN (APN) to `srsapn`

The DNN configured in the SMF/UPF **must match** the subscriber's DNN and the APN on the phone. This guide uses `srsapn`:

```bash
sed -i 's/dnn: internet/dnn: srsapn/' smf/smf.yaml upf/upf.yaml
grep -n "dnn:" smf/smf.yaml upf/upf.yaml     # expect srsapn (and ims)
```

### 4.4 Start the core

```bash
set -a; source .env; set +a
docker compose -f sa-deploy.yaml build
docker compose -f sa-deploy.yaml up -d
docker ps --format "table {{.Names}}\t{{.Status}}"     # 15 containers "Up"
```

### 4.5 Verify

```bash
ping -c 2 172.22.0.10                                   # host → AMF
docker logs amf 2>&1 | grep ngap_server | tail -1       # [172.22.0.10]:38412
docker exec -it upf ip -br addr                         # eth0 172.22.0.8, ogstun 192.168.100.1
docker exec -it upf ping -c 2 8.8.8.8                   # UPF → internet (N6 + NAT)
docker exec amf sh -c 'grep -A2 "plmn_id" $(find / -name amf.yaml -path "*open5gs*" | head -1)' | head -3
```

### 4.6 Default container IPs

| Component | IP | Key ports |
|---|---|---|
| Docker bridge (host side) | 172.22.0.1 | gNB `bind_addrs` |
| MongoDB | 172.22.0.2 | 27017 |
| SMF | 172.22.0.7 | 8805/udp (PFCP), 7777 (SBI) |
| UPF | 172.22.0.8 | 2152/udp (N3), 8805/udp (N4) |
| **AMF** | **172.22.0.10** | **38412/sctp (N2)**, 7777 |
| AUSF | 172.22.0.11 | 7777 |
| NRF | 172.22.0.12 | 7777 |
| UDM | 172.22.0.13 | 7777 |
| UDR | 172.22.0.14 | 7777 |
| WebUI | 172.22.0.26 | 9999 (`admin` / `1423`) |
| PCF | 172.22.0.27 | 7777 |
| NSSF | 172.22.0.28 | 7777 |
| BSF | 172.22.0.29 | 7777 |
| SCP | 172.22.0.35 | 7777 |
| Prometheus | 172.22.0.36 | 9090 |
| Grafana | 172.22.0.39 | 3000 |
| UE pool (`srsapn`) | 192.168.100.0/24 | gateway 192.168.100.1 |

The WebUI port is published on all host interfaces (`9999:9999/tcp`), so it is also reachable at `http://<any host IP>:9999`.

---

## 5. How Docker networking connects everything

- **Each container** has its own network namespace: its own `eth0`, IP and routing table.
- **The Docker bridge** (`br-<id>`, `172.22.0.1`) is a virtual switch on the host. Compose creates it as `docker_open5gs_default` using `TEST_NETWORK` from `.env`.
- **veth pairs** are virtual cables: `eth0` inside each container ↔ `vethXXXX` on the host, plugged into the bridge.
- **The host** is the router: it reaches every container directly and NATs container traffic out through the internet interface.
- **IPs** are fixed: `.env` → `sa-deploy.yaml` (`ipv4_address: ${AMF_IP}`) → each NF's config file, filled in at container start.

Useful commands:

```bash
docker network ls
docker network inspect docker_open5gs_default | grep -E '"Name"|IPv4Address|Gateway|Subnet'
ip -br addr | grep -E "br-|veth"
ip route | grep 172.22
docker exec -it amf ip addr
sudo iptables -t nat -L -n -v
sudo tcpdump -i br-<id> -n port 7777 or sctp      # watch NFs talk
```

5G interfaces on the bridge:

| Interface | Between | Protocol |
|---|---|---|
| SBI | all NFs ↔ NRF / SCP | HTTP/2, 7777 |
| N2 | gNB ↔ AMF | SCTP, 38412 |
| N4 | SMF ↔ UPF | PFCP, UDP 8805 |
| N3 | gNB ↔ UPF | GTP-U, UDP 2152 |
| N6 | UPF → internet | IP via `ogstun` + NAT |

---

## 6. UHD and the USRP X310

### 6.1 Keep exactly **one** UHD install

Mixed installs (apt/PPA in `/usr/bin` + source builds in `/usr/local`) cause hard-to-debug errors. Check:

```bash
which -a uhd_usrp_probe
uhd_config_info --version
ls /usr/local/lib | grep -i uhd
dpkg -l | grep -i uhd
```

This guide uses **UHD 4.8 built from source** in `/usr/local`. Remove the apt/PPA copy by **exact package name**. Don't use `libuhd*`, which would also remove GNU Radio's dependency:

```bash
sudo apt remove --purge uhd-host libuhd-dev libuhd4.11.0 python3-uhd uhd-rfnoc-dev
sudo add-apt-repository --remove ppa:ettusresearch/uhd
sudo ldconfig && hash -r
which -a uhd_usrp_probe          # only /usr/local/bin
```

### 6.2 Probe the X310

```bash
uhd_find_devices
sudo uhd_usrp_probe --args "type=x300,addr=192.168.40.2"
```

Default X310 addresses: `192.168.10.2` (1 GbE, SFP0), `192.168.20.2` (1 GbE, SFP1), `192.168.30.2`, `192.168.40.2` (10 GbE). The probe output lists them as `ip-addr0..3`.

**FPGA/UHD mismatch errors** mean the FPGA image was flashed by a different UHD version:

| Error | Meaning |
|---|---|
| `Major compat number mismatch ... revision 1 and UHD supports revision 0` | FPGA newer than UHD |
| `RFNoC protocol mismatch (SW: 2.0, HW: 1.0)` | FPGA older than UHD |

Fix by flashing the image that matches **your** UHD (use the same UHD's tools), then **power-cycle** the X310:

```bash
sudo uhd_images_downloader -t x310
uhd_image_loader --args "type=x300,addr=192.168.40.2,fpga=HG"   # HG = default image
```

### 6.3 Benchmark the link

```bash
sudo /usr/local/lib/uhd/examples/benchmark_rate \
  --args "type=x300,addr=192.168.40.2,master_clock_rate=184.32e6" \
  --rx_rate 23.04e6 --tx_rate 23.04e6 --duration 10
```

Expect **0 dropped samples, 0 overruns, 0 underruns, 0 sequence errors**.

---

## 7. Build OCUDU

```bash
sudo apt install -y git cmake make gcc g++ pkg-config libmbedtls-dev \
  libsctp-dev libyaml-cpp-dev libgtest-dev libfftw3-dev

cd ~/5g
git clone https://gitlab.com/ocudu/ocudu.git
cd ocudu && mkdir build && cd build
cmake -DDU_SPLIT_TYPE=SPLIT_8 -DBUILD_TESTING=OFF ../ 2>&1 | tee cmake.log
grep -i uhd cmake.log                 # Found UHD: /usr/local/lib/libuhd.so
make -j $(nproc)

ls -l apps/gnb/gnb
ldd apps/gnb/gnb | grep uhd           # /usr/local/lib/libuhd.so.4.8.0
```

---

## 8. gNB configuration

Copy [`configs/gnb_x310.yml`](configs/gnb_x310.yml) to `~/5g/gnb_x310.yml`:

```yaml
cu_cp:
  amf:
    addrs: 172.22.0.10          # AMF container
    port: 38412
    bind_addrs: 172.22.0.1      # host side of the Docker bridge
    supported_tracking_areas:
      - tac: 1                  # = TAC in .env
        plmn_list:
          - plmn: "00101"       # = MCC+MNC in .env and first 5 digits of the IMSI
            tai_slice_support_list:
              - sst: 1

cu_up:
  ngu:
    socket:
      - bind_addr: 172.22.0.1   # N3 towards UPF 172.22.0.8

ru_sdr:
  device_driver: uhd
  device_args: type=x300,addr=192.168.40.2,master_clock_rate=184.32e6,send_frame_size=8000,recv_frame_size=8000
  clock: internal               # 'external' with a 10 MHz + PPS reference
  sync: internal
  srate: 23.04                  # 184.32 / 8 → 20 MHz carrier
  tx_gain: 30
  rx_gain: 30
  time_alignment_calibration: auto

cell_cfg:
  dl_arfcn: 627340              # 3410.1 MHz, n78
  band: 78
  channel_bandwidth_MHz: 20
  common_scs: 30
  plmn: "00101"
  tac: 1
  pci: 1

log:
  filename: /tmp/gnb.log
  all_level: info

pcap:
  ngap_enable: true
  ngap_filename: /tmp/gnb_ngap.pcap
```

Notes:

- With **UBX-40** boards, keep the carrier at **20 MHz** (40 MHz fills the whole analog bandwidth).
- The X310 sample rate must divide the master clock: 23.04 (20 MHz), 46.08 (40 MHz), 92.16 (80 MHz) with 184.32 MHz.
- If the gNB rejects `addrs` / `bind_addrs`, use the older key names `addr` / `bind_addr`.
- The gNB reads its config **only at startup**: stop it (Ctrl+C) before editing, then start again.

---

## 9. Program the SIM card

### 9.1 Install pySim and the reader driver

```bash
sudo apt install -y pcscd pcsc-tools libccid libpcsclite-dev python3-pyscard \
  python3-setuptools python3-pycryptodome python3-pip
sudo systemctl enable --now pcscd

cd ~/5g
git clone https://gitea.osmocom.org/sim-card/pysim.git
cd pysim
pip3 install --user -r requirements.txt

pcsc_scan          # reader + "Card inserted"
```

`libccid` is required for most USB readers. Without it pySim reports `No reader found for number 0`.

### 9.2 Read the card

```bash
./pySim-read.py -p0
```

Note the **IMSI**, **ICCID**, **FPLMN** list and **USIM Service Table**.

### 9.3 Reprogram the IMSI to PLMN 00101

The **first 5 digits of the IMSI are the SIM's home network** and must match the network's PLMN. sysmocom cards ship with `99970…`. Pixel phones work best with **00101**.

Pass `-k` / `-o` with the **Ki / OPc from the data sheet** to keep the original keys (otherwise pySim generates new random keys, which you must note down):

```bash
./pySim-prog.py -p0 -s <ICCID> --mcc=001 --mnc=01 -a <ADM1> \
  --imsi=00101<last 10 digits of the original IMSI> \
  -k <Ki> -o <OPc>

./pySim-read.py -p0 | grep -E "IMSI|ICCID"
```

> ⚠️ Entering a wrong **ADM1** key ~3 times **locks the card permanently**. If pySim reports an ADM error, stop and double-check. Don't retry blindly.

### 9.4 Disable SUCI concealment (if enabled)

```bash
./pySim-read.py -p0 | grep -E "Service 12[2-5]"
```

If services **124** or **125** are listed, deactivate them:

```bash
./pySim-shell.py -p0
pySIM-shell (MF)> verify_adm <ADM1>
pySIM-shell (MF)> select MF/ADF.USIM/EF.UST
pySIM-shell (MF/ADF.USIM/EF.UST)> ust_service_deactivate 124
pySIM-shell (MF/ADF.USIM/EF.UST)> ust_service_deactivate 125
pySIM-shell (MF/ADF.USIM/EF.UST)> quit
```

### 9.5 Check the forbidden-network list (FPLMN)

If a registration is rejected, the phone may write `00101` into the SIM's forbidden list and stop trying:

```bash
./pySim-read.py -p0 | grep -A5 "FPLMN"
```

If `00f110` (MCC 001 / MNC 01) appears, clear the list:

```bash
./pySim-shell.py -p0
verify_adm <ADM1>
select MF/ADF.USIM/EF.FPLMN
update_binary ffffffffffffffffffffffff
quit
```

---

## 10. Add the subscriber to Open5GS

Use the **same IMSI, Ki and OPc as the card**. A mismatch here is the most common cause of authentication failures.

```bash
cd ~/5g/docker_open5gs
docker exec -it webui misc/db/open5gs-dbctl add_ue_with_apn <IMSI> <Ki> <OPc> srsapn
docker exec webui misc/db/open5gs-dbctl showpretty | grep -E "imsi|name|ipv4"
```

Expect your IMSI, `name: 'srsapn'`, and **no** static `ipv4` from an old pool.

To replace an existing entry:

```bash
docker exec -it webui misc/db/open5gs-dbctl remove <old IMSI>
```

Or use the WebUI (`http://<host IP>:9999`, `admin` / `1423`): IMSI, K, **OPc** (select the OPc type!), AMF `8000`, SST `1`, DNN `srsapn`, IPv4.

---

## 11. Configure the Google Pixel

### 11.1 SIM settings

**Settings → Network & internet → SIMs → [your SIM]:**

| Setting | Value |
|---|---|
| Use SIM | ON (disable other SIMs / eSIMs while testing) |
| Mobile data | ON |
| Roaming | ON |
| Preferred network type | 5G (recommended) |
| Automatically select network | ON |
| Allow 2G | OFF |
| Carrier settings version | should start with `test001` (test SIM recognised) |

### 11.2 Access Point Name

**Settings → Network & internet → SIMs → [your SIM] → Access Point Names → +**

| Field | Value |
|---|---|
| Name | `srsapn` |
| APN | `srsapn` |
| MCC | `001` (auto-filled from the IMSI) |
| MNC | `01` (auto-filled from the IMSI) |
| APN type | `default` |
| APN protocol | IPv4 |
| APN roaming protocol | IPv4 |
| Everything else | Not set |

Save via **⋮ → Save**, then **select** the APN.

### 11.3 Force 5G NR only

1. Enable Developer options: **Settings → About phone →** tap **Build number** 7 times.
2. Dial `*#*#4636#*#*` → **Phone information**.
3. On dual-SIM phones, select the **correct phone index / SIM** at the top.
4. **Set preferred network type → NR only**.

This setting can **reset after a reboot**. Re-check it after every restart.

### 11.4 Prevent disconnects (IMS timers)

Dial `*#*#0702#*#*` and set:

| Setting | Value |
|---|---|
| `NR_TIMER_WAIT_IMS_REGISTRATION` | `-1` (infinite) |
| `SUPPORT_IMS_NR_REGISTRATION_TIMER` | `0` (disabled) |

These are per-SIM and survive reboots.

### 11.5 Inspect the phone over USB (adb)

Enable **USB debugging** in Developer options, connect the phone to the host, and accept the prompt:

```bash
sudo apt install -y adb
adb devices

# SIM PLMN as the phone sees it (expect 00101)
adb shell getprop gsm.sim.operator.numeric

# 5G SA allowed by the carrier profile? (expect [1, 2]; 2 = SA)
adb shell dumpsys carrier_config | grep -i carrier_nr_availabilities

# Current radio technology: 14 = LTE (not good), 20 = NR, 0 = searching
adb shell dumpsys telephony.registry | grep -o "getRilDataRadioTechnology=[0-9]*([A-Z]*)" | tail -1

# Radio log during an attach attempt
adb logcat -b radio -c
# toggle airplane mode on the phone, wait 60 s
adb logcat -b radio -d | grep -i -E "reject|cause|registration|00101|IN_SERVICE" | tail -40
```

If the phone reports **LTE** and shows local operators (e.g. "vodafone UK", emergency only), NR-only is **not** active and the phone will never scan for your cell. Set it again (11.3).

---

## 12. Run and stop the testbed

### Start

```bash
# 1. Core
cd ~/5g/docker_open5gs
set -a; source .env; set +a
docker compose -f sa-deploy.yaml up -d
docker ps --format "table {{.Names}}\t{{.Status}}"

# 2. Host tuning (resets on reboot)
cd ~/5g/ocudu && sudo ./scripts/ocudu_performance     # answer y to all

# 3. gNB
cd ~/5g/ocudu/build/apps/gnb
sudo ./gnb -c ~/5g/gnb_x310.yml
```

Expected gNB output:

```
Cell pci=1, bw=20 MHz, 1T1R, dl_arfcn=627340 (n78), dl_freq=3410.1 MHz, dl_ssb_arfcn=626976, ul_freq=3410.1 MHz
Connected to AMF. Supported PLMNs: 00101
==== gNB started ===
```

Type `t` + Enter in the gNB console to show the live UE metrics table. The warning `Attempting to set tick rate to 0. Skipping.` is harmless.

### Watch

```bash
# Terminal 2: core
docker logs -f --tail 0 amf

# Terminal 3: gNB RRC events
sudo tail -f /tmp/gnb.log | grep --line-buffered -E "rrcSetupRequest|rrcSetupComplete|rrcRelease|Reject"
```

### Stop

```bash
# gNB: Ctrl+C
cd ~/5g/docker_open5gs
docker compose -f sa-deploy.yaml down
```

---

## 13. Verify and test connectivity

A successful attach looks like this:

| Where | What you see |
|---|---|
| AMF | `gNB-N2 accepted`, `Number of gNBs is now 1` |
| gNB log | `rrcSetupRequest` → `rrcSetupComplete` → `dlInformationTransfer` / `ulInformationTransfer` (no immediate `rrcRelease`) |
| AMF | `Registration complete`, UE context created |
| SMF | PDU session, UE IP `192.168.100.x` |
| Phone | **5G** icon, operator shown |

Connectivity tests:

```bash
# Uplink, from the phone (e.g. Termux):
ping 192.168.100.1

# Downlink, from the host:
docker exec upf ping -c 3 192.168.100.<UE IP>

# Internet + DNS, from the phone:
ping 1.1.1.1
ping google.com          # fails but 1.1.1.1 works → DNS problem (see 4.2)
```

---

## 14. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `uhd_usrp_probe`: *compat number mismatch* / *RFNoC protocol mismatch* | FPGA image built for a different UHD | Flash the image matching your UHD (6.2), power-cycle |
| Several `uhd_usrp_probe` paths, different versions | Mixed apt + source UHD | Keep one (6.1); confirm with `ldd gnb \| grep uhd` |
| *send buffer could not be resized* | Small socket buffers | Section 3.3 / `ocudu_performance` |
| Late / underflow / overflow counts keep rising | Host can't keep up or link problem | `ocudu_performance`, MTU 9000, rerun `benchmark_rate` |
| pySim: *No reader found for number 0* | CCID driver missing | `sudo apt install libccid && sudo systemctl restart pcscd` |
| gNB: no `Connected to AMF` | Core down / wrong address | `ping 172.22.0.10`; `addrs` = 172.22.0.10, `bind_addrs` = 172.22.0.1 |
| NG Setup failure | PLMN or TAC mismatch | Same PLMN/TAC in `.env` and `gnb_x310.yml` |
| Phone never appears in gNB log | Phone on LTE / NR-only not set | 11.3; check with adb (11.5) |
| Phone camps on local operators "emergency only" | Same as above | Set NR only on the correct SIM slot |
| `rrcSetupComplete` then immediate `rrcRelease` | Core rejected registration | Read `docker logs amf`: IMSI/PLMN mismatch, wrong Ki/OPc, SUCI enabled |
| IMSI starts with `99970` but network is `00101` | SIM home network ≠ network PLMN | Reprogram SIM (9.3) or set core + gNB to the SIM's PLMN |
| Authentication / MAC failure | Ki or OPc in DB ≠ card | Re-add subscriber with data sheet values (10) |
| Registered but no data | DNN mismatch (`internet` vs `srsapn`), stale static IP | DNN identical in SMF/UPF, subscriber and phone APN |
| Phone stops trying the network | `00101` added to FPLMN | Clear FPLMN (9.5) |
| UE has IP but no websites | Network blocks public DNS | Set `SMF_DNS1/2` to your network's resolvers (4.2) |
| `docker build`: `Could not resolve host` | DNS blocked inside containers | Section 3.7 |
| UE internet broken after old native install | Stale host `ogstun` hijacks routes | `sudo ip link del ogstun` (3.5) |
| Unstable cell / phone can't lock | Frequency error of internal oscillator | Use an external 10 MHz + PPS reference, `clock/sync: external` |

---

## 15. References

- Open5GS in Docker: <https://github.com/herlesupreeth/docker_open5gs>
- OCUDU documentation: <https://docs.ocudu.org/>, source: <https://gitlab.com/ocudu/ocudu>
- OCUDU config reference: <https://docs.ocudu.org/user_manual/config_reference/>
- srsRAN COTS UE tutorial: <https://docs.srsran.com/projects/project/en/latest/tutorials/source/cotsUE/source/index.html>
- pySim: <https://gitea.osmocom.org/sim-card/pysim>
- UoY X310 setup: <https://github.com/uoy-research/srsRAN-USRPs-OTA>
- UoY OCUDU + COTS guide: <https://github.com/SystronLab/OCUDU-USRPs-COTS>
