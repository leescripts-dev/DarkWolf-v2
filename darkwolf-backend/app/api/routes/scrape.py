import os
import re
import shutil
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException


router = APIRouter(prefix="/api/v1/scrape", tags=["Scrape"])

PROJECT_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = PROJECT_ROOT / "darkwolf-backend"
SCRIPT_PATH = BACKEND_ROOT / "run_full_scrape.ps1"
LOG_ROOT = BACKEND_ROOT / "logs"
STAGE_NAMES = ["inc-ransom", "html-leak-sites", "api-leak-sites", "javascript-leak-sites"]

_lock = threading.Lock()
_state = {
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "current_stage": None,
    "stages": [{"name": name, "status": "queued"} for name in STAGE_NAMES],
    "exit_code": None,
    "log_path": None,
    "message": None,
}


def _copy_state():
    with _lock:
        return {**_state, "stages": [stage.copy() for stage in _state["stages"]]}


def _append_line(line: str, log_file):
    message = line.strip()
    if not message:
        return
    log_file.write(line)
    log_file.flush()
    with _lock:
        _state["message"] = message[-500:]
        start = re.search(r"Starting (.+?) \(live\)\.\.\.", message)
        if start:
            stage_name = start.group(1)
            _state["current_stage"] = stage_name
            for stage in _state["stages"]:
                if stage["name"] == stage_name:
                    stage["status"] = "running"
                    break
        completed = re.search(r"Completed (.+?)\.", message)
        if completed:
            stage_name = completed.group(1)
            for stage in _state["stages"]:
                if stage["name"] == stage_name:
                    stage["status"] = "completed"
                    break
        warning = re.search(r"WARNING: (.+?) reported failure\(s\)", message)
        if warning:
            stage_name = warning.group(1)
            for stage in _state["stages"]:
                if stage["name"] == stage_name:
                    stage["status"] = "completed_with_errors"
                    break


def _run_scrape(log_path: Path):
    powershell = shutil.which("pwsh.exe") or shutil.which("powershell.exe") or "powershell.exe"
    command = [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT_PATH)]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        with log_path.open("w", encoding="utf-8", errors="replace") as log_file:
            process = subprocess.Popen(
                command,
                cwd=str(PROJECT_ROOT),
                env=os.environ.copy(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
            )
            with _lock:
                _state["status"] = "running"
                _state["process_id"] = process.pid
            assert process.stdout is not None
            for line in process.stdout:
                _append_line(line, log_file)
            exit_code = process.wait()

        with _lock:
            _state["exit_code"] = exit_code
            _state["finished_at"] = datetime.now(timezone.utc).isoformat()
            _state["current_stage"] = None
            if exit_code == 0:
                _state["status"] = "completed"
                _state["message"] = "Full scrape cycle completed successfully."
                for stage in _state["stages"]:
                    if stage["status"] == "queued":
                        stage["status"] = "completed"
            elif any(stage["status"] == "completed_with_errors" for stage in _state["stages"]):
                _state["status"] = "completed_with_errors"
                _state["message"] = "Scrape cycle finished; one or more stages reported site errors."
            else:
                _state["status"] = "failed"
                _state["message"] = f"Scrape launcher exited with code {exit_code}. Check the run log."
    except Exception as exc:
        with _lock:
            _state["status"] = "failed"
            _state["finished_at"] = datetime.now(timezone.utc).isoformat()
            _state["current_stage"] = None
            _state["message"] = f"Could not run the scrape cycle: {type(exc).__name__}: {exc}"


@router.post("/start")
def start_scrape():
    if not SCRIPT_PATH.is_file():
        raise HTTPException(status_code=500, detail=f"Scrape launcher not found: {SCRIPT_PATH}")

    with _lock:
        if _state["status"] in {"starting", "running"}:
            raise HTTPException(status_code=409, detail="A full scrape cycle is already running.")
        LOG_ROOT.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_path = LOG_ROOT / f"ui-full-scrape-{timestamp}.log"
        _state.update({
            "status": "starting",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
            "current_stage": None,
            "stages": [{"name": name, "status": "queued"} for name in STAGE_NAMES],
            "exit_code": None,
            "log_path": str(log_path),
            "message": "Starting full scrape cycle and checking MongoDB and Tor.",
            "process_id": None,
        })

    threading.Thread(target=_run_scrape, args=(log_path,), daemon=True, name="full-scrape-runner").start()
    return _copy_state()


@router.get("/status")
def scrape_status():
    return _copy_state()
