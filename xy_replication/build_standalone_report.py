"""Package xy_replication_report.html as a single self-contained HTML file.

Only packaging is performed: no number, chart option, conclusion or evidence
label is changed. All <img> sources become data URIs and the ECharts CDN
<script> is replaced by a local, inlined copy. The primary report keeps its
relative image paths and CDN reference; this standalone copy is a second
deliverable intended for offline viewing or sharing as one file.
"""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # tda_project/
OUT = ROOT / "outputs"
SOURCE = OUT / "xy_replication_report.html"
TARGET = OUT / "xy_replication_report_standalone.html"
AUDIT = OUT / "xy_standalone_report_audit.json"
ECHARTS = ROOT / "third_party" / "echarts" / "echarts.min.js"
CDN_TAG = (
    '<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>'
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    html = SOURCE.read_text(encoding="utf-8")
    source_bytes = SOURCE.read_bytes()
    assert CDN_TAG in html, "primary report no longer uses the expected ECharts CDN tag"

    images: list[dict] = []

    def inline_image(match: re.Match[str]) -> str:
        tag = match.group(0)
        src_attr = re.search(r'src="([^"]+)"', tag)
        assert src_attr is not None
        rel = src_attr.group(1)
        path = (OUT / rel).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"image missing: {path}")
        payload = path.read_bytes()
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        encoded = base64.b64encode(payload).decode("ascii")
        images.append({
            "original_src": rel,
            "bytes": len(payload),
            "sha256": sha256(payload),
            "mime": mime,
        })
        return tag.replace(src_attr.group(0), f'src="data:{mime};base64,{encoded}"')

    html = re.sub(r'<img[^>]+src="[^"]+"[^>]*>', inline_image, html)

    echarts_bytes = ECHARTS.read_bytes()
    echarts_js = echarts_bytes.decode("utf-8").replace("</script", "<\\/script")
    html = html.replace(CDN_TAG, "<script>\n" + echarts_js + "\n</script>")

    # Packaging-only checks: no remote or relative asset dependencies remain.
    # ECharts itself contains HTML-ish string literals; strip <script> bodies
    # before asserting on markup so those literals cannot create false hits.
    skeleton = re.sub(r"<script\b[^>]*>.*?</script>", "<script></script>", html, flags=re.S)
    inlined_tags = len(re.findall(r'<img[^>]+src="data:image/', skeleton))
    assert inlined_tags == len(images), "unexpected inlined image count"
    assert len(images) >= 7, f"expected at least 7 figures, got {len(images)}"
    assert CDN_TAG not in html and "cdn.jsdelivr.net" not in html
    assert not re.search(r'<img[^>]+src="(?!data:image/)', skeleton)
    assert not re.search(r"<script[^>]+src=", skeleton)
    assert not re.search(r'<link[^>]+href="https?://', skeleton)
    assert "window.echarts" in html
    assert "const DATA=" in html

    TARGET.write_text(html, encoding="utf-8")
    audit = {
        "generated_on": date.today().isoformat(),
        "source": "outputs/xy_replication_report.html",
        "target": "outputs/xy_replication_report_standalone.html",
        "packaging_only": True,
        "content_or_numbers_changed": False,
        "source_html_sha256": sha256(source_bytes),
        "standalone_html_sha256": sha256(TARGET.read_bytes()),
        "standalone_html_bytes": TARGET.stat().st_size,
        "echarts": {
            "path": "third_party/echarts/echarts.min.js",
            "bytes": len(echarts_bytes),
            "sha256": sha256(echarts_bytes),
            "origin": "https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js",
            "license_note": "Apache-2.0; third-party bundle, see THIRD_PARTY.md",
        },
        "inlined_images": images,
        "offline_viewing": "All figures and chart library are embedded; no network or sibling folders required.",
        "boundary": "Standalone copy is a packaging artifact. Topology features, evidence labels and the exploratory-only status of section 4 (preregistered grid and IC diagnostics) are unchanged; no confirmatory corrected-version strategy performance is claimed.",
    }
    AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({
        "standalone": str(TARGET),
        "bytes": TARGET.stat().st_size,
        "inlined_images": len(images),
        "echarts_bytes": len(echarts_bytes),
        "audit": str(AUDIT),
    })


if __name__ == "__main__":
    main()
