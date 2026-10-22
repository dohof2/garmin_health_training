"""Explicit foreground session; no login item, service, or auto-start."""
from __future__ import annotations

import argparse
import fcntl
import os
from pathlib import Path
import select
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
PORT = 8765
URL = f'http://127.0.0.1:{PORT}/#dashboard'


def build_frontend() -> None:
    frontend = ROOT / 'frontend'
    index = frontend / 'dist' / 'index.html'
    inputs = [frontend / 'package.json', frontend / 'package-lock.json', frontend / 'vite.config.ts']
    inputs.extend(p for p in (frontend / 'src').rglob('*') if p.is_file())
    inputs.append(frontend / 'index.html')
    inputs.extend(frontend.glob('tsconfig*.json'))
    if index.exists() and all(p.stat().st_mtime <= index.stat().st_mtime for p in inputs if p.exists()):
        return
    npm = shutil.which('npm')
    if not npm:
        raise RuntimeError('Node/npm is missing. Install Node.js 24, then run make setup.')
    print('Preparing the app…', flush=True)
    subprocess.run([npm, 'run', 'build'], cwd=frontend, check=True)


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    # The launcher only signals the process group it created.
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def run(*, check: bool = False, open_browser: bool = True) -> None:
    runtime = ROOT / 'data' / 'local-app'
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / 'session.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if open_browser:
                webbrowser.open(URL)
            print('The app is already open. Use its existing Terminal window to quit.')
            return
        build_frontend()
        if check:
            print('Local launcher and frontend are ready.')
            return
        with socket.socket() as probe:
            # A just-closed session may leave TCP connections in TIME_WAIT.
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(('127.0.0.1', PORT))
            except OSError as error:
                raise RuntimeError(f'Port {PORT} is occupied by another process. Nothing was stopped.') from error
        log_path = runtime / 'server.log'
        with log_path.open('a') as log:
            process = subprocess.Popen([
                str(ROOT / '.venv' / 'bin' / 'python'), '-m', 'uvicorn',
                'app.local_app:app', '--app-dir', 'backend', '--host', '127.0.0.1',
                '--port', str(PORT),
            ], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError(f'The server could not start. See {log_path}')
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/api/health', timeout=1) as response:
                            if response.status == 200:
                                break
                    except (OSError, ValueError):
                        time.sleep(.25)
                else:
                    raise RuntimeError(f'Startup timed out. See {log_path}')
                if open_browser:
                    webbrowser.open(URL)
                print(f'Garmin is open: {URL}\n\nKeep this window open while using the app.\nPress Return here to QUIT. Closing this Terminal session also stops the app.\nClosing only the browser tab does not quit.\n', flush=True)
                while process.poll() is None:
                    readable, _, _ = select.select([sys.stdin], [], [], .5)
                    if readable:
                        sys.stdin.readline()
                        break
                if process.poll() is not None:
                    raise RuntimeError(f'The app stopped unexpectedly. See {log_path}')
            finally:
                stop_process(process)
                print('Garmin stopped.', flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Build/check without starting the server')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    for event in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(event, interrupted)
    try:
        run(check=args.check, open_browser=not args.no_browser)
        return 0
    except KeyboardInterrupt:
        return 0
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f'Could not open Garmin: {error}', file=sys.stderr)
        if sys.stdin.isatty():
            input('Press Return to close. ')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
