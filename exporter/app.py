import os
import re
import requests
from urllib.parse import urlparse
from flask import Flask, Response

app = Flask(__name__)
session = requests.Session()
session.headers.update({"User-Agent": "turboflakes-exporter/1.0"})

# Convert letter grades to numeric (for alerting)
GRADE_MAP = {"A+": 1, "A": 2, "B": 3, "C": 4, "D": 5, "F": 6}


def get_target_urls():
    """
    Accept TARGET_URLS separated by commas and/or newlines.
    Also supports TARGET_URLS_FILE (one URL per line).
    """
    urls = []
    path = os.getenv("TARGET_URLS_FILE")
    if path and os.path.exists(path):
        with open(path, "r") as f:
            urls += [ln.strip() for ln in f if ln.strip()]
    raw = os.getenv("TARGET_URLS", "")
    # Split on commas or any whitespace (spaces, newlines, tabs)
    for u in re.split(r"[,\s]+", raw.strip()):
        if u:
            urls.append(u)
    # Deduplicate while preserving order
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def parse_labels(url: str):
    """
    Extract validator and network (polkadot/kusama) from Turboflakes grade URL.
    """
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("kusama-"):
        network = "kusama"
    elif host.startswith("polkadot-"):
        network = "polkadot"
    else:
        m = re.match(r"^([a-z0-9-]+)-onet-api\.turboflakes\.io$", host)
        network = m.group(1) if m else "unknown"

    mval = re.search(r"/validators/([^/]+)/grade", url)
    validator = mval.group(1) if mval else "unknown"
    return validator, network


def build_profile_url(network: str, validator: str) -> str:
    return f"https://{network}-onet-api.turboflakes.io/api/v1/validators/{validator}/profile"


@app.route("/metrics")
def metrics():
    urls = get_target_urls()
    if not urls:
        return Response("# No TARGET_URLS configured\n", mimetype="text/plain")

    lines = []
    # Metric headers
    lines.append("# HELP polka_validator_grade_value Validator grade numeric (1=A+,2=A,3=B,4=C,5=D,6=F) with grade label")
    lines.append("# TYPE polka_validator_grade_value gauge")
    lines.append("# HELP polka_validator_missed_votes_total Missed votes total")
    lines.append("# TYPE polka_validator_missed_votes_total gauge")
    lines.append("# HELP polka_exporter_up 1 if fetch ok for this validator, else 0")
    lines.append("# TYPE polka_exporter_up gauge")

    for url in urls:
        validator, network = parse_labels(url)
        name_label = validator
        up = 0

        try:
            # 1️⃣ Grade JSON
            gj = session.get(url, timeout=10)
            gj.raise_for_status()
            gj = gj.json()
            grade_letter = (gj.get("grade") or "F").strip()
            missed = gj.get("missed_votes_total", 0)
            grade_value = GRADE_MAP.get(grade_letter, 9)

            # 2️⃣ Profile JSON (best-effort)
            try:
                pj = session.get(build_profile_url(network, validator), timeout=10)
                pj.raise_for_status()
                pj = pj.json()
                identity = pj.get("identity") or {}
                name_label = identity.get("name") or identity.get("sub") or pj.get("stash") or validator
            except Exception:
                pass

            # 3️⃣ Emit metrics
            base = f'validator="{validator}",network="{network}",name="{name_label}",grade="{grade_letter}"'
            lines.append(f'polka_validator_grade_value{{{base}}} {grade_value}')
            lines.append(f'polka_validator_missed_votes_total{{validator="{validator}",network="{network}",name="{name_label}"}} {missed}')
            up = 1

        except Exception:
            pass

        lines.append(f'polka_exporter_up{{validator="{validator}",network="{network}",name="{name_label}"}} {up}')

    return Response("\n".join(lines) + "\n", mimetype="text/plain")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9101)
