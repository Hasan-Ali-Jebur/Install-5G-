#!/usr/bin/env bash
# Add a consecutive range of subscribers for UERANSIM to the Open5GS DB.
#
# Usage: ./scripts/add_ueransim_subscribers.sh [COUNT] [FIRST_INDEX]
#   COUNT        number of subscribers (default 100)
#   FIRST_INDEX  index of the first IMSI (default 1001 -> 001010000001001)
#
# IMSI = MCC+MNC (00101) + 10-digit index. The range must match `supi` in
# configs/ueransim_ue.yaml, because `nr-ue -n N` counts up from that IMSI.
# IMSIs already in the DB are skipped, so the script is safe to re-run.
set -euo pipefail

COUNT="${1:-100}"
FIRST="${2:-1001}"
PLMN="${PLMN:-00101}"
K="${K:-00112233445566778899aabbccddeeff}"
OPC="${OPC:-63BFA50EE6523365FF14C1F45F88737D}"
DNN="${DNN:-srsapn}"
CONTAINER="${CONTAINER:-webui}"

if ! docker ps --format '{{.Names}}' | grep -qx "${CONTAINER}"; then
  echo "ERROR: container '${CONTAINER}' is not running" >&2
  exit 1
fi

# Same DB connection open5gs-dbctl uses inside the container.
mongo_eval() {
  docker exec "${CONTAINER}" sh -c "mongosh --quiet \"\${DB_URI:-mongodb://localhost/open5gs}\" --eval '$1'"
}

EXISTING=$(mongo_eval 'db.subscribers.find({},{imsi:1,_id:0}).toArray().map(d=>d.imsi).join(" ")' 2>/dev/null || true)
if [[ -z "${EXISTING}" ]]; then
  echo "Note: could not list existing subscribers (or DB is empty); duplicates are not checked."
fi

LAST=$((FIRST + COUNT - 1))
echo "Adding ${COUNT} subscribers: $(printf "${PLMN}%010d" "${FIRST}") .. $(printf "${PLMN}%010d" "${LAST}")  (DNN ${DNN})"

added=0; skipped=0
for ((i = FIRST; i <= LAST; i++)); do
  IMSI=$(printf "${PLMN}%010d" "${i}")
  if [[ " ${EXISTING} " == *" ${IMSI} "* ]]; then
    skipped=$((skipped + 1))
    continue
  fi
  docker exec "${CONTAINER}" misc/db/open5gs-dbctl add_ue_with_apn "${IMSI}" "${K}" "${OPC}" "${DNN}" >/dev/null
  added=$((added + 1))
  printf "\r  added %d" "${added}"
done
echo

echo "Added ${added}, skipped ${skipped} (already present)."
echo "Subscribers in DB: $(mongo_eval 'db.subscribers.countDocuments()' 2>/dev/null || echo '?')"
