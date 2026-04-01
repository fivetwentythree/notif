from __future__ import annotations

from pathlib import Path
import json

from booking_monitor.models import MonitorState, utc_now_iso


class JsonStateStore:
    def __init__(self, state_dir: str | Path) -> None:
        self.state_dir = Path(state_dir)
        self.path = self.state_dir / "state.json"

    def load(self) -> MonitorState:
        if not self.path.exists():
            return MonitorState()
        payload = json.loads(self.path.read_text())
        return MonitorState.from_dict(payload)

    def save(self, state: MonitorState) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        state.updated_at = utc_now_iso()
        temp_path = self.path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n")
        temp_path.replace(self.path)
