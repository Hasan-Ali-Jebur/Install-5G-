#!/usr/bin/env bash
# Export a run's capture to CSV for analysis / ML.
#
# Usage: ./scripts/pcap_to_csv.sh <run folder | capture.pcap>
#
# Writes next to the pcap:
#   nas_ngap.csv  one row per NGAP/NAS-5GS packet (timing, UE IDs, NAS message type,
#                 registration type, SUCI MSIN, 5GMM cause, ...)
#   sbi.csv       one row per SBI HTTP/2 header frame (AMF <-> AUSF/UDM/SMF/..., via SCP)
#
# NAS after Security Mode is only readable because Open5GS picks NEA0 (null
# ciphering) first; `nas-5gs.null_decipher` tells Wireshark to decode it.
set -euo pipefail

IN="${1:?usage: $0 <run folder | capture.pcap>}"
[[ -d "${IN}" ]] && IN="${IN%/}/capture.pcap"
[[ -f "${IN}" ]] || { echo "ERROR: ${IN} not found" >&2; exit 1; }
OUT_DIR=$(dirname "${IN}")

command -v tshark >/dev/null || { echo "ERROR: tshark missing (scripts/install_analysis_tools.sh)" >&2; exit 1; }

OPTS=(-o "nas-5gs.null_decipher:TRUE" -d "tcp.port==7777,http2")
CSV=(-T fields -E header=y -E 'separator=,' -E quote=d -E occurrence=a -E aggregator=';')

# Keep only fields this tshark version knows, so older Wireshark builds don't abort.
KNOWN=$(tshark -G fields 2>/dev/null | cut -f3)
pick() {
  local out=()
  for f in "$@"; do
    if grep -qx -- "${f}" <<<"${KNOWN}"; then out+=(-e "${f}"); else echo "  (field ${f} not in this tshark, skipped)" >&2; fi
  done
  printf '%s\n' "${out[@]}"
}

mapfile -t NAS_FIELDS < <(pick \
  frame.number frame.time_epoch ip.src ip.dst \
  ngap.procedureCode ngap.RAN_UE_NGAP_ID ngap.AMF_UE_NGAP_ID \
  nas-5gs.security_header_type nas-5gs.mm.message_type nas-5gs.mm.5gs_reg_type \
  nas-5gs.mm.suci.msin nas-5gs.mm.5gmm_cause)

mapfile -t SBI_FIELDS < <(pick \
  frame.number frame.time_epoch ip.src ip.dst tcp.srcport tcp.dstport \
  http2.streamid http2.headers.method http2.headers.path http2.headers.status)

echo "Reading ${IN}"
tshark -r "${IN}" "${OPTS[@]}" -Y "ngap || nas-5gs" "${CSV[@]}" "${NAS_FIELDS[@]}" >"${OUT_DIR}/nas_ngap.csv"
tshark -r "${IN}" "${OPTS[@]}" -Y "http2.headers.method || http2.headers.status" "${CSV[@]}" "${SBI_FIELDS[@]}" >"${OUT_DIR}/sbi.csv"

echo "  nas_ngap.csv: $(($(wc -l <"${OUT_DIR}/nas_ngap.csv") - 1)) rows"
echo "  sbi.csv:      $(($(wc -l <"${OUT_DIR}/sbi.csv") - 1)) rows"
echo "Registration Requests (0x41): $(tshark -r "${IN}" "${OPTS[@]}" -Y 'nas-5gs.mm.message_type == 0x41' 2>/dev/null | wc -l)"
