#!/usr/bin/env python3
"""Quick sanity summary of one run, from the CSV written by pcap_to_csv.sh.

Usage (inside the analysis venv):
    python scripts/registration_summary.py ~/5g/runs/<run folder>

Prints NAS message counts, Registration Requests per second, and per-UE
(SUCI MSIN) registration counts and inter-arrival times.
"""
import json
import sys
from pathlib import Path

import pandas as pd

# 5GMM message types (3GPP TS 24.501, Table 8.2.1.1)
MM_TYPES = {
    0x41: "RegistrationRequest", 0x42: "RegistrationAccept", 0x43: "RegistrationComplete",
    0x44: "RegistrationReject", 0x45: "DeregRequest(UE-orig)", 0x46: "DeregAccept(UE-orig)",
    0x47: "DeregRequest(UE-term)", 0x48: "DeregAccept(UE-term)", 0x4C: "ServiceRequest",
    0x4D: "ServiceReject", 0x4E: "ServiceAccept", 0x56: "AuthenticationRequest",
    0x57: "AuthenticationResponse", 0x58: "AuthenticationReject", 0x59: "AuthenticationFailure",
    0x5A: "AuthenticationResult", 0x5B: "IdentityRequest", 0x5C: "IdentityResponse",
    0x5D: "SecurityModeCommand", 0x5E: "SecurityModeComplete", 0x5F: "SecurityModeReject",
    0x64: "5GMMStatus", 0x67: "ULNASTransport", 0x68: "DLNASTransport",
}


def to_int(v):
    try:
        return int(str(v), 0)
    except ValueError:
        return None


def main(run_dir: Path) -> None:
    df = pd.read_csv(run_dir / "nas_ngap.csv", dtype=str)
    meta_file = run_dir / "meta.json"
    if meta_file.exists():
        print("Run:", json.loads(meta_file.read_text()))

    # A packet can carry several NAS messages (';'-separated); one row per message.
    nas = df.dropna(subset=["nas-5gs.mm.message_type"]).copy()
    nas["msg"] = nas["nas-5gs.mm.message_type"].str.split(";")
    nas = nas.explode("msg")
    nas["msg_type"] = nas["msg"].map(to_int)
    nas["msg_name"] = nas["msg_type"].map(lambda t: MM_TYPES.get(t, f"0x{t:02x}" if t is not None else "?"))
    nas["t"] = nas["frame.time_epoch"].astype(float)
    t0 = nas["t"].min()

    print("\nNAS 5GMM messages:")
    print(nas["msg_name"].value_counts().to_string())

    reg = nas[nas["msg_type"] == 0x41].copy()
    if reg.empty:
        print("\nNo Registration Requests found.")
        return

    reg["sec"] = (reg["t"] - t0).astype(int)
    per_sec = reg.groupby("sec").size()
    span = per_sec.index.max() + 1
    print(f"\nRegistration Requests: {len(reg)} over {span} s  "
          f"(average {len(reg) / span:.2f}/s, peak {per_sec.max()} in one second)")

    if "nas-5gs.mm.suci.msin" in reg:
        reg["msin"] = reg["nas-5gs.mm.suci.msin"].fillna("(GUTI)")
        per_ue = reg.groupby("msin")["t"].agg(["count", lambda s: s.sort_values().diff().mean()])
        per_ue.columns = ["registrations", "mean_interarrival_s"]
        print("\nPer UE (SUCI MSIN):")
        print(per_ue.to_string())


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]).expanduser())
