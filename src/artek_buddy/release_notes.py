"""GitHub Release notes from CHANGELOG.md. Used by release.yml, not an HTTP route."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_HEADING = re.compile(r"^## \[([^\]]+)\]", re.MULTILINE)


def changelog_section(text: str, version: str) -> str:
    matches = list(_HEADING.finditer(text))
    for index, match in enumerate(matches):
        if match.group(1) != version:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.start() : end].strip()
        if body:
            return body + "\n"
    raise ValueError(f"CHANGELOG.md has no section for {version}")


def render_release_notes(version: str, changelog_text: str) -> str:
    section = changelog_section(changelog_text, version).rstrip()
    return f"""# Artek Buddy {version}

{section}

## Artifacts

- `artek-buddy-client_{version}_all.deb` — owner window, no baked host URL
- `SHA256SUMS`
- `sbom-client.cdx.json` — CycloneDX of the client tree
- `sbom-host.cdx.json` — CycloneDX of the host image
- `install-host.sh`

## Verify

```bash
sha256sum -c SHA256SUMS
gh attestation verify artek-buddy-client_{version}_all.deb --repo itsuppartem/artek-buddy
gh attestation verify oci://ghcr.io/itsuppartem/artek-buddy:{version} --repo itsuppartem/artek-buddy
```

## Known limits

- Computer image is not built in Actions (QEMU Chromium hangs). `install-host.sh` builds it on the Pi when GHCR has no tag.
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="artek_buddy.release_notes")
    parser.add_argument("version")
    parser.add_argument("changelog", nargs="?", default="CHANGELOG.md")
    args = parser.parse_args(argv)
    text = Path(args.changelog).read_text(encoding="utf-8")
    sys.stdout.write(render_release_notes(args.version, text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
