import json
import threading
import socket
import secrets
from http.server import BaseHTTPRequestHandler, HTTPServer
from PyQt6.QtCore import QObject, pyqtSignal


class WebServerSignals(QObject):
    goals_updated = pyqtSignal(dict)
    alerts_toggled = pyqtSignal(bool)
    theme_toggled = pyqtSignal(bool)
    test_notification_requested = pyqtSignal()
    reset_requested = pyqtSignal()


class GoalsHTTPRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress logging to stdout/stderr to keep the console clean
        pass

    def _set_headers(self, content_type="application/json", status=200):
        self.send_response(status)
        self.send_header("Content-type", content_type)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-TrueHour-Token")
        self.end_headers()

    def _is_request_authorized(self, is_post=False) -> bool:
        host = self.headers.get("Host", "")
        allowed_hosts = [
            f"127.0.0.1:{self.server.server_port}",
            f"localhost:{self.server.server_port}",
        ]
        if host and host.lower() not in allowed_hosts:
            return False

        origin = self.headers.get("Origin")
        if origin:
            allowed_origins = [
                f"http://127.0.0.1:{self.server.server_port}",
                f"http://localhost:{self.server.server_port}",
            ]
            if origin.lower() not in allowed_origins:
                return False

        if is_post:
            token = self.headers.get("X-TrueHour-Token", "")
            if not token or token != getattr(self.server, "auth_token", ""):
                return False

        return True

    def do_OPTIONS(self):
        if not self._is_request_authorized(is_post=False):
            self._set_headers(status=403)
            self.wfile.write(json.dumps({"error": "Forbidden"}).encode("utf-8"))
            return
        self._set_headers(status=200)

    def do_GET(self):
        if not self._is_request_authorized(is_post=False):
            self._set_headers(status=403)
            self.wfile.write(json.dumps({"error": "Forbidden"}).encode("utf-8"))
            return

        if self.path == "/":
            # Serve the goals HTML page
            try:
                import os
                import sys

                # Check for user-customized template next to executable/script
                if getattr(sys, "frozen", False):
                    root_dir = os.path.dirname(sys.executable)
                else:
                    root_dir = os.path.dirname(
                        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    )

                user_template_path = os.path.join(
                    root_dir, "templates", "goals_dashboard.html"
                )

                if os.path.exists(user_template_path):
                    template_path = user_template_path
                elif getattr(sys, "frozen", False):
                    # Fallback to PyInstaller's bundled temp directory
                    mei_dir = getattr(sys, "_MEIPASS", "")
                    template_path = os.path.join(
                        mei_dir, "templates", "goals_dashboard.html"
                    )
                else:
                    template_path = user_template_path

                with open(template_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # Dynamic injection of port and configuration state to avoid initial fetch delay
                data = self.server.get_state_callback()
                json_state = json.dumps(data)
                auth_token = getattr(self.server, "auth_token", "")
                injection = f"window.INITIAL_STATE = {json_state};\nwindow.SERVER_TOKEN = \"{auth_token}\";"
                content = content.replace(
                    "/*{{INITIAL_STATE}}*/", injection
                )

                self._set_headers(content_type="text/html", status=200)
                self.wfile.write(content.encode("utf-8"))
            except Exception as e:
                self._set_headers(content_type="text/plain", status=500)
                self.wfile.write(f"Internal Server Error: {e}".encode("utf-8"))

        elif self.path == "/api/goals":
            try:
                data = self.server.get_state_callback()
                self._set_headers(status=200)
                self.wfile.write(json.dumps(data).encode("utf-8"))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
        else:
            self._set_headers(content_type="text/plain", status=404)
            self.wfile.write(b"Not Found")

    def do_POST(self):
        if not self._is_request_authorized(is_post=True):
            self._set_headers(status=403)
            self.wfile.write(json.dumps({"error": "Forbidden"}).encode("utf-8"))
            return

        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)

        payload = {}
        if post_data:
            try:
                payload = json.loads(post_data.decode("utf-8"))
            except Exception:
                self._set_headers(status=400)
                self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode("utf-8"))
                return

        if self.path == "/api/goals":
            data_to_emit = {}
            if "weekly_goals" in payload:
                weekly_goals = payload["weekly_goals"]
                if isinstance(weekly_goals, dict):
                    sanitized = {}
                    for k, v in weekly_goals.items():
                        try:
                            sanitized[k] = float(v)
                        except (ValueError, TypeError):
                            sanitized[k] = 0.0
                    data_to_emit["weekly_goals"] = sanitized
            if "weekly_earnings_goal" in payload:
                try:
                    data_to_emit["weekly_earnings_goal"] = float(
                        payload["weekly_earnings_goal"]
                    )
                except (ValueError, TypeError):
                    data_to_emit["weekly_earnings_goal"] = 0.0
            if "earnings_goal_period" in payload:
                data_to_emit["earnings_goal_period"] = str(
                    payload["earnings_goal_period"]
                )

            if data_to_emit:
                self.server.signals.goals_updated.emit(data_to_emit)
                self._set_headers(status=200)
                self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
            else:
                self._set_headers(status=400)
                self.wfile.write(
                    json.dumps(
                        {
                            "error": "No valid weekly_goals or weekly_earnings_goal provided"
                        }
                    ).encode("utf-8")
                )

        elif self.path == "/api/settings":
            if "enable_goal_tray_alerts" in payload:
                enabled = bool(payload["enable_goal_tray_alerts"])
                self.server.signals.alerts_toggled.emit(enabled)
            if "dark_mode" in payload:
                dark_mode = bool(payload["dark_mode"])
                self.server.signals.theme_toggled.emit(dark_mode)

            self._set_headers(status=200)
            self.wfile.write(json.dumps({"success": True}).encode("utf-8"))

        elif self.path == "/api/test-notification":
            self.server.signals.test_notification_requested.emit()
            self._set_headers(status=200)
            self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
        elif self.path == "/api/goals/reset":
            self.server.signals.reset_requested.emit()
            self._set_headers(status=200)
            self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
        else:
            self._set_headers(status=404)
            self.wfile.write(b"Not Found")


class GoalsWebServer(HTTPServer):
    def __init__(
        self, server_address, RequestHandlerClass, get_state_callback, signals
    ):
        super().__init__(server_address, RequestHandlerClass)
        self.get_state_callback = get_state_callback
        self.signals = signals
        self.auth_token = secrets.token_hex(16)


def find_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class WebServerManager(QObject):
    def __init__(self, get_state_callback, parent=None):
        super().__init__(parent)
        self.get_state_callback = get_state_callback
        self.signals = WebServerSignals()
        self.port = find_free_port()
        self.server = None
        self.thread = None
        self.running = False

    def start(self):
        if self.running:
            return

        self.server = GoalsWebServer(
            ("127.0.0.1", self.port),
            GoalsHTTPRequestHandler,
            self.get_state_callback,
            self.signals,
        )
        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.running = True
        self.thread.start()

    def _run_server(self):
        try:
            self.server.serve_forever()
        except Exception as e:
            print(f"[TrueHour Web Server] Server encountered error: {e}")

    def stop(self):
        if not self.running:
            return
        self.running = False
        if self.server:
            # shutdown() closes serve_forever cleanly
            self.server.shutdown()
            self.server.server_close()
        if self.thread:
            self.thread.join(timeout=1.0)

