import os, re, requests
from flask import Flask, Response

app = Flask(__name__)

# Accept a comma- or newline-separated list of full grade URLs
RAW = os.environ.get("TARGET_URLS", "").strip()
URLS = [u.strip() for u in (RAW.replace(",", "\n")).splitlines() if u.strip()]

# Map letter grade to numeric for easier alerts
GRADE_MAP = {"A+": 1, "A": 2, "B": 3, "C": 4, "D": 5, "F": 6}

re_validator = re.compile(r"/validators/([^/]+)/grade")
re_network  = re.compile(r"https?://([a-z0-9-]+)-onet-api\.turboflakes\.io", re.I)

def parse_labels(url: str):
    vm = re_validator.search(url)
    nm = re_network.search(url)
    validator = vm.group(1) if vm else "unknown"
    network = nm.group(1) if nm else "unknown"
    return validator, network

def build_profile_url(network: str, validator: str) -> str:
    return f"https://{network}-onet-api.turboflakes.io/api/v1/validators/{validator}/profile"

session = requests.Session()

@app.route("/metrics")
def metrics():
    lines = []
    # Headers
    lines.append("# HELP polka_validator_grade Grade numeric (1=A+,2=A,3=B,4=C,5=D,6=F)")
    lines.append("# TYPE polka_validator_grade gauge")
    lines.append("# HELP polka_validator_missed_votes_total Missed votes total")
    lines.append("# TYPE polka_validator_missed_votes_total gauge")
    lines.append("# HELP polka_exporter_up 1 if fetch ok for this validator, else 0")
    lines.append("# TYPE polka_exporter_up gauge")

    for url in URLS:
        validator, network = parse_labels(url)
        name_label = validator  # default fallback
        up = 0

        try:
            # 1) Grade
            gj = session.get(url, timeout=8).json()
            grade  = gj.get("grade", "F")
            missed = gj.get("missed_votes_total", 0)
            num    = GRADE_MAP.get(grade, 9)

            # 2) Name from profile (best-effort)
            try:
                pj = session.get(build_profile_url(network, validator), timeout=8).json()
                identity = pj.get("identity") or {}
                name_label = identity.get("name") or identity.get("sub") or pj.get("stash") or validator
            except Exception:
                pass

            # Emit metrics with labels
            lines.append(f'polka_validator_grade{{validator="{validator}",network="{network}",name="{name_label}"}} {num}')
            lines.append(f'polka_validator_missed_votes_total{{validator="{validator}",network="{network}",name="{name_label}"}} {missed}')
            up = 1
        except Exception:
            # failed to fetch grade; expose up=0
            pass

        lines.append(f'polka_exporter_up{{validator="{validator}",network="{network}",name="{name_label}"}} {up}')

    return Response("\n".join(lines) + "\n", mimetype="text/plain")

if __name__ == "__main__":
    # default port 9101
    app.run(host="0.0.0.0", port=9101)
