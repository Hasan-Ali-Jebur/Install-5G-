#!/usr/bin/env bash
# Give UERANSIM its own address (172.22.0.200) on the docker_open5gs bridge,
# so it does not clash with OCUDU, which binds N2/N3 on 172.22.0.1.
#
# Re-run after every reboot and after `docker compose down` (the bridge is recreated).
set -euo pipefail

ALIAS_IP="${ALIAS_IP:-172.22.0.200}"
AMF_IP="${AMF_IP:-172.22.0.10}"

BR=$(ip -br addr | awk '/172\.22\.0\.1\//{print $1; exit}')
if [[ -z "${BR}" ]]; then
  echo "ERROR: no interface with 172.22.0.1 found. Is the core running? (docker compose -f sa-deploy.yaml up -d)" >&2
  exit 1
fi

if ip -br addr show dev "${BR}" | grep -q "${ALIAS_IP}/"; then
  echo "${ALIAS_IP} already on ${BR}"
else
  sudo ip addr add "${ALIAS_IP}/24" dev "${BR}"
  echo "Added ${ALIAS_IP}/24 to ${BR}"
fi

if ping -c 2 -W 1 -I "${ALIAS_IP}" "${AMF_IP}" >/dev/null; then
  echo "OK: AMF ${AMF_IP} reachable from ${ALIAS_IP}"
else
  echo "WARNING: AMF ${AMF_IP} not reachable from ${ALIAS_IP}" >&2
  exit 1
fi
