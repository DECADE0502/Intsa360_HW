from __future__ import annotations

import json
import mimetypes
import sys
import argparse
import uuid
import re
import zipfile
import io
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backend import assets
from app.backend import history
from app.backend import lifecycle
from app.backend import update_api
from app.backend.capabilities import load_capabilities, set_cadence_menu_visibility
from app.backend.plugins import load_plugins, set_plugin_cadence_menu_visibility
from app.backend.tool_registry import ToolRegistry, build_registry


FRONTEND_DIR = ROOT / "app" / "frontend"
USER_INPUT_ERROR_PATTERNS = ("缺少", "输入", "表头识别失败")


def json_response(payload: dict[str, object], status: int = 200) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    return body, {
        "Content-Type": "application/json; charset=utf-8",
        "Content-Length": str(len(body)),
        "Cache-Control": "no-store",
        "X-Status": str(status),
    }


def _safe_child(base: Path, requested: str) -> Path | None:
    target = (base / requested).resolve()
    try:
        target.relative_to(base.resolve())
    except ValueError:
        return None
    return target


def _parse_multipart_files(body: bytes, content_type: str) -> list[tuple[str, bytes]]:
    marker = "boundary="
    if marker not in content_type:
        raise ValueError("missing multipart boundary")
    boundary = content_type.split(marker, 1)[1].strip().strip('"')
    delimiter = ("--" + boundary).encode("utf-8")
    files: list[tuple[str, bytes]] = []
    for part in body.split(delimiter):
        part = part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        header_blob, _, content = part.partition(b"\r\n\r\n")
        if not header_blob or not content:
            continue
        headers = header_blob.decode("utf-8", errors="ignore")
        match = re.search(r'filename="([^"]+)"', headers)
        if not match:
            continue
        filename = Path(match.group(1)).name
        if content.endswith(b"\r\n"):
            content = content[:-2]
        files.append((filename, content))
    return files


def _content_disposition(filename: str) -> str:
    ascii_fallback = "".join(char if 32 <= ord(char) < 127 and char not in {'"', "\\", ";"} else "_" for char in filename)
    encoded = quote(filename.encode("utf-8"))
    return f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded}'


def _timestamp_for_filename() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


class SuiteRequestHandler(BaseHTTPRequestHandler):
    registry: ToolRegistry
    root: Path

    def _send(self, status: int, body: bytes, headers: dict[str, str]) -> None:
        self.send_response(status)
        for key, value in headers.items():
            if key != "X-Status":
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict[str, object], status: int = 200) -> None:
        body, headers = json_response(payload, status)
        self._send(status, body, headers)

    def _outputs_dir(self) -> Path:
        return self.root / "data" / "outputs"

    def _uploads_dir(self) -> Path:
        return self.root / "data" / "uploads"

    @staticmethod
    def _is_user_input_error(exc: Exception) -> bool:
        message = str(exc)
        return isinstance(exc, (KeyError, ValueError, FileNotFoundError, PermissionError)) or any(
            pattern in message for pattern in USER_INPUT_ERROR_PATTERNS
        )

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/tools":
            self._send_json({"tools": self.registry.list_tools()})
            return
        if parsed.path == "/api/capabilities":
            self._send_json(load_capabilities(self.root))
            return
        if parsed.path == "/api/plugins":
            self._send_json(load_plugins(self.root))
            return
        if parsed.path == "/api/platform/status":
            capabilities = load_capabilities(self.root)["capabilities"]
            scripts = [item for item in capabilities if item.get("type") == "cadence_tcl"]
            self._send_json(
                {
                    "status": "ok",
                    "platform": "Insta360硬件提效平台",
                    "tools": len(self.registry.list_tools()),
                    "cadence_scripts": len(scripts),
                    "enableable_scripts": len([item for item in scripts if item.get("can_enable") is True]),
                    "enabled_scripts": len([item for item in scripts if item.get("show_in_cadence") is True]),
                    "pending_scripts": len([item for item in scripts if item.get("can_enable") is not True]),
                    "root": str(self.root),
                }
            )
            return
        if parsed.path == "/api/lifecycle/check":
            self._send_json(lifecycle.run_self_check(self.root))
            return
        if parsed.path == "/api/logs":
            log_dir = self.root / "data" / "reports" / "runtime"
            files = sorted(
                [{"name": item.name, "size": item.stat().st_size, "mtime": item.stat().st_mtime} for item in log_dir.iterdir() if item.is_file()],
                key=lambda item: item["mtime"], reverse=True,
            ) if log_dir.exists() else []
            self._send_json({"files": files})
            return
        if parsed.path == "/api/logs/download":
            log_dir = self.root / "data" / "reports" / "runtime"
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for item in sorted(log_dir.iterdir()) if log_dir.exists() else []:
                    if item.is_file():
                        zf.write(item, arcname=item.name)
            data = buf.getvalue()
            self._send(200, data, {"Content-Type": "application/zip", "Content-Length": str(len(data)), "Content-Disposition": _content_disposition("platform_logs.zip")})
            return
        if parsed.path == "/api/version":
            self._send_json(update_api.version_payload(self.root))
            return
        if parsed.path == "/api/update/check":
            self._send_json(update_api.check_update(self.root))
            return
        if parsed.path == "/api/update/status":
            self._send_json(update_api.update_status(self.root))
            return
        if parsed.path == "/api/uninstall/check":
            self._send_json(update_api.check_uninstall(self.root))
            return
        if parsed.path == "/api/uninstall/status":
            self._send_json(update_api.uninstall_status(self.root))
            return
        if parsed.path == "/api/history":
            self._send_json({"runs": history.list_runs(self.root)})
            return
        if parsed.path == "/api/assets":
            self._send_json(assets.list_assets(self.root))
            return
        if parsed.path.startswith("/api/history/"):
            run_id = unquote(parsed.path.removeprefix("/api/history/"))
            run = history.get_run(self.root, run_id)
            if run is None:
                self._send_json({"error": "history not found"}, 404)
                return
            self._send_json(run)
            return
        if parsed.path.startswith("/outputs/"):
            requested = unquote(parsed.path.removeprefix("/outputs/"))
            target = _safe_child(self._outputs_dir(), requested)
            if target is None or not target.is_file():
                self._send_json({"error": "output not found"}, 404)
                return
            content = target.read_bytes()
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self._send(
                200,
                content,
                {
                    "Content-Type": content_type,
                    "Content-Length": str(len(content)),
                    "Content-Disposition": _content_disposition(target.name),
                },
            )
            return
        self._serve_frontend(parsed.path)

    def _record_history(self, tool_id: str, params: dict[str, object], result: dict[str, object]) -> None:
        try:
            name = self.registry.get_tool(tool_id).get("name", tool_id)
            history.record(self.root, tool_id, name, params, result)
        except Exception:
            pass

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/history":
            history.clear_runs(self.root)
            self._send_json({"status": "ok"})
            return
        if parsed.path.startswith("/api/history/"):
            run_id = unquote(parsed.path.removeprefix("/api/history/"))
            history.remove_run(self.root, run_id)
            self._send_json({"status": "ok"})
            return
        self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/upload":
            self._handle_upload()
            return
        if parsed.path == "/api/package":
            self._handle_package()
            return
        if parsed.path == "/api/update/run":
            self._send_json(update_api.run_update(self.root))
            return
        if parsed.path == "/api/cadence/install":
            self._handle_cadence_install()
            return
        if parsed.path == "/api/uninstall/run":
            try:
                params = self._read_json_body()
                result = update_api.run_uninstall(self.root, str(params.get("mode") or "detach"))
            except Exception as exc:
                self._send_json({"status": "error", "error": str(exc)}, 400 if self._is_user_input_error(exc) else 500)
                return
            self._send_json(result, 200 if result.get("status") == "ok" else 400)
            return
        if parsed.path.startswith("/api/capabilities/") and parsed.path.endswith("/cadence-menu"):
            capability_id = unquote(parsed.path.removeprefix("/api/capabilities/").removesuffix("/cadence-menu"))
            self._handle_cadence_menu_update(capability_id)
            return
        if parsed.path.startswith("/api/plugins/") and parsed.path.endswith("/cadence-menu"):
            plugin_id = unquote(parsed.path.removeprefix("/api/plugins/").removesuffix("/cadence-menu"))
            self._handle_plugin_menu_update(plugin_id)
            return
        if parsed.path.startswith("/api/tools/") and parsed.path.endswith("/run"):
            tool_id = parsed.path.removeprefix("/api/tools/").removesuffix("/run")
            try:
                params = self._read_json_body()
                result = self.registry.run_tool(tool_id, params)
            except Exception as exc:
                self._send_json({"status": "error", "error": str(exc)}, 400 if self._is_user_input_error(exc) else 500)
                return
            self._record_history(tool_id, params, result)
            self._send_json(result, 400 if result.get("status") == "error" else 200)
            return
        self._send_json({"error": "not found"}, 404)

    def _handle_cadence_menu_update(self, capability_id: str) -> None:
        try:
            params = self._read_json_body()
            show = bool(params.get("show_in_cadence"))
            redeploy = bool(params.get("redeploy", True))
            capability = set_cadence_menu_visibility(self.root, capability_id, show)
            redeployed = False
            if redeploy:
                # PowerShell owns Cadence loader generation, so keep the API thin and explicit.
                script = self.root / "scripts" / "redeploy_cadence_loader.ps1"
                if not script.exists():
                    raise FileNotFoundError("未找到 Cadence 菜单重部署脚本")
                import subprocess

                completed = subprocess.run(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                    cwd=str(self.root),
                    text=True,
                    capture_output=True,
                    timeout=30,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if completed.returncode != 0:
                    raise RuntimeError((completed.stderr or completed.stdout or "Cadence 菜单重部署失败").strip())
                redeployed = True
        except Exception as exc:
            self._send_json({"status": "error", "error": str(exc)}, 400 if self._is_user_input_error(exc) else 500)
            return
        self._send_json({"status": "ok", "capability": capability, "redeployed": redeployed})

    def _redeploy_cadence_loader(self) -> tuple[bool, list[str], str]:
        script = self.root / "scripts" / "redeploy_cadence_loader.ps1"
        if not script.exists():
            raise FileNotFoundError("未找到 Cadence 菜单重新部署脚本")
        import subprocess

        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            cwd=str(self.root),
            text=True,
            capture_output=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "Cadence 菜单重新部署失败").strip())
        output = "\n".join(part for part in [completed.stdout, completed.stderr] if part)
        installed = []
        for line in output.splitlines():
            if "iac_bom_tool.tcl" in line:
                if "：" in line:
                    installed.append(line.rsplit("：", 1)[-1].strip())
                elif ": " in line:
                    installed.append(line.rsplit(": ", 1)[-1].strip())
        return True, installed, output

    def _handle_cadence_install(self) -> None:
        try:
            redeployed, installed, output = self._redeploy_cadence_loader()
        except Exception as exc:
            self._send_json({"status": "error", "error": str(exc)}, 400 if self._is_user_input_error(exc) else 500)
            return
        self._send_json(
            {
                "status": "ok",
                "redeployed": redeployed,
                "installed": installed,
                "output": output,
                "message": "Cadence 集成已重新安装",
                "hot_reload_command": 'source [file join $env(HOME) "cdssetup/OrCAD_Capture/tclscripts/capAutoLoad/iac_bom_tool.tcl"]',
            }
        )

    def _handle_plugin_menu_update(self, plugin_id: str) -> None:
        try:
            params = self._read_json_body()
            show = bool(params.get("show_in_cadence"))
            redeploy = bool(params.get("redeploy", True))
            plugin = set_plugin_cadence_menu_visibility(self.root, plugin_id, show)
            redeployed = self._redeploy_cadence_loader()[0] if redeploy else False
        except Exception as exc:
            self._send_json({"status": "error", "error": str(exc)}, 400 if self._is_user_input_error(exc) else 500)
            return
        self._send_json({"status": "ok", "plugin": plugin, "redeployed": redeployed})

    def _read_json_body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length == 0:
            return {}
        body = self.rfile.read(length)
        return json.loads(body.decode("utf-8"))

    def _handle_upload(self) -> None:
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._send_json({"error": "multipart/form-data required"}, 400)
            return
        session = uuid.uuid4().hex[:12]
        target_dir = self._uploads_dir() / session
        target_dir.mkdir(parents=True, exist_ok=True)
        files = []
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length)
        for filename, content in _parse_multipart_files(body, content_type):
            target = target_dir / filename
            target.write_bytes(content)
            files.append({"name": filename, "path": str(target)})
        self._send_json({"status": "ok", "session": session, "files": files, "folder": str(target_dir)})

    def _handle_package(self) -> None:
        try:
            params = self._read_json_body()
        except Exception:
            self._send_json({"error": "bad request"}, 400)
            return
        name = str(params.get("name") or "BOM导出").strip() or "BOM导出"
        members: list[Path] = []
        seen: set[str] = set()
        for raw in params.get("files") or []:
            normalized = unquote(str(raw)).replace("\\", "/")
            marker = "/data/outputs/"
            idx = normalized.find(marker)
            rel = normalized[idx + len(marker):] if idx >= 0 else normalized.replace("data/outputs/", "")
            target = _safe_child(self._outputs_dir(), rel)
            if target and target.is_file() and str(target) not in seen:
                seen.add(str(target))
                members.append(target)
        if not members:
            self._send_json({"error": "no files to package"}, 404)
            return
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for member in members:
                zf.write(member, arcname=member.name)
        data = buffer.getvalue()
        stamp = _timestamp_for_filename()
        self._send(200, data, {
            "Content-Type": "application/zip",
            "Content-Length": str(len(data)),
            "Content-Disposition": _content_disposition(f"{name}_{stamp}.zip"),
        })

    def _serve_frontend(self, path: str) -> None:
        requested = "index.html" if path in {"", "/"} else path.lstrip("/")
        target = _safe_child(FRONTEND_DIR, requested)
        if target is None or not target.is_file():
            self._send_json({"error": "not found"}, 404)
            return
        content = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix in {".html", ".css", ".js"}:
            content_type += "; charset=utf-8"
        self._send(
            200,
            content,
            {
                "Content-Type": content_type,
                "Content-Length": str(len(content)),
                "Cache-Control": "no-store",
            },
        )

    def log_message(self, format: str, *args) -> None:
        return


def create_server(root: Path = ROOT, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    registry = build_registry(root)

    class Handler(SuiteRequestHandler):
        pass

    Handler.registry = registry
    Handler.root = root
    return ThreadingHTTPServer((host, port), Handler)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the hardware efficiency tool suite.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = create_server(host=args.host, port=args.port)
    host, port = server.server_address
    print(f"Hardware Efficiency Suite running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
