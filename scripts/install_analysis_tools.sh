#!/usr/bin/env bash
# Install the tools used to capture and analyse 5G core traffic (guide 02, step 1).
#
#   tcpdump            capture on the Docker bridge
#   wireshark/tshark   inspect and export NGAP, NAS-5GS and SBI (HTTP/2)
#   jq                 read Prometheus metric exports
#   Python venv        pandas / matplotlib / scapy / pyshark / jupyter for feature extraction and ML
set -euo pipefail

VENV="${VENV:-$HOME/5g/analysis-venv}"

sudo apt update
# Answer "Yes" when asked whether non-superusers may capture packets.
sudo apt install -y tcpdump wireshark tshark jq python3-venv python3-pip

# Let your user capture without sudo (takes effect after logging out and in again).
sudo usermod -aG wireshark "$USER"

python3 -m venv "${VENV}"
# shellcheck disable=SC1091
source "${VENV}/bin/activate"
pip install --upgrade pip
pip install pandas numpy matplotlib scapy pyshark scikit-learn jupyterlab

echo
echo "Done."
echo "  tshark:  $(tshark --version | head -1)"
echo "  venv:    ${VENV}  (activate with: source ${VENV}/bin/activate)"
echo "Log out and in again so the 'wireshark' group applies."
