from __future__ import annotations

import json
import mimetypes
import sys
import argparse
import uuid
import re
import zipfile
import io
import shutil
import tempfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from openpyxl.utils.exceptions import InvalidFileException

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


def _resolve_output_member(outputs_dir: Path, requested: object) -> Path:
    text = unquote(str(requested)).strip()
    if not text:
        raise ValueError("empty package path")
    if text.startswith("\\\\") or text.startswith("//"):
        raise ValueError("package path must be inside data/outputs")
    normalized = text.replace("\\", "/")
    if re.match(r"^[A-Za-z]:/", normalized):
        candidate = Path(text)
        try:
            rel = candidate.resolve().relative_to(outputs_dir.resolve())
        except (OSError, ValueError) as exc:
            raise ValueError("package path must be inside data/outputs") from exc
    else:
        parts = [part for part in normalized.split("/") if part]
        if ".." in parts:
            raise ValueError("package path must not contain '..'")
        marker = ["data", "outputs"]
        rel_parts = parts
        for idx in range(0, max(len(parts) - 1, 0)):
            if [part.lower() for part in parts[idx:idx + 2]] == marker:
                rel_parts = parts[idx + 2:]
                break
        rel = Path(*rel_parts) if rel_parts else Path("")
    target = _safe_child(outputs_dir, rel.as_posix())
    if target is None:
        raise ValueError("package path must be inside data/outputs")
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


def _multipart_boundary(content_type: str) -> bytes:
    marker = "boundary="
    if marker not in content_type:
        raise ValueError("missing multipart boundary")
    boundary = content_type.split(marker, 1)[1].split(";", 1)[0].strip().strip('"')
    if not boundary:
        raise ValueError("missing multipart boundary")
    return ("--" + boundary).encode("utf-8")


def _parse_multipart_files_from_disk(body_path: Path, content_type: str, target_dir: Path) -> list[dict[str, str]]:
    boundary = _multipart_boundary(content_type)
    final_boundary = boundary + b"--"
    files: list[dict[str, str]] = []

    with body_path.open("rb") as handle:
        line = handle.readline()
        while line and line.rstrip(b"\r\n") != boundary:
            line = handle.readline()

        while line:
            headers: list[bytes] = []
            while True:
                line = handle.readline()
                if not line:
                    return files
                if line in (b"\r\n", b"\n"):
                    break
                headers.append(line)

            header_text = b"".join(headers).decode("utf-8", errors="ignore")
            match = re.search(r'filename="([^"]+)"', header_text)
            filename = Path(match.group(1)).name if match else ""
            target = target_dir / filename if filename else None
            pending: bytes | None = None
            out = target.open("wb") if target else None
            try:
                while True:
                    line = handle.readline()
                    if not line:
                        if pending and out:
                            out.write(pending)
                        return files
                    stripped = line.rstrip(b"\r\n")
                    if stripped == boundary or stripped == final_boundary:
                        if pending and out:
                            if pending.endswith(b"\r\n"):
                                pending = pending[:-2]
                            elif pending.endswith(b"\n"):
                                pending = pending[:-1]
                            out.write(pending)
                        if target:
                            files.append({"name": filename, "path": str(target)})
                        if stripped == final_boundary:
                            return files
                        break
                    if pending and out:
                        out.write(pending)
                    pending = line
            finally:
                if out:
                    out.close()


def _copy_exact_request_body(source, target, length: int, chunk_size: int = 64 * 1024) -> int:
    remaining = length
    copied = 0
    while remaining > 0:
        chunk = source.read(min(chunk_size, remaining))
        if not chunk:
            break
        target.write(chunk)
        copied += len(chunk)
        remaining -= len(chunk)
    return copied


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

    def _validate_output_dir_param(self, params: dict[str, object]) -> None:
        raw = params.get("output_dir")
        if not raw:
            return
        outputs = self._outputs_dir().resolve()
        requested = Path(str(raw))
        if not requested.is_absolute():
            requested = outputs / requested
        try:
            requested.resolve().relative_to(outputs)
        except ValueError as exc:
            raise ValueError("bad_output_dir: output_dir must be inside data/outputs") from exc

    @staticmethod
    def _is_user_input_error(exc: Exception) -> bool:
        message = str(exc)
        return isinstance(exc, (KeyError, ValueError, FileNotFoundError, PermissionError, zipfile.BadZipFile, InvalidFileException)) or any(
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
                self._validate_output_dir_param(params)
                result = self.registry.run_tool(tool_id, params)
            except Exception as exc:
                message = str(exc)
                error_kind = "bad_output_dir" if message.startswith("bad_output_dir") else "tool_error"
                self._send_json(
                    {"status": "error", "error": message, "message": message, "user_message": message, "error_kind": error_kind},
                    400 if self._is_user_input_error(exc) else 500,
                )
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
        tmp_path: Path | None = None
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            with tempfile.NamedTemporaryFile(delete=False, dir=target_dir) as tmp:
                copied = _copy_exact_request_body(self.rfile, tmp, length)
                if length and copied != length:
                    raise ValueError("upload truncated")
                tmp_path = Path(tmp.name)
            files = _parse_multipart_files_from_disk(tmp_path, content_type, target_dir)
            if tmp_path.exists():
                tmp_path.unlink()
            self._send_json({"status": "ok", "session": session, "files": files, "folder": str(target_dir)})
        except Exception as exc:
            shutil.rmtree(target_dir, ignore_errors=True)
            message = str(exc) or type(exc).__name__
            self._send_json({"status": "error", "error": message, "user_message": message, "error_kind": type(exc).__name__}, 400)

    def _handle_package(self) -> None:
        try:
            params = self._read_json_body()
        except Exception:
            self._send_json({"error": "bad request"}, 400)
            return
        name = str(params.get("name") or "BOM导出").strip() or "BOM导出"
        members: list[Path] = []
        seen: set[str] = set()
        try:
            requested_files = params.get("files") or []
            for raw in requested_files:
                target = _resolve_output_member(self._outputs_dir(), raw)
                if target and target.is_file() and str(target) not in seen:
                    seen.add(str(target))
                    members.append(target)
        except ValueError as exc:
            self._send_json({"status": "error", "error": str(exc), "user_message": str(exc), "error_kind": "bad_package_path"}, 400)
            return
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
