import os
import re
import logging
import requests
from urllib.parse import urlparse
from flask import Flask, Response

app = Flask(__name__)
session = requests.Session()
session.headers.update({"User-Agent": "turboflakes-exporter/1.1"})

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO),
                    format="%(asctime)s [%(levelname)s] %(message)s")

# Convert letter grades to numeric
GRADE_MAP = {"A+": 1, "A": 2, "B": 3, "B+": 4, "C": 5, "D": 6, "F": 7}

URL_RE = re.compile(r"^https?://", re.IGNORECASE)

def _clean_lines(raw: str):
    """
    Yield cleaned lines from a raw block (ENV or file):
    - strip whitespace & quotes
    - drop empty, '-' lines, and comments (# ...)
    """
    for ln in raw.splitlines():
        ln = ln.strip().strip("'").strip('"')
        if not ln:
            continue
        if ln == "-":
            continue
        if ln.startswith("#"):
            continue
        yield ln

def get_target_urls():
    """
    Accept TARGET_URLS (commas or newlines) and/or TARGET_URLS_FILE (one URL per line).
    Drop invalid entries and log them.
    """
    urls = []

    # From file
    path = os.getenv("TARGET_URLS_FILE")
    if path and os.path.exists(path):
        with open(path, "r") as f:
            for ln in _clean_lines(f.read()):
                urls.append(ln)

    # From env (split on commas first; then split each chunk by lines)
    raw = os.getenv("TARGET_URLS", "")
    if raw:
        for chunk in raw.split(","):
            for ln in _clean_lines(chunk):
                urls.append(ln)

    # Dedup while preserving order, and validate schema
    seen = set()
    valid = []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        if URL_RE.match(u):
            valid.append(u)
        else:
            logging.warning("Dropped TARGET_URLS entry (not a URL): %r", u)

    return valid


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


@app.route("/health")
def health():
    return Response("ok\n", mimetype="text/plain")


@app.route("/metrics")
def metrics():
    urls = get_target_urls()
    if not urls:
        return Response("# No TARGET_URLS configured\n", mimetype="text/plain")

    lines = []
    # Metric headers
    lines.append("# HELP polka_validator_grade_value Validator grade numeric (1=A+,2=A,3=B,4=B+,5=C,6=D,7=F) with grade label")
    lines.append("# TYPE polka_validator_grade_value gauge")
    lines.append("# HELP polka_validator_missed_votes_total Missed votes total")
    lines.append("# TYPE polka_validator_missed_votes_total gauge")
    lines.append("# HELP polka_exporter_up 1 if fetch ok for this validator, else 0")
    lines.append("# TYPE polka_exporter_up gauge")

    for url in urls:
        validator, network = parse_labels(url)
        name_label = validator
        emitted_any = False

        try:
            # 1) Grade JSON
            gj = session.get(url, timeout=10)
            gj.raise_for_status()
            gj = gj.json()
            grade_letter = (gj.get("grade") or "").strip()

            # If grade not in allowed list, skip + log warning
            if grade_letter not in GRADE_MAP:
                logging.warning(
                    "Dropped validator %s on %s: unrecognized grade %r (url=%s)",
                    validator, network, grade_letter, url
                )
                continue

            missed = gj.get("missed_votes_total", 0)
            grade_value = GRADE_MAP[grade_letter]

            # 2) Profile JSON (best-effort)
            try:
                pj = session.get(build_profile_url(network, validator), timeout=10)
                pj.raise_for_status()
                pj = pj.json()
                identity = pj.get("identity") or {}
                name_part = identity.get("name")
                sub_part = identity.get("sub")
                if name_part and sub_part:
                    name_label = f"{name_part}/{sub_part}"
                elif name_part:
                    name_label = name_part
                elif sub_part:
                    name_label = sub_part
                else:
                    name_label = pj.get("stash") or validator
            except Exception as e:
                logging.debug("Profile fetch failed for %s on %s: %s", validator, network, e)

            # 3) Emit metrics
            base = f'validator="{validator}",network="{network}",name="{name_label}",grade="{grade_letter}"'
            lines.append(f'polka_validator_grade_value{{{base}}} {grade_value}')
            lines.append(f'polka_validator_missed_votes_total{{validator="{validator}",network="{network}",name="{name_label}"}} {missed}')
            emitted_any = True

        except Exception as e:
            logging.error("Error fetching validator %s on %s (url=%s): %s", validator, network, url, e)

        if emitted_any:
            lines.append(f'polka_exporter_up{{validator="{validator}",network="{network}",name="{name_label}"}} 1')

    return Response("\n".join(lines) + "\n", mimetype="text/plain")


if __name__ == "__main__":
    logging.info("Starting Turboflakes exporter on port 9101 ...")
    app.run(host="0.0.0.0", port=9101)
