"""Headless live battle sampling and model session (roadmap B4).

Decouples the sampling worker, :class:`~hbr_live_app.model.BattleModel` updates,
automatic team-build capture and snapshot delivery from ``hbr_live_app.app.App``.

Public interface:

* :meth:`LiveSession.start` -- start the read-only memory sampling thread;
* :meth:`LiveSession.stop` -- signal the sampling thread to stop;
* :meth:`LiveSession.pause` -- pause or resume sampling;
* :meth:`LiveSession.events` -- drain queued worker packets, update the model
  and team store, and return processed ``(kind, payload)`` events;
* :meth:`LiveSession.latest_snapshot` -- return an immutable (deep-copied)
  contract-compliant :class:`~hbr_live_core.schema.Snapshot`.

Can also be run from the command line without Tk::

    python -B -m hbr_live_core.live_session --replay sessions/<run>.jsonl
    python -B -m hbr_live_core.live_session --once
"""
import argparse
import copy
import json
import queue
import sqlite3
import sys
import threading
import time
from pathlib import Path

from hbr_live_app.model import BattleModel
from .snapshot import live_snapshot

ROOT = Path(__file__).resolve().parent.parent


class LiveSession:
    """Thread-safe coordinator for battle sampling, model updates and snapshots."""

    def __init__(self, session_dir=None, team_store=None, runner=None):
        self.session_dir = Path(session_dir) if session_dir is not None else (ROOT / 'sessions')
        self.team_store = team_store
        self._runner = runner
        self.model = BattleModel()
        self.queue = queue.Queue()
        self.stop_event = threading.Event()
        self.paused = threading.Event()
        self.thread = None
        self.connected = False
        self.session_path = None
        self.last_sample = None
        self.last_packet = None
        self.last_events = []
        self._lock = threading.RLock()

    def is_running(self):
        return self.thread is not None and self.thread.is_alive()

    def clear_queue(self):
        while True:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break

    def start(self):
        """Start a new background sampling thread if not already running."""
        if self.is_running():
            return False
        self.clear_queue()
        self.stop_event.clear()
        self.paused.clear()
        self.connected = False
        runner = self._runner
        if runner is None:
            from hbr_live_app.source import run as runner
        self.thread = threading.Thread(
            target=runner,
            args=(self.stop_event, self.paused, self.queue.put, self.session_dir),
            daemon=True,
        )
        self.thread.start()
        return True

    def stop(self, wait=False, timeout=2.0):
        """Signal the sampling worker to stop; optionally wait for thread exit."""
        self.stop_event.set()
        if wait and self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=timeout)

    def pause(self, paused=None):
        """Set or toggle the pause state; return ``True`` when paused."""
        if paused is None:
            paused = not self.paused.is_set()
        if paused:
            self.paused.set()
        else:
            self.paused.clear()
        return self.paused.is_set()

    def apply_event(self, kind, data):
        """Apply one worker message to the model and return enriched event info."""
        with self._lock:
            if kind == 'connected':
                self.model = BattleModel()
                self.model.run_id = data['run_id']
                self.session_path = data.get('path')
                self.last_sample = None
                self.connected = True
                return kind, dict(data)
            if kind == 'snapshot':
                self.model.update(data)
                team_captured = False
                team_error = None
                if self.team_store is not None:
                    try:
                        team_captured = bool(
                            self.team_store.observe(
                                self.model.run_id,
                                self.model.players,
                                self.model.turn_context,
                            )
                        )
                    except (OSError, sqlite3.Error, ValueError) as exc:
                        team_error = str(exc)
                self.last_packet = data
                self.last_events = list(data.get('events', []))
                return kind, dict(
                    packet=data,
                    events=self.last_events,
                    team_captured=team_captured,
                    team_error=team_error,
                )
            if kind == 'heartbeat':
                self.last_sample = data
                return kind, data
            if kind == 'stopped':
                self.connected = False
                return kind, data
            return kind, data

    def events(self, limit=200):
        """Drain up to ``limit`` queued worker messages and update session state."""
        processed = []
        try:
            for _ in range(limit):
                kind, data = self.queue.get_nowait()
                processed.append(self.apply_event(kind, data))
        except queue.Empty:
            pass
        return processed

    def latest_snapshot(self, immutable=True):
        """Return the latest :class:`~hbr_live_core.schema.Snapshot`.

        When ``immutable=True`` (the default), a deep copy is returned so UI or
        HTTP consumers can never mutate internal model state across threads.
        """
        with self._lock:
            snap = live_snapshot(self.model, self.connected)
            return copy.deepcopy(snap) if immutable else snap

    def export(self):
        """Return a deep copy of the full battle export dictionary."""
        with self._lock:
            return copy.deepcopy(self.model.export())

    def replay_file(self, path):
        """Replay a recorded ``sessions/*.jsonl`` file into this session."""
        path = Path(path)
        with path.open(encoding='utf-8') as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                packet = json.loads(line)
                if packet.get('kind') == 'start':
                    self.apply_event('connected', dict(run_id=packet.get('run_id'), path=str(path)))
                elif 'enemies' in packet:
                    self.apply_event('snapshot', packet)
                elif packet.get('kind') == 'end':
                    self.apply_event('stopped', None)
        # Keep connected=True after replay if enemies were loaded so callers can inspect the snapshot.
        if self.model.enemies:
            self.connected = True
        return self.latest_snapshot(immutable=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Headless HBR Live session runner (B4).')
    parser.add_argument('--replay', type=Path, help='Replay a recorded session JSONL file and output the snapshot JSON.')
    parser.add_argument('--once', action='store_true', help='Connect to the game, wait for the first complete snapshot, print JSON and exit.')
    parser.add_argument('--timeout', type=float, default=30.0, help='Seconds to wait when --once is used.')
    args = parser.parse_args(argv)

    session = LiveSession()
    if args.replay:
        snap = session.replay_file(args.replay)
        print(json.dumps(snap, ensure_ascii=False, indent=2))
        return 0

    session.start()
    deadline = time.monotonic() + args.timeout
    try:
        while time.monotonic() < deadline:
            for kind, payload in session.events():
                if kind == 'error':
                    print(json.dumps({'ok': False, 'error': payload}, ensure_ascii=False), file=sys.stderr)
                    return 1
                if kind == 'snapshot':
                    snap = session.latest_snapshot(immutable=True)
                    if not args.once or (snap.get('players') and not payload['packet'].get('loading_details')):
                        print(json.dumps(snap, ensure_ascii=False, indent=2))
                        if args.once:
                            return 0
                if kind == 'stopped':
                    return 0
            time.sleep(0.05)
    finally:
        session.stop(wait=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
