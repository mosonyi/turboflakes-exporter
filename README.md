# Polkadot & Kusama Validator Exporter

This Dockerized Python exporter collects validator metrics from the
[Turboflakes API](https://turboflakes.io) for both **Polkadot** and **Kusama**
networks and exposes Prometheus metrics.

---

## 🚀 Features

- Supports multiple validators (Polkadot + Kusama) in one container.
- Exposes metrics with validator **stash**, **network**, and **name** (identity).
- Provides numeric grades for easy alerting (1=A+, 2=A, 3=B, ...).
- Integrates directly with Prometheus and Alertmanager (no webhook needed).

---

## 📁 Project Structure

```
polkadot-monitor/
├── exporter/
│   └── app.py
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

---

## 🧠 Environment Variable

`TARGET_URLS` — list of Turboflakes *grade* API URLs (both Polkadot & Kusama).  
You can separate with commas or newlines.

Example:
```yaml
TARGET_URLS: |
  https://polkadot-onet-api.turboflakes.io/api/v1/validators/1123RekaPHgWaPL5v9qfsikRemeZdYC4tvKXYuLXwhfT3NKy/grade
  https://kusama-onet-api.turboflakes.io/api/v1/validators/FJgeBDUj4gF2rYxLmxc7QcccEMZQ26xudp4sro3HFMGZMRL/grade
```

---

## 🐳 Build & Run

```bash
docker build -t mosonyi/turboflakes-exporter:v1.0 .
docker run  --name turboflakes-exporter   -p 9201:9101   -e TARGET_URLS="https://polkadot-onet-api.turboflakes.io/api/v1/validators/1123RekaPHgWaPL5v9qfsikRemeZdYC4tvKXYuLXwhfT3NKy/grade,https://kusama-onet-api.turboflakes.io/api/v1/validators/FJgeBDUj4gF2rYxLmxc7QcccEMZQ26xudp4sro3HFMGZMRL/grade"  mosonyi/turboflakes-exporter:v1.0

```
## 🐳 Run with docker compose

```bash
docker compose up -d
```

Then visit: [http://localhost:9101/metrics](http://localhost:9101/metrics)

---

## 📊 Example Prometheus Scrape Config

```yaml
scrape_configs:
  - job_name: 'validators-exporter'
    static_configs:
      - targets: ['turboflakes-exporter:9101']
```

---

## ⚠️ Example Alert Rules

```yaml
groups:
- name: validators
  rules:
  - alert: ValidatorDegraded
    expr: polka_validator_grade > 1
    for: 10m
    labels:
      severity: warning
    annotations:
      summary: "Validator degraded: {{ $labels.network }} / {{ $labels.name }}"
      description: "Grade numeric={{ $value }} (1=A+). Stash={{ $labels.validator }}."
```

---

## 🧾 Metrics Exposed

| Metric | Description |
|--------|--------------|
| `polka_validator_grade` | Validator grade (1=A+,2=A,3=B,4=C,5=D,6=F) |
| `polka_validator_missed_votes_total` | Missed votes total |
| `polka_exporter_up` | 1 if fetch succeeded, 0 otherwise |

Each metric includes labels:  
`validator`, `network`, and `name`.

---

## 🧰 Alertmanager Template Example

```yaml
route:
  receiver: 'slack-main'

receivers:
  - name: 'slack-main'
    slack_configs:
      - send_resolved: true
        channel: '#validators'
        title: '{{ .CommonAnnotations.summary }}'
        text: >-
          *Status:* {{ .Status }}
          {{ range .Alerts -}}
          • *{{ .Annotations.summary }}*
            Network: {{ .Labels.network }}
            Validator: {{ .Labels.name }} ({{ .Labels.validator }})
          {{ end }}
```

---

## 📄 License

MIT License © 2025
