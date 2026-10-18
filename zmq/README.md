# Install 5G (No Hardware): Open5GS (Docker) + OCUDU gNB + srsUE over ZeroMQ

A step-by-step guide to running a complete **5G Standalone (SA)** network on **one Linux machine with no radio hardware**:

- **5G Core:** Open5GS in Docker ([herlesupreeth/docker_open5gs](https://github.com/herlesupreeth/docker_open5gs))
- **gNB:** OCUDU built with the **ZeroMQ (ZMQ)** virtual radio
- **UE:** **srsUE** (from srsRAN 4G) built with ZMQ, running in its own network namespace

Instead of an SDR, the gNB and the UE exchange baseband IQ samples over local TCP sockets. Everything else, including NGAP, NAS, authentication, PDU sessions and GTP-U, is the real 5G stack. That makes this setup ideal for learning, development and **5G core security research**.

> For the over-the-air version with a USRP X310 and a Google Pixel, see the [main guide](../README.md).

---

## Contents

1. [Architecture](#1-architecture)
2. [Requirements](#2-requirements)
3. [Host preparation](#3-host-preparation)
4. [Open5GS 5G Core in Docker](#4-open5gs-5g-core-in-docker)
5. [Build OCUDU with ZMQ](#5-build-ocudu-with-zmq)
6. [Build srsUE with ZMQ](#6-build-srsue-with-zmq)
7. [Add the simulated subscriber](#7-add-the-simulated-subscriber)
8. [gNB configuration (ZMQ)](#8-gnb-configuration-zmq)
9. [srsUE configuration (ZMQ)](#9-srsue-configuration-zmq)
10. [Run the network](#10-run-the-network)
11. [Routing and connectivity tests](#11-routing-and-connectivity-tests)
12. [Stop the network](#12-stop-the-network)
13. [Troubleshooting](#13-troubleshooting)
14. [Next steps](#14-next-steps)
15. [References](#15-references)

---

## 1. Architecture

```
                                Internet
                                   │
                         ┌─────────┴──────────┐
   HOST (Ubuntu 22.04)   │ routing + NAT      │
                         │ br-xxxx 172.22.0.1 │ ← Docker bridge
                         └─────────┬──────────┘
         ┌─────────────── Docker network 172.22.0.0/24 ───────────────┐
      ┌──┴──┐   ┌──┴──┐   ┌──┴──┐   ┌──┴──┐   ┌──┴──┐   ┌───┴───┐
      │ NRF │   │ AMF │   │ SMF │   │ UPF │   │ UDM │   │ mongo │ ...
      │ .12 │   │ .10 │   │ .7  │   │ .8  │   │ .13 │   │  .2   │
      └─────┘   └──┬──┘   └─────┘   └──┬──┘   └─────┘   └───────┘
                   │ N2 SCTP 38412     │ N3 GTP-U 2152      ogstun 192.168.100.1 → N6 → NAT
                   │                   │
            ┌──────┴───────────────────┴──────┐
            │  OCUDU gNB (host, 172.22.0.1)   │
            │  ru_sdr: zmq                    │
            │  TX → tcp://127.0.0.1:2000      │
            │  RX ← tcp://127.0.0.1:2001      │
            └───────────────┬─────────────────┘
                            │  IQ samples over ZMQ (localhost)
            ┌───────────────┴─────────────────┐
            │  srsUE (netns "ue1")            │
            │  TX → tcp://127.0.0.1:2001      │
            │  RX ← tcp://127.0.0.1:2000      │
            │  tun_srsue 192.168.100.x        │
            └─────────────────────────────────┘
```

The ports are crossed: the gNB **transmits** on 2000, which the UE **receives** on, and the UE transmits on 2001, which the gNB receives on.

---

## 2. Requirements

| Item | Recommended |
|---|---|
| OS | Ubuntu 22.04 LTS (bare metal or VM) |
| CPU | **≥ 6 cores**. ZMQ processes every sample in real time, and fewer than about 5 cores often fails to attach. |
| RAM | ≥ 8 GB (≥ 4 GB free for building) |
| Disk | ~15 GB |
| Hardware | **None** |

---

## 3. Host preparation

### 3.1 Base packages and Docker

```bash
sudo apt update
sudo apt install -y git curl build-essential cmake make gcc g++ pkg-config \
  libfftw3-dev libmbedtls-dev libsctp-dev libyaml-cpp-dev libgtest-dev \
  libboost-program-options-dev libconfig++-dev libzmq3-dev iperf3

curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
docker --version && docker compose version
```

### 3.2 Make sure DNS works inside Docker

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

### 3.3 Kernel and firewall

```bash
echo "net.ipv4.ip_forward=1" | sudo tee /etc/sysctl.d/99-open5gs.conf
sudo sysctl --system
sudo ufw disable
```

### 3.4 Remove leftovers (if you had native Open5GS or other labs before)

```bash
sudo systemctl stop 'open5gs-*' 2>/dev/null; sudo systemctl disable 'open5gs-*' 2>/dev/null
ip link show ogstun 2>/dev/null && sudo ip link del ogstun
docker network prune
```

---

## 4. Open5GS 5G Core in Docker

This is the **same core** as the hardware guide.

### 4.1 Clone and build

```bash
mkdir -p ~/5g && cd ~/5g
git clone https://github.com/herlesupreeth/docker_open5gs
cd docker_open5gs
cd base && docker build --no-cache --force-rm -t docker_open5gs . && cd ..
```

### 4.2 Configure `.env`

```bash
nano .env
```

```
MCC=001
MNC=01
TAC=1
DOCKER_HOST_IP=<your host IP>
UE_IPV4_INTERNET=192.168.100.0/24
SMF_DNS1=<DNS reachable from your network>
SMF_DNS2=<DNS reachable from your network>
```

> **DNS for the phone/UE:** use DNS servers that work on **your** network. Some networks block public resolvers like `8.8.8.8`. Find yours with `resolvectl status | grep -A2 "DNS Servers"`, and check one works with `dig @<server> google.com`. If public DNS works for you, `8.8.8.8` / `8.8.4.4` are fine.

### 4.3 Use the DNN `srsapn`

srsUE requests the DNN set in its config (`apn = srsapn`). The core must offer the same DNN:

```bash
sed -i 's/dnn: internet/dnn: srsapn/' smf/smf.yaml upf/upf.yaml
grep -n "dnn:" smf/smf.yaml upf/upf.yaml       # srsapn (and ims)
```

### 4.4 Start and verify

```bash
set -a; source .env; set +a
docker compose -f sa-deploy.yaml build
docker compose -f sa-deploy.yaml up -d
docker ps --format "table {{.Names}}\t{{.Status}}"    # 15 containers "Up"

ping -c 2 172.22.0.10                                  # host → AMF
docker logs amf 2>&1 | grep ngap_server | tail -1      # [172.22.0.10]:38412
docker exec -it upf ping -c 2 8.8.8.8                  # UPF → internet
```

Key addresses:

| Component | IP |
|---|---|
| Host on the Docker bridge | 172.22.0.1 |
| AMF (N2, SCTP 38412) | 172.22.0.10 |
| UPF (N3, GTP-U 2152) | 172.22.0.8 |
| WebUI (`admin` / `1423`) | `http://<host IP>:9999` |
| UE pool / gateway | 192.168.100.0/24 / 192.168.100.1 |

---

## 5. Build OCUDU with ZMQ

ZMQ support is **off by default** and must be enabled at build time. If you already have an OCUDU build for a USRP, use a **separate build folder** so both coexist.

```bash
cd ~/5g
[ -d ocudu ] || git clone https://gitlab.com/ocudu/ocudu.git
cd ocudu
mkdir -p build_zmq && cd build_zmq
cmake ../ -DENABLE_EXPORT=ON -DENABLE_ZEROMQ=ON -DBUILD_TESTING=OFF 2>&1 | tee cmake.log
grep -i zmq cmake.log            # ZeroMQ found / enabled
make -j $(nproc)
ls -l apps/gnb/gnb
```

At startup, the gNB banner should include `zmq` in `Available radio types`.

---

## 6. Build srsUE with ZMQ

srsUE is part of **srsRAN 4G** and supports 5G SA. With `libzmq3-dev` installed, ZMQ support is detected automatically.

```bash
cd ~/5g
git clone https://github.com/srsran/srsRAN_4G.git
cd srsRAN_4G
mkdir -p build && cd build
cmake ../ 2>&1 | tee cmake.log
grep -i zeromq cmake.log         # FOUND ZEROMQ / ZEROMQ enabled
make -j $(nproc) srsue
ls -l srsue/src/srsue
```

> Building only the `srsue` target is faster than building all of srsRAN 4G. If you run `make test`, skip failures in components you don't use.

---

## 7. Add the simulated subscriber

srsUE uses a **software USIM** whose identity is set in its config file. These are the public example values from the srsRAN tutorials. They're fine for a lab, but change them for anything shared:

| Field | Value |
|---|---|
| IMSI | `001010123456780` |
| K | `00112233445566778899aabbccddeeff` |
| OPc | `63BFA50EE6523365FF14C1F45F88737D` |
| DNN | `srsapn` |

```bash
cd ~/5g/docker_open5gs
docker exec -it webui misc/db/open5gs-dbctl add_ue_with_apn 001010123456780 \
  00112233445566778899aabbccddeeff 63BFA50EE6523365FF14C1F45F88737D srsapn
docker exec webui misc/db/open5gs-dbctl showpretty | grep -E "imsi|name"
```

---

## 8. gNB configuration (ZMQ)

Save as `~/5g/gnb_zmq.yml` (also in [`gnb_zmq.yml`](gnb_zmq.yml)):

```yaml
cu_cp:
  amf:
    addrs: 172.22.0.10          # AMF container
    port: 38412
    bind_addrs: 172.22.0.1      # host side of the Docker bridge
    supported_tracking_areas:
      - tac: 1                  # = TAC in .env
        plmn_list:
          - plmn: "00101"       # = MCC+MNC in .env
            tai_slice_support_list:
              - sst: 1
  inactivity_timer: 7200        # keep the simulated UE connected

cu_up:
  ngu:
    socket:
      - bind_addr: 172.22.0.1   # N3 towards UPF 172.22.0.8

ru_sdr:
  device_driver: zmq
  device_args: tx_port=tcp://127.0.0.1:2000,rx_port=tcp://127.0.0.1:2001,base_srate=23.04e6
  srate: 23.04
  tx_gain: 75
  rx_gain: 75

cell_cfg:
  dl_arfcn: 368500              # band 3 FDD (srsUE supports 15 kHz SCS FDD)
  band: 3
  channel_bandwidth_MHz: 20
  common_scs: 15
  plmn: "00101"
  tac: 1
  pci: 1
  pdcch:                        # settings required to match srsUE capabilities
    common:
      ss0_index: 0
      coreset0_index: 12
    dedicated:
      ss2_type: common
      dci_format_0_1_and_1_1: false
  prach:
    prach_config_index: 1
  pdsch:
    mcs_table: qam64
  pusch:
    mcs_table: qam64

log:
  filename: /tmp/gnb.log
  all_level: info
  hex_max_size: 0

pcap:
  mac_enable: false
  mac_filename: /tmp/gnb_mac.pcap
  ngap_enable: true
  ngap_filename: /tmp/gnb_ngap.pcap
```

Why these values:

- **Band 3 FDD, 15 kHz SCS, 20 MHz.** srsUE's 5G SA support is limited to FDD with 15 kHz subcarrier spacing. The hardware guide's n78 TDD cell won't work with srsUE.
- **`pdcch` / `prach` overrides** make the gNB use configurations that srsUE can decode.
- **ZMQ has no real RF**, so the frequency is only a label. Nothing is transmitted and no licence is needed.

---

## 9. srsUE configuration (ZMQ)

Save as `~/5g/ue_zmq.conf` (also in [`ue_zmq.conf`](ue_zmq.conf)):

```ini
[rf]
freq_offset = 0
tx_gain = 50
rx_gain = 40
srate = 23.04e6
nof_antennas = 1
device_name = zmq
device_args = tx_port=tcp://127.0.0.1:2001,rx_port=tcp://127.0.0.1:2000,base_srate=23.04e6

[rat.eutra]
dl_earfcn = 2850
nof_carriers = 0

[rat.nr]
bands = 3
nof_carriers = 1
max_nof_prb = 106
nof_prb = 106

[pcap]
enable = none
mac_filename = /tmp/ue_mac.pcap
mac_nr_filename = /tmp/ue_mac_nr.pcap
nas_filename = /tmp/ue_nas.pcap

[log]
all_level = info
phy_lib_level = none
all_hex_limit = 32
filename = /tmp/ue.log
file_max_size = -1

[usim]
mode = soft
algo = milenage
opc  = 63BFA50EE6523365FF14C1F45F88737D
k    = 00112233445566778899aabbccddeeff
imsi = 001010123456780
imei = 353490069873319

[rrc]
release = 15
ue_category = 4

[nas]
apn = srsapn
apn_protocol = ipv4

[gw]
netns = ue1
ip_devname = tun_srsue
ip_netmask = 255.255.255.0

[gui]
enable = false
```

Notes:

- `nof_carriers = 0` under `[rat.eutra]` disables LTE, so the UE runs **5G SA only**.
- `nof_prb = 106` matches **20 MHz at 15 kHz SCS**. For 10 MHz use 52, and for 5 MHz use 25 (change the gNB bandwidth and both `srate` / `base_srate` values to match).
- `netns = ue1` puts the UE's IP interface (`tun_srsue`) into its own **network namespace**. That way its traffic really goes through the 5G network instead of the host's normal routing.
- The `[usim]` and `[nas] apn` values must match the subscriber in section 7.

---

## 10. Run the network

Use **three terminals**. Start them **in this order**.

### Terminal 1: core

```bash
cd ~/5g/docker_open5gs
set -a; source .env; set +a
docker compose -f sa-deploy.yaml up -d
docker logs -f --tail 0 amf
```

### Terminal 2: gNB

```bash
cd ~/5g/ocudu/build_zmq/apps/gnb
sudo ./gnb -c ~/5g/gnb_zmq.yml
```

Expected:

```
Available radio types: ... zmq ...
Cell pci=1, bw=20 MHz, 1T1R, dl_arfcn=368500 (n3), dl_freq=1842.5 MHz, ...
Connected to AMF. Supported PLMNs: 00101
==== gNB started ===
```

With ZMQ, the gNB **waits** for the UE before its clock starts running. That's normal.

### Terminal 3: UE

```bash
sudo ip netns add ue1 2>/dev/null; sudo ip netns list    # ue1
cd ~/5g/srsRAN_4G/build/srsue/src
sudo ./srsue ~/5g/ue_zmq.conf
```

Expected UE output:

```
Attaching UE...
Random Access Transmission: prach_occasion=0, preamble_index=..., ra-rnti=..., tti=...
Random Access Complete.     c-rnti=0x4601, ta=0
RRC Connected
PDU Session Establishment successful. IP: 192.168.100.2
RRC NR reconfiguration successful.
```

The AMF (Terminal 1) should show `Registration complete` and the UE's IMSI. In the gNB console, type `t` + Enter to see live UE metrics (MCS, throughput, BLER).

---

## 11. Routing and connectivity tests

### 11.1 Routes

```bash
# Host → UE subnet goes via the UPF container
sudo ip route add 192.168.100.0/24 via 172.22.0.8

# UE default route goes through the 5G tunnel
sudo ip netns exec ue1 ip route add default via 192.168.100.1 dev tun_srsue
sudo ip netns exec ue1 ip route
```

### 11.2 Ping

```bash
# Uplink: UE → UPF gateway
sudo ip netns exec ue1 ping -c 4 192.168.100.1

# Downlink: host → UE (use the IP srsUE printed)
ping -c 4 192.168.100.2

# UE → internet through the 5G core (N6 + NAT)
sudo ip netns exec ue1 ping -c 4 1.1.1.1
```

### 11.3 DNS inside the UE namespace (optional)

```bash
sudo mkdir -p /etc/netns/ue1
echo "nameserver <your network DNS server>" | sudo tee /etc/netns/ue1/resolv.conf
sudo ip netns exec ue1 ping -c 2 google.com
```

### 11.4 Throughput with iperf3

```bash
# Server on the host (Docker bridge address)
iperf3 -s -B 172.22.0.1

# Uplink (UE → host), in another terminal
sudo ip netns exec ue1 iperf3 -c 172.22.0.1 -i 1 -t 30

# Downlink (host → UE)
sudo ip netns exec ue1 iperf3 -c 172.22.0.1 -i 1 -t 30 -R
```

ZMQ throughput depends on CPU speed. It's a functional test, not a performance benchmark.

### 11.5 Capture the 5G traffic

```bash
# N2 (NGAP/NAS) and N3 (GTP-U) on the Docker bridge
sudo tcpdump -i $(ip -br link | awk '/^br-/{print $1; exit}') -w /tmp/5g_core.pcap 'sctp or udp port 2152'
```

Open the capture in Wireshark. With `NEA0` (null ciphering, the Open5GS default first choice), the NAS registration and authentication messages are readable, which is useful for security studies.

---

## 12. Stop the network

```bash
# Terminal 3: Ctrl+C (srsUE)
# Terminal 2: Ctrl+C (gNB)
cd ~/5g/docker_open5gs && docker compose -f sa-deploy.yaml down
sudo ip netns delete ue1                             # optional
sudo ip route del 192.168.100.0/24 via 172.22.0.8    # optional
```

---

## 13. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| gNB: `Invalid radio type zmq` / zmq missing from `Available radio types` | OCUDU built without ZMQ | Rebuild in `build_zmq` with `-DENABLE_EXPORT=ON -DENABLE_ZEROMQ=ON` (section 5) |
| srsUE: `Supported RF device list` lacks `zmq` | `libzmq3-dev` missing at build time | Install it, delete `build/`, rebuild srsUE |
| Nothing happens after both start | Ports not crossed | gNB `tx=2000, rx=2001` and UE `tx=2001, rx=2000` |
| `base_srate` / `srate` errors | Rates differ between gNB and UE | Same `srate` and `base_srate` (23.04e6) on both |
| UE stuck at `Attaching UE...`, no RACH | Too few CPU cores / slow VM | ≥ 6 cores, close other loads, give the VM more vCPUs |
| UE: `Error opening netns` | Namespace missing | `sudo ip netns add ue1` |
| gNB: no `Connected to AMF` | Core not running / wrong IPs | `ping 172.22.0.10`, `addrs`/`bind_addrs` as in section 8 |
| AMF: authentication failure | K/OPc/IMSI differ between DB and `ue_zmq.conf` | Re-add the subscriber with the same values (section 7) |
| AMF: registration rejected, PLMN not allowed | PLMN/TAC mismatch | `00101` and TAC `1` in `.env`, gNB and IMSI prefix |
| Registered but `PDU Session Establishment` fails | DNN mismatch | `srsapn` in SMF/UPF, subscriber and `[nas] apn` |
| UE has IP but can't ping out | Missing routes | Section 11.1 routes. `docker exec upf ping 8.8.8.8` must work |
| Ping by IP works, names don't | DNS | Section 11.3, and your network's DNS in `.env` |
| `docker build`: `Could not resolve host` | DNS blocked inside containers | Section 3.2 |
| Restarting only the UE fails | ZMQ socket state | Restart **gNB then UE** together |

Logs: gNB `/tmp/gnb.log`, UE `/tmp/ue.log`, core `docker logs <amf|smf|upf|ausf|udm>`.

---

## 14. Next steps

- **Multiple UEs:** use a GNU Radio ZMQ broker to connect several srsUE instances to one gNB (see the srsRAN multi-UE tutorial in References).
- **Security experiments:** modify the core configs (e.g. integrity/ciphering order in the AMF), capture NAS/NGAP with Wireshark, or test SUCI concealment with home-network keys.
- **Move to real radio:** the core and subscriber steps are identical. Swap `ru_sdr` back to `uhd` and follow the [main guide](../README.md).

---

## 15. References

- Open5GS in Docker: <https://github.com/herlesupreeth/docker_open5gs>
- OCUDU installation (ZMQ build): <https://docs.ocudu.org/user_manual/installation/>
- OCUDU config reference: <https://docs.ocudu.org/user_manual/config_reference/>
- srsRAN Project, srsUE tutorial (ZMQ configs this guide is based on): <https://docs.srsran.com/projects/project/en/latest/tutorials/source/srsUE/source/index.html>
- srsRAN 4G (srsUE): <https://github.com/srsran/srsRAN_4G>
- srsRAN 4G ZeroMQ app note: <https://docs.srsran.com/projects/4g/en/latest/app_notes/source/zeromq/source/index.html>
- s5uishida, OCUDU with ZMQ: <https://github.com/s5uishida/build_ocudu_zmq>
