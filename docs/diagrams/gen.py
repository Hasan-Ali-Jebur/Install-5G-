"""Generate srsRAN-style architecture diagrams (original drawings) as SVG."""
import sys, os

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)

FONT = "Open Sans, DejaVu Sans, Arial, Helvetica, sans-serif"
BLUE = "#cfe3f7"; BLUE_D = "#a9c8e8"; BLUE_DD = "#8fb3d9"
GREEN = "#d6efd2"; ORANGE = "#fde2c4"; PURPLE = "#e4dcf3"; YELLOW = "#fff4c2"
MACHINE = "#efefef"; CORE_BG = "#dcdcdc"; STROKE = "#333"


class SVG:
    def __init__(self, w, h):
        self.w, self.h, self.parts = w, h, []

    def add(self, s):
        self.parts.append(s)

    def rect(self, x, y, w, h, fill, rx=10, stroke=STROKE, sw=1.5, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def text(self, x, y, s, size=15, weight="normal", anchor="middle", fill="#111", italic=False):
        st = ' font-style="italic"' if italic else ""
        s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.add(f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" fill="{fill}"{st}>{s}</text>')

    def lines(self, x, y, items, size=13, gap=17, **kw):
        for i, s in enumerate(items):
            self.text(x, y + i * gap, s, size=size, **kw)

    def box(self, x, y, w, h, title, sub=None, fill=BLUE, size=17, subsize=12):
        self.rect(x, y, w, h, fill)
        if sub:
            ty = y + h / 2 - (len(sub) * 15) / 2 + 2
            self.text(x + w / 2, ty, title, size=size, weight="bold")
            self.lines(x + w / 2, ty + 19, sub, size=subsize, gap=15, fill="#333")
        else:
            self.text(x + w / 2, y + h / 2 + 6, title, size=size, weight="bold")

    def server(self, x, y, w, h, label, sub=None, d=10, fill=BLUE):
        """3D server block like the srsRAN core drawings."""
        self.add(f'<polygon points="{x},{y} {x+d},{y-d} {x+w+d},{y-d} {x+w},{y}" fill="{BLUE_D}" stroke="{STROKE}" stroke-width="1.2"/>')
        self.add(f'<polygon points="{x+w},{y} {x+w+d},{y-d} {x+w+d},{y+h-d} {x+w},{y+h}" fill="{BLUE_DD}" stroke="{STROKE}" stroke-width="1.2"/>')
        self.rect(x, y, w, h, fill, rx=0, sw=1.2)
        if sub:
            self.text(x + w / 2, y + h / 2 - 2, label, size=14, weight="bold")
            self.text(x + w / 2, y + h / 2 + 15, sub, size=11, fill="#333")
        else:
            self.text(x + w / 2, y + h / 2 + 5, label, size=14, weight="bold")

    def line(self, x1, y1, x2, y2, dash=None, color=STROKE, sw=1.6, start=False, end=True):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        ms = ' marker-start="url(#arrs)"' if start else ""
        me = ' marker-end="url(#arr)"' if end else ""
        self.add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{sw}"{d}{ms}{me}/>')

    def path(self, d, dash=None, sw=1.6, color=STROKE, start=False, end=True, fill="none"):
        da = f' stroke-dasharray="{dash}"' if dash else ""
        ms = ' marker-start="url(#arrs)"' if start else ""
        me = ' marker-end="url(#arr)"' if end else ""
        self.add(f'<path d="{d}" fill="{fill}" stroke="{color}" stroke-width="{sw}"{da}{ms}{me}/>')

    def label(self, x, y, s, size=14, weight="bold", fill="#111", bg=True, anchor="middle"):
        if bg:
            w = len(s) * size * 0.58 + 10
            bx = x - w / 2 if anchor == "middle" else x - 5
            self.add(f'<rect x="{bx}" y="{y-size}" width="{w}" height="{size+7}" rx="3" fill="#ffffff" opacity="0.92"/>')
        self.text(x, y, s, size=size, weight=weight, fill=fill, anchor=anchor)

    def waves(self, x, y, n=3, r0=14, step=10, right=True):
        sgn = 1 if right else -1
        for i in range(n):
            r = r0 + i * step
            self.add(f'<path d="M {x} {y-r} A {r} {r} 0 0 {1 if right else 0} {x} {y+r}" fill="none" stroke="#2b6cb0" stroke-width="2"/>')

    def phone(self, x, y, w=62, h=112):
        self.rect(x, y, w, h, "#2d3748", rx=10, sw=1.5)
        self.rect(x + 5, y + 12, w - 10, h - 26, "#e2f0fd", rx=3, stroke="#2d3748", sw=0.8)
        self.add(f'<circle cx="{x+w/2}" cy="{y+h-7}" r="3" fill="#cbd5e0"/>')
        self.text(x + w / 2, y + h / 2 + 4, "5G", size=15, weight="bold", fill="#2b6cb0")

    def cloud(self, cx, cy, label):
        self.add(f'<g fill="#ffffff" stroke="{STROKE}" stroke-width="1.5">'
                 f'<ellipse cx="{cx-34}" cy="{cy+6}" rx="34" ry="22"/><ellipse cx="{cx+34}" cy="{cy+6}" rx="34" ry="22"/>'
                 f'<ellipse cx="{cx}" cy="{cy-8}" rx="40" ry="28"/></g>'
                 f'<g fill="#ffffff"><ellipse cx="{cx-30}" cy="{cy+6}" rx="31" ry="19"/><ellipse cx="{cx+30}" cy="{cy+6}" rx="31" ry="19"/>'
                 f'<ellipse cx="{cx}" cy="{cy-6}" rx="37" ry="25"/></g>')
        self.text(cx, cy + 6, label, size=15, weight="bold")

    def save(self, name, title):
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{title}">'
                f'<title>{title}</title>'
                '<defs>'
                f'<marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{STROKE}"/></marker>'
                f'<marker id="arrs" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{STROKE}"/></marker>'
                '</defs>'
                f'<rect x="0" y="0" width="{self.w}" height="{self.h}" fill="#ffffff"/>')
        open(os.path.join(OUT, name), "w").write(head + "\n".join(self.parts) + "</svg>\n")


def core_block(s, x, y, w=520, h=470, compact=False):
    """Open5GS-in-Docker block: SBI NFs, AMF, SMF, UPF, DB, WebUI. Returns anchor points."""
    s.rect(x, y, w, h, CORE_BG, rx=40)
    s.text(x + w / 2, y - 12, "Open5GS 5G Core (Docker)", size=17, weight="bold")
    # bridge bar
    s.rect(x + 20, y + h - 48, w - 40, 30, YELLOW, rx=6)
    s.text(x + w / 2, y + h - 28, "Docker bridge  172.22.0.0/24   (host = 172.22.0.1)", size=13, weight="bold")
    # SBI functions
    s.rect(x + 30, y + 22, w - 60, 28, BLUE, rx=4)
    s.text(x + w / 2, y + 42, "5G Core Functions  (SBI · HTTP/2 :7777)", size=14, weight="bold")
    nfs = [("NRF", ".12"), ("SCP", ".35"), ("AUSF", ".11"), ("UDM", ".13"),
           ("UDR", ".14"), ("PCF", ".27"), ("NSSF", ".28"), ("BSF", ".29")]
    bw, bh, gx = 92, 46, 20
    for i, (n, ip) in enumerate(nfs):
        cx = x + 34 + (i % 4) * (bw + gx + 6)
        cy = y + 76 + (i // 4) * (bh + 22)
        s.server(cx, cy, bw, bh, n, ip, d=8)
    # main NFs: AMF and UPF on the left (facing the gNB)
    amf = (x + 34, y + 222, 118, 62)
    smf = (x + 214, y + 222, 118, 62)
    upf = (x + 34, y + 318, 118, 62)
    s.server(*amf, "AMF", "172.22.0.10")
    s.server(*smf, "SMF", "172.22.0.7")
    s.server(*upf, "UPF", "172.22.0.8")
    # N4 SMF <-> UPF
    s.path(f"M {smf[0]+40} {smf[1]+smf[3]} L {upf[0]+upf[2]+2} {upf[1]+30}", start=True)
    s.label(smf[0] + 2, upf[1] - 4, "N4", size=12)
    # ogstun next to UPF
    s.rect(x + 214, y + 330, 132, 44, ORANGE, rx=6)
    s.text(x + 280, y + 348, "ogstun", size=13, weight="bold")
    s.text(x + 280, y + 365, "192.168.100.1/24", size=11, fill="#333")
    s.line(upf[0] + upf[2] + 10, upf[1] + 44, x + 214, y + 352, start=True, end=False)
    # DB + WebUI on the right
    s.server(x + 380, y + 230, 108, 44, "MongoDB", ".2", d=7, fill=GREEN)
    s.server(x + 380, y + 326, 108, 44, "WebUI", ":9999", d=7, fill=GREEN)
    s.line(x + 280, y + 374, x + 280, y + h - 48)
    s.label(x + 300, y + h - 60, "N6", size=12, anchor="start")
    tun = (x + w / 2, y + h - 18)
    return {"amf": amf, "upf": upf, "tun": tun, "x": x, "y": y, "w": w, "h": h}


# ---------------------------------------------------------------- overview
s = SVG(1500, 790)
s.rect(20, 60, 1460, 710, MACHINE, rx=14)
s.text(40, 755, "Host PC  ·  Ubuntu 22.04", size=16, weight="bold", anchor="start")
s.text(750, 34, "Install-5G  ·  one core, two RF options, two UE options", size=21, weight="bold")

# UE options column
s.text(185, 100, "UE options", size=16, weight="bold")
# srsUE (sim)
s.box(70, 125, 230, 120, "srsUE", ["srsRAN-4G · software USIM", "netns ue1 · tun_srsue", "192.168.100.x"], fill=PURPLE)
s.text(185, 268, "Simulated UE", size=13, italic=True, fill="#444")
# phone (real)
s.phone(80, 430)
s.text(111, 562, "Pixel 9 Pro", size=13, weight="bold")
s.text(111, 578, "+ test SIM", size=12, fill="#444")
s.waves(150, 486, right=True)
# X310
s.server(230, 440, 110, 90, "USRP X310", "UBX · RF A", d=10, fill="#e2e8f0")
s.text(187, 640, "Real phone (over the air)", size=13, italic=True, fill="#444")
s.label(205, 470, "n78", size=12)

# RF option labels
s.text(470, 100, "RF options", size=16, weight="bold")
# gNB
gx, gy, gw, gh = 560, 255, 230, 190
s.box(gx, gy, gw, gh, "gNB", ["OCUDU (split 8)", "ru_sdr: zmq | uhd", "binds 172.22.0.1"], size=22)
s.text(gx + gw / 2, gy - 12, "OCUDU", size=16, weight="bold")
# ZMQ link
s.path(f"M 300 185 C 430 185 470 300 {gx} 300", dash="7,5", start=True)
s.label(470, 175, "ZMQ (IQ over TCP)", size=13)
s.text(470, 196, "tcp 2000 ⇄ 2001", size=12, fill="#333")
# 10GbE link
s.path(f"M 350 485 C 450 485 480 400 {gx} 400", start=True, sw=2.4)
s.label(448, 470, "UHD · 10 GbE", size=13)
s.text(450, 512, "192.168.40.1 ⇄ .2 · MTU 9000", size=12, fill="#333")

core = core_block(s, 890, 130)
amf, upf = core["amf"], core["upf"]
# N2/N3
s.path(f"M {gx+gw} 310 C 850 310 850 {amf[1]+31} {amf[0]} {amf[1]+31}", start=True)
s.label(866, 296, "N2 · NGAP/SCTP :38412", size=12)
s.path(f"M {gx+gw} 410 C 850 410 850 {upf[1]+31} {upf[0]} {upf[1]+31}", start=True)
s.label(858, 440, "N3 · GTP-U :2152", size=12)
# internet
tx, ty = core["tun"]
s.cloud(tx, ty + 95, "Internet")
s.line(tx, ty, tx, ty + 62)
s.label(tx + 12, ty + 38, "host NAT", size=12, anchor="start")
s.save("architecture-overview.svg", "Install-5G architecture overview")

# ---------------------------------------------------------------- ZMQ mode
s = SVG(1500, 760)
s.rect(20, 50, 1460, 690, MACHINE, rx=14)
s.text(40, 725, "Machine 1 (no radio hardware)", size=16, weight="bold", anchor="start")
s.text(750, 32, "Path A · ZMQ virtual radio + srsUE (simulation)", size=21, weight="bold")
# netns
s.rect(50, 150, 300, 250, "#f7f3fd", rx=18, dash="6,4", stroke="#7a5fb5")
s.text(200, 175, "network namespace  ue1", size=13, weight="bold", fill="#5a3f95")
s.box(80, 195, 240, 120, "srsUE", ["srsRAN-4G", "IMSI 001010123456780", "DNN srsapn"], fill=PURPLE)
s.rect(95, 335, 210, 46, ORANGE, rx=6)
s.text(200, 354, "tun_srsue", size=13, weight="bold")
s.text(200, 371, "192.168.100.x", size=12, fill="#333")
s.text(200, 130, "srsRAN-4G", size=16, weight="bold")
# gNB
gx, gy, gw, gh = 560, 200, 230, 160
s.box(gx, gy, gw, gh, "gNB", ["device_driver: zmq", "band 3 FDD · 20 MHz", "15 kHz SCS"], size=22)
s.text(gx + gw / 2, gy - 12, "OCUDU", size=16, weight="bold")
# ZMQ arrows
s.line(320, 235, gx, 235, dash="7,5")
s.label(440, 228, "UE TX → tcp://127.0.0.1:2001 → gNB RX", size=11)
s.line(gx, 300, 320, 300, dash="7,5")
s.label(440, 293, "gNB TX → tcp://127.0.0.1:2000 → UE RX", size=11)
s.text(440, 330, "ZMQ · baseband IQ samples · 23.04 MS/s", size=12, italic=True, fill="#444")
core = core_block(s, 900, 110)
tx, ty = core["tun"]; s.cloud(tx, ty + 95, "Internet"); s.line(tx, ty, tx, ty + 62); s.label(tx + 12, ty + 38, "host NAT", size=12, anchor="start")
amf, upf = core["amf"], core["upf"]
s.path(f"M {gx+gw} 245 C 850 245 850 {amf[1]+31} {amf[0]} {amf[1]+31}", start=True)
s.label(845, 236, "N2", size=13)
s.path(f"M {gx+gw} 330 C 850 330 850 {upf[1]+31} {upf[0]} {upf[1]+31}", start=True)
s.label(850, 372, "N3", size=13)
s.save("mode-zmq.svg", "ZMQ simulation mode")

# ---------------------------------------------------------------- UHD mode
s = SVG(1500, 780)
s.rect(330, 50, 1150, 710, MACHINE, rx=14)
s.text(350, 745, "Host PC", size=16, weight="bold", anchor="start")
s.text(750, 32, "Path B · USRP X310 (UHD) + real phone (over the air)", size=21, weight="bold")
# phone + sim
s.phone(40, 230, w=72, h=130)
s.text(76, 384, "Google Pixel 9 Pro", size=13, weight="bold")
s.text(76, 400, "NR only · APN srsapn", size=12, fill="#444")
s.rect(26, 418, 100, 46, YELLOW, rx=6)
s.text(76, 437, "test SIM", size=13, weight="bold")
s.text(76, 454, "IMSI 00101…", size=11, fill="#333")
s.waves(122, 295)
s.label(235, 222, "n78 TDD · 3410.1 MHz", size=12)
s.text(235, 242, "20 MHz · 30 kHz SCS", size=12, fill="#333")
# X310 outside machine? place between
s.server(185, 380, 120, 100, "USRP X310", "2× UBX-40", d=12, fill="#e2e8f0")
s.text(245, 505, "RF A: TX/RX + RX2", size=12, fill="#333")
s.text(245, 521, "ref: internal | 10 MHz+PPS", size=12, fill="#333")
s.path("M 160 300 C 200 320 230 340 240 372", end=True, dash="2,4", sw=2)
# NIC
s.rect(360, 400, 150, 56, ORANGE, rx=6)
s.text(435, 422, "enp45s0f1 (SFP+)", size=12, weight="bold")
s.text(435, 440, "192.168.40.1 · MTU 9000", size=11, fill="#333")
s.line(305, 430, 360, 428, start=True, sw=2.4)
s.label(334, 412, "10 GbE", size=12)
# gNB
gx, gy, gw, gh = 560, 200, 240, 170
s.box(gx, gy, gw, gh, "gNB", ["device_driver: uhd", "UHD 4.8 · FPGA matched", "PLMN 00101 · TAC 1"], size=22)
s.text(gx + gw / 2, gy - 12, "OCUDU", size=16, weight="bold")
s.path(f"M 510 428 C 540 428 545 340 {gx} 340", start=True, sw=2.4)
s.label(545, 400, "IQ", size=12)
core = core_block(s, 910, 110)
tx, ty = core["tun"]; s.cloud(tx, ty + 95, "Internet"); s.line(tx, ty, tx, ty + 62); s.label(tx + 12, ty + 38, "host NAT", size=12, anchor="start")
amf, upf = core["amf"], core["upf"]
s.path(f"M {gx+gw} 245 C 850 245 850 {amf[1]+31} {amf[0]} {amf[1]+31}", start=True)
s.label(855, 236, "N2", size=13)
s.path(f"M {gx+gw} 340 C 850 340 850 {upf[1]+31} {upf[0]} {upf[1]+31}", start=True)
s.label(860, 382, "N3", size=13)
s.save("mode-uhd.svg", "USRP X310 over-the-air mode")

# ---------------------------------------------------------------- Docker network
s = SVG(1400, 560)
s.text(700, 32, "How the host and the Docker containers are connected", size=21, weight="bold")
s.rect(20, 55, 1360, 485, MACHINE, rx=14)
s.text(40, 527, "Host PC", size=16, weight="bold", anchor="start")
# host side
s.cloud(170, 105, "Internet")
s.rect(60, 165, 220, 58, ORANGE, rx=6); s.text(170, 189, "Internet NIC (eno2)", size=13, weight="bold"); s.text(170, 207, "routing + NAT (MASQUERADE)", size=11, fill="#333")
s.line(170, 133, 170, 165, start=True)
s.rect(60, 250, 220, 58, ORANGE, rx=6); s.text(170, 274, "OCUDU gNB (host)", size=13, weight="bold"); s.text(170, 292, "binds 172.22.0.1", size=11, fill="#333")
s.rect(60, 335, 220, 58, ORANGE, rx=6); s.text(170, 359, "WebUI via any host IP", size=13, weight="bold"); s.text(170, 377, "published 9999:9999", size=11, fill="#333")
s.line(280, 194, 330, 180, start=True)
s.line(280, 279, 330, 196, start=True)
s.line(280, 364, 330, 202, start=True, dash="5,4")
# bridge
s.rect(330, 160, 1010, 46, YELLOW, rx=8)
s.text(835, 189, "br-<id>  ·  docker_open5gs_default  ·  172.22.0.0/24  ·  gateway 172.22.0.1 (the host)", size=14, weight="bold")
# containers
items = [("NRF", "172.22.0.12"), ("SCP", "172.22.0.35"), ("AMF", "172.22.0.10"), ("SMF", "172.22.0.7"),
         ("UPF", "172.22.0.8"), ("AUSF", "172.22.0.11"), ("UDM", "172.22.0.13"), ("MongoDB", "172.22.0.2"), ("WebUI", "172.22.0.26")]
for i, (n, ip) in enumerate(items):
    cx = 345 + i * 110
    s.line(cx + 45, 206, cx + 45, 290, end=False, sw=1.4)
    s.text(cx + 52, 252, "veth", size=10, fill="#555", anchor="start")
    s.rect(cx, 290, 92, 92, "#ffffff", rx=6, stroke="#666", dash="4,3")
    s.server(cx + 10, 322, 72, 40, n, None, d=6, fill=GREEN if n in ("MongoDB", "WebUI") else BLUE)
    s.text(cx + 46, 307, "eth0", size=10, fill="#555")
    s.text(cx + 46, 400, ip, size=11, weight="bold")
s.rect(895, 420, 130, 44, ORANGE, rx=6); s.text(960, 439, "ogstun (in UPF)", size=12, weight="bold"); s.text(960, 456, "192.168.100.1/24", size=11, fill="#333")
s.line(877, 375, 905, 420)
s.text(835, 495, "Each container = own network namespace (eth0, IP, routes).  veth = virtual cable to the bridge.  IPs come from .env → sa-deploy.yaml.",
       size=13, fill="#333")
s.save("docker-network.svg", "Docker networking of the 5G core")
print("ok")

# ---------------------------------------------------------------- near-RT RIC
s = SVG(1500, 730)
s.rect(20, 50, 1460, 660, MACHINE, rx=14)
s.text(40, 695, "Host PC (single machine, ZMQ or USRP)", size=16, weight="bold", anchor="start")
s.text(750, 32, "O-RAN SC near-RT RIC (Docker) + xApps connected to OCUDU over E2", size=21, weight="bold")
# RIC block
rx, ry, rw, rh = 60, 110, 760, 420
s.rect(rx, ry, rw, rh, CORE_BG, rx=40)
s.text(rx + rw / 2, ry - 12, "O-RAN SC near-RT RIC  (i-release, Docker)", size=17, weight="bold")
s.rect(rx + 20, ry + rh - 48, rw - 40, 30, YELLOW, rx=6)
s.text(rx + rw / 2, ry + rh - 28, "RIC Docker network  10.0.2.0/24   (host = 10.0.2.1)", size=13, weight="bold")
s.rect(rx + 30, ry + 22, rw - 60, 28, BLUE, rx=4)
s.text(rx + rw / 2, ry + 42, "RIC platform  ·  RMR message routing + REST", size=14, weight="bold")
plat = [("e2mgr", "10.0.2.11"), ("dbaas", "10.0.2.12"), ("submgr", "10.0.2.13"), ("appmgr", "10.0.2.14"), ("rtmgr_sim", "10.0.2.15")]
for i, (n, ip) in enumerate(plat):
    s.server(rx + 34 + i * 142, ry + 80, 112, 52, n, ip, d=8)
s.server(rx + 560, ry + 190, 150, 80, "e2term", "10.0.2.10 :36421", d=10)
# xApp runner
s.rect(rx + 34, ry + 180, 470, 170, "#f7f3fd", rx=16, dash="6,4", stroke="#7a5fb5")
s.text(rx + 269, ry + 202, "python_xapp_runner  ·  10.0.2.20", size=13, weight="bold", fill="#5a3f95")
for i, (n, sub) in enumerate([("KPM monitor", "E2SM-KPM"), ("RC control", "E2SM-RC"), ("your xApp", "Python")]):
    s.box(rx + 50 + i * 150, ry + 220, 135, 100, n, [sub, "xApp"], fill=PURPLE, size=15)
s.line(rx + 504, ry + 265, rx + 560, ry + 235, start=True)
s.label(rx + 532, ry + 236, "RMR", size=11)
# gNB
gx, gy, gw, gh = 900, 230, 240, 170
s.box(gx, gy, gw, gh, "gNB", ["OCUDU", "E2 agent (DU)", "KPM · RC · CCC"], size=22)
s.text(gx + gw / 2, gy - 12, "OCUDU", size=16, weight="bold")
s.path(f"M {rx+710+10} {ry+225} C 860 {ry+225} 860 300 {gx} 300", start=True, sw=2.2)
s.label(836, 262, "E2 · E2AP/SCTP :36421", size=12)
s.text(836, 282, "bind 10.0.2.1 → 10.0.2.10", size=11, fill="#333")
# core + UE
s.box(1230, 200, 220, 110, "Open5GS 5GC", ["Docker 172.22.0.0/24", "AMF .10 · UPF .8"], fill=GREEN, size=16)
s.line(gx + gw, 280, 1230, 255, start=True)
s.label(1185, 252, "N2 / N3", size=12)
s.box(900, 560, 240, 110, "UE", ["srsUE (ZMQ)", "or phone (USRP)"], fill=PURPLE, size=18)
s.line(gx + gw / 2, gy + gh, gx + gw / 2, 560, start=True, dash="7,5")
s.label(gx + gw / 2 + 60, 490, "ZMQ / radio", size=12)
# flow notes
s.lines(80, 580, ["① gNB → e2term: E2 Setup (registers RAN functions KPM, RC, CCC)",
                  "② xApp → submgr (REST) → e2term → gNB: RIC Subscription",
                  "③ gNB → e2term → xApp (RMR): RIC Indication with metrics",
                  "④ xApp → e2term → gNB: RIC Control (e.g. PRB quota)"], size=14, gap=26, anchor="start")
s.save("mode-ric.svg", "O-RAN SC near-RT RIC with xApps connected to OCUDU")
