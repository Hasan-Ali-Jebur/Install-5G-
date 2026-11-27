#!/usr/bin/env bash
# One labelled experiment run = one folder with capture + logs + metrics + metadata.
#
# Usage (needs root for tcpdump and the UE TUN interfaces):
#   sudo ./scripts/run_experiment.sh -l LABEL [-n UES] [-t TEMPO_MS] [-H HOLD_S]
#                                    [-f FIRST_INDEX] [-c UE_CONFIG] [-g] [-D]
#
#   -l  label written into the folder name and meta.json (e.g. benign, attack)   [required]
#   -n  number of UEs                                    (default 10, max 512 per nr-ue)
#   -t  delay between UE starts, ms (registration rate)  (default 1000)
#   -H  seconds to stay registered after the last UE starts  (default 30)
#   -f  first IMSI index, 1001 -> imsi-001010000001001   (default 1001)
#   -c  UE config                                        (default ~/5g/ueransim_ue.yaml)
#   -g  also capture GTP-U user plane (udp 2152)         (default: control plane only)
#   -D  do NOT deregister at the end (UEs just disappear)
#
# Prerequisites: core running, setup_ueransim_ip.sh done, nr-gnb running,
# subscribers added (add_ueransim_subscribers.sh).
#
# Output: ~/5g/runs/<UTC time>_<label>_n<UES>_t<TEMPO>/
#   capture.pcap   N2 (NGAP/NAS) + SBI (HTTP/2 on 7777) [+ N3]
#   ue.log         nr-ue output
#   amf.log ...    core NF logs for the run window
#   metrics.json   Open5GS AMF metrics from Prometheus (if reachable)
#   meta.json      run parameters and timestamps (your labels)
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo $0 $*" >&2
  exit 1
fi

REAL_USER="${SUDO_USER:-root}"
REAL_HOME=$(getent passwd "${REAL_USER}" | cut -d: -f6)

LABEL=""; UES=10; TEMPO=1000; HOLD=30; FIRST=1001
UE_CFG="${REAL_HOME}/5g/ueransim_ue.yaml"
UERANSIM_DIR="${UERANSIM_DIR:-${REAL_HOME}/5g/UERANSIM}"
RUNS_DIR="${RUNS_DIR:-${REAL_HOME}/5g/runs}"
PROM="${PROM:-http://172.22.0.36:9090}"
PLMN="${PLMN:-00101}"
WITH_GTP=0; DEREGISTER=1

while getopts "l:n:t:H:f:c:gD" opt; do
  case $opt in
    l) LABEL=$OPTARG ;;
    n) UES=$OPTARG ;;
    t) TEMPO=$OPTARG ;;
    H) HOLD=$OPTARG ;;
    f) FIRST=$OPTARG ;;
    c) UE_CFG=$OPTARG ;;
    g) WITH_GTP=1 ;;
    D) DEREGISTER=0 ;;
    *) sed -n '2,30p' "$0"; exit 1 ;;
  esac
done

[[ -n "${LABEL}" ]] || { echo "ERROR: -l LABEL is required" >&2; exit 1; }
[[ -f "${UE_CFG}" ]] || { echo "ERROR: UE config not found: ${UE_CFG}" >&2; exit 1; }
[[ -x "${UERANSIM_DIR}/build/nr-ue" ]] || { echo "ERROR: nr-ue not found in ${UERANSIM_DIR}/build" >&2; exit 1; }
pgrep -x nr-gnb >/dev/null || { echo "ERROR: nr-gnb is not running (start it first)" >&2; exit 1; }
(( UES >= 1 && UES <= 512 )) || { echo "ERROR: -n must be 1..512" >&2; exit 1; }

BR=$(ip -br addr | awk '/172\.22\.0\.1\//{print $1; exit}')
[[ -n "${BR}" ]] || { echo "ERROR: Docker bridge 172.22.0.1 not found" >&2; exit 1; }

FILTER="sctp or tcp port 7777"
(( WITH_GTP )) && FILTER="${FILTER} or udp port 2152"

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
RUN="${RUNS_DIR}/${STAMP}_${LABEL}_n${UES}_t${TEMPO}"
mkdir -p "${RUN}"

FIRST_IMSI=$(printf "${PLMN}%010d" "${FIRST}")
LAST_IMSI=$(printf "${PLMN}%010d" $((FIRST + UES - 1)))

TCPDUMP_PID=""; UE_PID=""
cleanup() {
  [[ -n "${UE_PID}" ]] && kill -INT "${UE_PID}" 2>/dev/null && wait "${UE_PID}" 2>/dev/null || true
  [[ -n "${TCPDUMP_PID}" ]] && kill -INT "${TCPDUMP_PID}" 2>/dev/null && wait "${TCPDUMP_PID}" 2>/dev/null || true
  chown -R "${REAL_USER}:" "${RUN}" 2>/dev/null || true
}
trap cleanup EXIT

echo "== Run ${RUN##*/}"
echo "   UEs ${UES} (${FIRST_IMSI}..${LAST_IMSI}), one every ${TEMPO} ms, hold ${HOLD} s"
echo "   capture on ${BR}: ${FILTER}"

# 1. Capture first
tcpdump -i "${BR}" -U -w "${RUN}/capture.pcap" "${FILTER}" 2>"${RUN}/tcpdump.log" &
TCPDUMP_PID=$!
sleep 2
START_EPOCH=$(date +%s.%N)

# 2. UEs
"${UERANSIM_DIR}/build/nr-ue" -c "${UE_CFG}" -i "${FIRST_IMSI}" -n "${UES}" -t "${TEMPO}" -r \
  >"${RUN}/ue.log" 2>&1 &
UE_PID=$!

RAMP=$(( (UES - 1) * TEMPO / 1000 + 1 ))
echo "   starting UEs (~${RAMP} s), then holding ${HOLD} s ..."
sleep $((RAMP + HOLD))

REGISTERED=$(grep -c "Initial Registration is successful" "${RUN}/ue.log" || true)
echo "   registered: ${REGISTERED}/${UES}"

# 3. Clean deregistration
if (( DEREGISTER )); then
  echo "   deregistering ..."
  for ((i = FIRST; i < FIRST + UES; i++)); do
    "${UERANSIM_DIR}/build/nr-cli" "imsi-$(printf "${PLMN}%010d" "${i}")" \
      -e "deregister switch-off" >>"${RUN}/nr-cli.log" 2>&1 || true
  done
  sleep 3
fi

# 4. Stop UEs, then capture
kill -INT "${UE_PID}" 2>/dev/null || true
wait "${UE_PID}" 2>/dev/null || true
UE_PID=""
sleep 2
END_EPOCH=$(date +%s.%N)
kill -INT "${TCPDUMP_PID}" 2>/dev/null || true
wait "${TCPDUMP_PID}" 2>/dev/null || true
TCPDUMP_PID=""

# 5. Core logs for the run window
SINCE=${START_EPOCH%.*}; UNTIL=$(( ${END_EPOCH%.*} + 1 ))
for nf in amf ausf udm smf; do
  docker logs --since "${SINCE}" --until "${UNTIL}" "${nf}" >"${RUN}/${nf}.log" 2>&1 || true
done

# 6. AMF metrics from Prometheus (optional)
if curl -sf -m 3 "${PROM}/-/ready" >/dev/null 2>&1; then
  curl -sf -G "${PROM}/api/v1/query_range" \
    --data-urlencode 'query={__name__=~"fivegs_amffunction_.*|ran_ue|gnb|amf_session"}' \
    --data-urlencode "start=${START_EPOCH}" --data-urlencode "end=${END_EPOCH}" \
    --data-urlencode "step=1" >"${RUN}/metrics.json" || echo "   (metrics query failed)"
else
  echo "   (Prometheus not reachable at ${PROM}, metrics skipped)"
fi

# 7. Metadata
cat >"${RUN}/meta.json" <<EOF
{
  "label": "${LABEL}",
  "num_ues": ${UES},
  "tempo_ms": ${TEMPO},
  "hold_s": ${HOLD},
  "first_imsi": "${FIRST_IMSI}",
  "last_imsi": "${LAST_IMSI}",
  "registered": ${REGISTERED},
  "deregistered": $( (( DEREGISTER )) && echo true || echo false ),
  "gnb_ngap_ip": "172.22.0.200",
  "capture_filter": "${FILTER}",
  "start_epoch": ${START_EPOCH},
  "end_epoch": ${END_EPOCH}
}
EOF

echo "== Done: ${RUN}"
ls -lh "${RUN}"
