from __future__ import annotations

from web_paths import safe_content_type, web_file_for_request


class StaticMixin:
    def _static(self) -> None:
        root = self.server.web_root  # type: ignore[attr-defined]
        target = web_file_for_request(root, self.path)
        if target is None:
            self.send_error(404)
            return
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", safe_content_type(target))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
