"""Persistent scheduler service for MusicNews."""
import json
import os
import signal
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from main import run_once
from src.utils import setup_logger

logger = setup_logger(__name__)

HOST = "127.0.0.1"
PORT = int(os.getenv("MUSICNEWS_SERVICE_PORT", "4332"))
SCHEDULE_HOUR = int(os.getenv("MUSICNEWS_SCHEDULE_HOUR", "9"))
SCHEDULE_MINUTE = int(os.getenv("MUSICNEWS_SCHEDULE_MINUTE", "0"))
POLL_SECONDS = max(int(os.getenv("MUSICNEWS_SERVICE_POLL_SECONDS", "15")), 5)

RUNTIME_DIR = Path(".runtime")
STATE_FILE = RUNTIME_DIR / "musicnews_service_state.json"


class ServiceState:
    def __init__(self):
        self._lock = threading.Lock()
        self._state = {
            "service": "starting",
            "pid": os.getpid(),
            "startedAt": datetime.now().isoformat(timespec="seconds"),
            "schedule": f"{SCHEDULE_HOUR:02d}:{SCHEDULE_MINUTE:02d}",
            "lastAttemptDate": None,
            "lastSuccessDate": None,
            "lastRunStartedAt": None,
            "lastRunFinishedAt": None,
            "lastRunMode": None,
            "lastRunSuccess": None,
            "lastSummaryPath": None,
            "lastError": None,
            "jobRunning": False
        }
        self._load()
        self._sync_with_existing_output()
        self._state["service"] = "running"
        self._persist()

    def _load(self):
        if not STATE_FILE.exists():
            return
        try:
            payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return
        for key, value in payload.items():
            if key in self._state:
                self._state[key] = value

    def _persist(self):
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(
            json.dumps(self._state, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def _sync_with_existing_output(self):
        today = datetime.now().strftime("%Y-%m-%d")
        summary_path = get_latest_successful_summary_for_date(today)
        if not summary_path:
            return
        self._state["lastAttemptDate"] = today
        self._state["lastSuccessDate"] = today
        self._state["lastRunMode"] = "send"
        self._state["lastRunSuccess"] = True
        self._state["lastSummaryPath"] = str(summary_path)
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self._state["lastRunFinishedAt"] = summary.get("finished_at")
        except Exception:
            pass

    def snapshot(self):
        with self._lock:
            return dict(self._state)

    def mark_running(self):
        with self._lock:
            self._state["service"] = "running"
            self._state["pid"] = os.getpid()
            self._persist()

    def mark_stopping(self):
        with self._lock:
            self._state["service"] = "stopping"
            self._persist()

    def mark_attempt_started(self):
        now = datetime.now()
        with self._lock:
            self._state["jobRunning"] = True
            self._state["lastAttemptDate"] = now.strftime("%Y-%m-%d")
            self._state["lastRunStartedAt"] = now.isoformat(timespec="seconds")
            self._state["lastRunMode"] = "send"
            self._state["lastError"] = None
            self._persist()

    def mark_attempt_finished(self, result):
        now = datetime.now()
        with self._lock:
            self._state["jobRunning"] = False
            self._state["lastRunFinishedAt"] = now.isoformat(timespec="seconds")
            self._state["lastRunSuccess"] = bool(result.get("success"))
            self._state["lastSummaryPath"] = result.get("summary_path")
            self._state["lastError"] = result.get("error")
            if result.get("success") and result.get("sent"):
                self._state["lastSuccessDate"] = now.strftime("%Y-%m-%d")
            self._persist()


def get_latest_successful_summary_for_date(day_str):
    day_dir = Path("output") / day_str
    if not day_dir.exists():
        return None

    run_dirs = sorted(
        [item for item in day_dir.iterdir() if item.is_dir()],
        key=lambda item: item.name,
        reverse=True
    )

    for run_dir in run_dirs:
        summary_path = run_dir / "run_summary.json"
        if not summary_path.exists():
            continue
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if summary.get("mode") == "send" and summary.get("sent") is True:
            return summary_path

    return None


class Handler(BaseHTTPRequestHandler):
    state = None

    def log_message(self, format, *args):
        del format, args
        return

    def do_GET(self):
        if self.path not in ("/health", "/status"):
            self.send_response(404)
            self.end_headers()
            return

        payload = self.state.snapshot()
        payload["ok"] = True
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def should_run_today(state_snapshot):
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    if state_snapshot.get("lastAttemptDate") == today:
        return False
    if now.hour > SCHEDULE_HOUR:
        return True
    if now.hour == SCHEDULE_HOUR and now.minute >= SCHEDULE_MINUTE:
        return True
    return False


def run_scheduler(state, stop_event):
    while not stop_event.is_set():
        snapshot = state.snapshot()
        if not snapshot.get("jobRunning") and should_run_today(snapshot):
            logger.info("Scheduled send started")
            state.mark_attempt_started()
            result = run_once(send_email=True)
            state.mark_attempt_finished(result)
            logger.info("Scheduled send finished: %s", result.get("success"))

        stop_event.wait(POLL_SECONDS)


def main():
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    stop_event = threading.Event()
    state = ServiceState()
    Handler.state = state
    server = ThreadingHTTPServer((HOST, PORT), Handler)

    def handle_stop(signum, frame):
        del signum, frame
        state.mark_stopping()
        stop_event.set()
        server.shutdown()

    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)

    scheduler_thread = threading.Thread(
        target=run_scheduler,
        args=(state, stop_event),
        daemon=True
    )
    scheduler_thread.start()

    try:
        state.mark_running()
        logger.info("MusicNews service listening on %s:%s", HOST, PORT)
        server.serve_forever(poll_interval=0.5)
    finally:
        stop_event.set()
        scheduler_thread.join(timeout=5)
        state.mark_stopping()
        server.server_close()


if __name__ == "__main__":
    main()
