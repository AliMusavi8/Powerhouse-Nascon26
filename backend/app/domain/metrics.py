"""Prometheus text exposition format 0.0.4 (NFR-6) and PII erasure helpers (NFR-9)."""
import hashlib

CONTENT_TYPE = "text/plain; version=0.0.4"

METRICS = (
    ("nascon_active_ws_connections", "gauge", "Open WebSocket and SSE client connections."),
    ("nascon_active_streams_total", "gauge", "Live ingest streams currently publishing."),
    ("nascon_stream_bitrate_kbps", "gauge", "Ingest bitrate per live stream in kbit/s."),
    ("nascon_dlq_depth", "gauge", "Notification events waiting in the dead-letter queue."),
    ("nascon_qr_scans_total", "counter", "Dynamic QR code scans since the last reset."),
)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _num(value) -> str:
    if isinstance(value, float):
        return repr(round(value, 3))
    return str(int(value))


def render(samples: dict) -> str:
    """samples: metric name -> number, or list of (labels dict, number)."""
    lines = []
    for name, kind, help_text in METRICS:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {kind}")
        value = samples.get(name, 0)
        if isinstance(value, list):
            if not value:
                lines.append(f"{name} 0")
            for labels, v in value:
                label_text = ",".join(f'{k}="{_escape(str(lv))}"' for k, lv in sorted(labels.items()))
                lines.append(f"{name}{{{label_text}}} {_num(v)}")
        else:
            lines.append(f"{name} {_num(value)}")
    return "\n".join(lines) + "\n"


def anon_id(user_id: str) -> str:
    return "anon-" + hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:8]
