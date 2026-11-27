# Multi-UE registration experiments: UERANSIM, capture and analysis

[← Back to README](../README.md) · Previous: [Guide 1: testbed setup](01-testbed-setup.md)

This guide adds **many simulated UEs** to the testbed from [guide 01](01-testbed-setup.md) and shows how to **capture and analyse** what the 5G core sees: N2 (NGAP/NAS) and the SBI (HTTP/2) traffic between the AMF and the other network functions.

It's built for control-plane research, for example studying UE registration behaviour at the AMF, building datasets and training detectors.

**Before you start:** the Open5GS core from guide 01 (sections 3–5) is running. OCUDU + srsUE (path A) can keep running at the same time, but they aren't required.

| Component | Address | Notes |
|---|---|---|
| AMF (N2) | `172.22.0.10:38412` | same core as guide 01 |
| OCUDU gNB | `172.22.0.1` | host side of the Docker bridge (guide 01) |
| **UERANSIM gNB** | **`172.22.0.200`** | extra address on the same bridge (step 3) |
| UERANSIM UEs | IMSI `001010000001001` … | own range, never clashes with srsUE `001010123456780` |
| UE IP pool | `192.168.100.0/24` | DNN `srsapn`, same as guide 01 |
| Prometheus | `172.22.0.36:9090` | AMF metrics |

**Steps**

1. [Get this repo on the testbed host](#1-get-this-repo-on-the-testbed-host)
2. [Install UERANSIM and the analysis tools](#2-install-ueransim-and-the-analysis-tools)
3. [Give UERANSIM its own IP on the bridge](#3-give-ueransim-its-own-ip-on-the-bridge)
4. [Add the UE subscribers](#4-add-the-ue-subscribers)
5. [Configure the gNB and UEs](#5-configure-the-gnb-and-ues)
6. [First run: 1 UE, then 10](#6-first-run-1-ue-then-10)
7. [Capture by hand](#7-capture-by-hand)
8. [Labelled experiment runs](#8-labelled-experiment-runs)
9. [Analyse a run](#9-analyse-a-run)
10. [Stop](#10-stop)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Get this repo on the testbed host

The configs and scripts used below live in this repository:

```bash
cd ~/5g
git clone https://github.com/Hasan-Ali-Jebur/Install-5G-.git
cd Install-5G-
chmod +x scripts/*.sh scripts/*.py
```

All commands from here on are run from `~/5g/Install-5G-` unless a `cd` says otherwise.

---

## 2. Install UERANSIM and the analysis tools

### 2.1 UERANSIM

```bash
sudo apt update
sudo apt install -y make gcc g++ libsctp-dev lksctp-tools iproute2 git
sudo snap install cmake --classic

cd ~/5g
git clone https://github.com/aligungr/UERANSIM
cd UERANSIM
make
ls build/          # nr-gnb  nr-ue  nr-cli  nr-binder
cd ~/5g/Install-5G-
```

### 2.2 Capture and analysis tools

```bash
./scripts/install_analysis_tools.sh
```

| Tool | Used for |
|---|---|
| `tcpdump` | capturing on the Docker bridge |
| `wireshark` / `tshark` | inspecting and exporting NGAP, NAS-5GS and SBI (HTTP/2) |
| `jq` | reading the Prometheus metric exports |
| Python venv `~/5g/analysis-venv` | `pandas`, `numpy`, `matplotlib`, `scapy`, `pyshark`, `scikit-learn`, `jupyterlab` |

When the installer asks *"Should non-superusers be able to capture packets?"*, answer **Yes**. Then log out and in again so the `wireshark` group applies.

---

## 3. Give UERANSIM its own IP on the bridge

OCUDU already binds N2 and **N3 (GTP-U, UDP 2152)** on `172.22.0.1`. A second gNB on the same address fails with `Address already in use`. So UERANSIM gets its own address, `172.22.0.200`, on the same Docker bridge:

```bash
./scripts/setup_ueransim_ip.sh
# Added 172.22.0.200/24 to br-xxxx
# OK: AMF 172.22.0.10 reachable from 172.22.0.200
```

> The address is lost on reboot and on `docker compose down` (the bridge is recreated). Re-run the script after either.

---

## 4. Add the UE subscribers

`nr-ue -n N` starts N UEs and **counts the IMSI up** from the first one, so the core needs a consecutive range. The script adds them with the same K/OPc as the srsUE in guide 01 (section 10.2) and the DNN `srsapn`:

```bash
./scripts/add_ueransim_subscribers.sh 100          # 001010000001001 … 001010000001100
```

- Optional second argument: the first index (default `1001`).
- Override the keys or DNN with environment variables: `K=... OPC=... DNN=... ./scripts/add_ueransim_subscribers.sh 100`.
- IMSIs already in the DB are skipped, so it's safe to re-run.
- Check them in the WebUI: `http://<host IP>:9999` (`admin` / `1423`).

---

## 5. Configure the gNB and UEs

```bash
cp configs/ueransim_gnb.yaml ~/5g/ueransim_gnb.yaml
cp configs/ueransim_ue.yaml  ~/5g/ueransim_ue.yaml
```

What matters in each file, and must match guide 01:

| File | Key | Value | Must match |
|---|---|---|---|
| [`ueransim_gnb.yaml`](../configs/ueransim_gnb.yaml) | `mcc` / `mnc` / `tac` | `001` / `01` / `1` | `MCC`, `MNC`, `TAC` in `.env` |
| | `nci` | `0x000000010` (gNB ID 1) | must differ from OCUDU's gNB ID |
| | `ngapIp`, `gtpIp` | `172.22.0.200` | step 3 |
| | `amfConfigs.address` | `172.22.0.10` | AMF container |
| [`ueransim_ue.yaml`](../configs/ueransim_ue.yaml) | `supi` | `imsi-001010000001001` | first IMSI from step 4 |
| | `key` / `op` / `opType` | lab K / OPc / `OPC` | subscriber DB |
| | `sessions.apn` | `srsapn` | SMF/UPF DNN (guide 01, 4.3) |
| | `gnbSearchList` | `127.0.0.1` | gNB `linkIp` |

`protectionScheme: 0` (null scheme) means the SUCI carries the MSIN in clear, so every UE is identifiable in the capture.

---

## 6. First run: 1 UE, then 10

Use three terminals.

```bash
# Terminal 1: AMF log
docker logs -f --tail 0 amf

# Terminal 2: UERANSIM gNB
cd ~/5g/UERANSIM
sudo ./build/nr-gnb -c ~/5g/ueransim_gnb.yaml
#   wait for: NG Setup procedure is successful

# Terminal 3: UEs
cd ~/5g/UERANSIM
sudo ./build/nr-ue -c ~/5g/ueransim_ue.yaml                  # 1 UE
#   Ctrl+C, then:
sudo ./build/nr-ue -c ~/5g/ueransim_ue.yaml -n 10            # 10 UEs at once
sudo ./build/nr-ue -c ~/5g/ueransim_ue.yaml -n 50 -t 2000    # 50 UEs, one every 2 s
```

| `nr-ue` option | Meaning |
|---|---|
| `-n N` | number of UEs (max 512 per process), IMSIs counted up from `supi` |
| `-i IMSI` | start from this IMSI instead of the one in the config |
| `-t MS` | delay in ms between UE starts, i.e. the **registration rate** |
| `-r` | don't create a route per UE TUN (use it for large N) |

**Check it worked:**

```bash
docker logs amf 2>&1 | grep -E "Number of gNBs|Registration complete" | tail
#   "Number of gNBs is now 2" when OCUDU is also connected

ip -br addr | grep uesimtun                 # one TUN per UE, 192.168.100.x
ping -c 3 -I uesimtun0 192.168.100.1        # uplink to the UPF

cd ~/5g/UERANSIM
./build/nr-cli --dump                       # all running UEs and gNBs
./build/nr-cli imsi-001010000001001 -e status
./build/nr-cli imsi-001010000001001 -e "deregister switch-off"
```

`deregister` accepts `normal`, `switch-off`, `disable-5g` and `remove-sim`.

---

## 7. Capture by hand

Capture on the **Docker bridge**. It sees N2 between any gNB on the host and the AMF, and all SBI traffic between the core containers, so you don't need tcpdump inside a container:

```bash
BR=$(ip -br addr | awk '/172\.22\.0\.1\//{print $1; exit}')
sudo tcpdump -i $BR -U -w ~/5g/test_run.pcap 'sctp or tcp port 7777'
#   add  or udp port 2152  for the N3 user plane
```

**Order for a clean capture:**

1. Start tcpdump.
2. Start the UEs.
3. Deregister the UEs, so the capture includes the de-registrations:
   ```bash
   cd ~/5g/UERANSIM
   for i in $(seq 1001 1010); do ./build/nr-cli imsi-00101000000$i -e "deregister switch-off"; done
   ```
4. Ctrl+C in the `nr-ue` terminal.
5. **Ctrl+C in the tcpdump terminal.** It flushes the file and prints the packet count. Don't close the terminal window instead, because that can truncate the file.

```bash
sudo chown $USER ~/5g/test_run.pcap
tshark -r ~/5g/test_run.pcap -Y "nas-5gs.mm.message_type == 0x41" | wc -l    # Registration Requests
```

---

## 8. Labelled experiment runs

For dataset collection, use `run_experiment.sh`. It does the whole sequence from step 7 for you and stores **one folder per run**:

```bash
# gNB must be running (step 6, terminal 2)
sudo ./scripts/run_experiment.sh -l benign -n 10 -t 1000 -H 30
sudo ./scripts/run_experiment.sh -l benign -n 50 -t 5000 -H 60
sudo ./scripts/run_experiment.sh -l benign_burst -n 50 -t 100 -H 30   # e.g. a mass re-registration after an outage
```

| Option | Meaning | Default |
|---|---|---|
| `-l` | label (folder name and `meta.json`) | required |
| `-n` | number of UEs | 10 |
| `-t` | ms between UE starts | 1000 |
| `-H` | seconds registered after the last UE starts | 30 |
| `-f` | first IMSI index | 1001 |
| `-c` | UE config | `~/5g/ueransim_ue.yaml` |
| `-g` | also capture GTP-U (N3) | off |
| `-D` | don't deregister at the end | deregister |

Output in `~/5g/runs/<UTC time>_<label>_n<UES>_t<TEMPO>/`:

| File | Content |
|---|---|
| `capture.pcap` | N2 (NGAP/NAS) + SBI (HTTP/2 on 7777) [+ N3] |
| `ue.log`, `nr-cli.log` | UERANSIM output |
| `amf.log`, `ausf.log`, `udm.log`, `smf.log` | core logs for the run window only |
| `metrics.json` | AMF metrics from Prometheus, 1 s resolution (if reachable) |
| `meta.json` | parameters, label, IMSI range, registered count, start/end time |

> Keep the gNB and core running between runs. Only the UEs and the capture restart. Leave a few seconds between runs so the AMF releases the old contexts.

---

## 9. Analyse a run

### 9.1 Wireshark

```bash
wireshark ~/5g/runs/<run>/capture.pcap
```

- **Edit → Preferences → Protocols → NAS-5GS →** tick *Try to detect and decode 5G-EA0 ciphered messages*. Open5GS picks NEA0 first, so the NAS after Security Mode becomes readable.
- **Analyze → Decode As… →** TCP port `7777` → `HTTP2`, to see the SBI calls.

Useful display filters:

| Filter | Shows |
|---|---|
| `ngap` | all N2 |
| `nas-5gs.mm.message_type == 0x41` | Registration Request |
| `nas-5gs.mm.message_type == 0x44` | Registration Reject |
| `nas-5gs.mm.message_type == 0x56` | Authentication Request |
| `nas-5gs.mm.5gmm_cause` | anything with a 5GMM cause (rejects, failures) |
| `nas-5gs.mm.suci.msin == "0000001001"` | one UE |
| `http2.headers.path contains "ue-authentications"` | AMF → AUSF authentication |
| `http2.headers.path contains "nudm-uecm"` | AMF → UDM context management |

5GMM message types (TS 24.501): `0x41` Registration Request · `0x42` Accept · `0x43` Complete · `0x44` Reject · `0x45`/`0x46` UE-originated Deregistration Request/Accept · `0x56` Authentication Request · `0x57` Authentication Response · `0x59` Authentication Failure · `0x5d` Security Mode Command · `0x5e` Security Mode Complete.

### 9.2 Export to CSV

```bash
./scripts/pcap_to_csv.sh ~/5g/runs/<run>
#   nas_ngap.csv  one row per NGAP/NAS packet: time, IPs, NGAP procedure, RAN/AMF UE IDs,
#                 security header, NAS message type, registration type, SUCI MSIN, 5GMM cause
#   sbi.csv       one row per SBI HTTP/2 header frame: time, stream, method, path, status
```

The script checks every field against your tshark version and skips unknown ones, so older Wireshark builds don't abort.

### 9.3 Quick summary

```bash
source ~/5g/analysis-venv/bin/activate
python scripts/registration_summary.py ~/5g/runs/<run>
```

It prints NAS message counts, Registration Requests per second (average and peak), and per-UE registration counts with mean inter-arrival time. Use it as a sanity check that each run did what its label says before you add it to a dataset.

### 9.4 AMF metrics

```bash
jq -r '.data.result[] | .metric.__name__' ~/5g/runs/<run>/metrics.json | sort -u
```

Grafana (`http://<host IP>:3000`) shows the same counters live.

---

## 10. Stop

```bash
# UEs: deregister (step 7) and Ctrl+C in the nr-ue terminal
# UERANSIM gNB: Ctrl+C
sudo pkill nr-ue; sudo pkill nr-gnb          # if anything is left over
# The core and OCUDU: guide 01, section 13
```

---

## 11. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| gNB: `bind failed` / `Address already in use` (2152) | `gtpIp` is still `172.22.0.1` (OCUDU's), or the alias is missing | Step 3; `gtpIp: 172.22.0.200` |
| gNB: SCTP connection refused / NG Setup fails | Alias gone after reboot or `compose down` | `./scripts/setup_ueransim_ip.sh` |
| NG Setup failure: unknown PLMN / TAC | `mcc`/`mnc`/`tac` differ from `.env` | Step 5 table |
| UE: `Cannot find SUCI` / not registered | IMSI not in the DB, or `supi` outside the added range | `./scripts/add_ueransim_subscribers.sh` with the right range |
| AMF: `MAC failure` / Authentication Reject | K, OPc or `opType` differ from the DB | Same values in `ueransim_ue.yaml` and the script |
| Registration OK, PDU session rejected | `apn` isn't `srsapn` | `sessions.apn: 'srsapn'` |
| Only some of N UEs register | Too many at once for the machine | Raise `-t`, add `-r`, check `ue.log` |
| `nr-cli`: node not found | UE process already stopped, or IMSI typo | `./build/nr-cli --dump` |
| No NAS details after Security Mode in Wireshark | Null-decipher preference off | 9.1, or use `pcap_to_csv.sh` (sets it) |
| `metrics.json` missing | Prometheus not reachable at `172.22.0.36:9090` | `PROM=http://<ip>:9090 sudo -E ./scripts/run_experiment.sh ...` |
| Ping via `uesimtun0` fails but registration works | Routing clash with guide 01 host routes | Not needed for control-plane data; test with `-g` captures only if you need N3 |
