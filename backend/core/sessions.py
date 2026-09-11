"""Session and conversation history persistence for FileOrganizer agent."""
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

SESSIONS_DIR = Path(__file__).parent.parent / ".sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


class SessionStore:
    def __init__(self, base_dir: Path = SESSIONS_DIR):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_session_path(self, session_id: str) -> Path:
        # Sanitize session_id to prevent path traversal
        clean_id = "".join(c for c in session_id if c.isalnum() or c in "-_")
        if not clean_id:
            clean_id = "default"
        return self.base_dir / f"{clean_id}.json"

    def list_sessions(self) -> List[Dict[str, Any]]:
        """Returns metadata for all saved sessions, sorted by last updated."""
        sessions = []
        for file in self.base_dir.glob("*.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                sessions.append({
                    "id": data.get("id", file.stem),
                    "title": data.get("title", "Untitled Session"),
                    "folder_path": data.get("folder_path", ""),
                    "created_at": data.get("created_at", 0),
                    "updated_at": data.get("updated_at", 0),
                    "turn_count": len(data.get("turns", [])),
                })
            except Exception:
                continue

        return sorted(sessions, key=lambda s: s["updated_at"], reverse=True)

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Loads a session by ID."""
        path = self._get_session_path(session_id)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def create_session(self, title: Optional[str] = None, folder_path: str = "") -> Dict[str, Any]:
        """Creates and saves a new empty session."""
        session_id = f"session_{uuid.uuid4().hex[:12]}"
        now = time.time()
        session_data = {
            "id": session_id,
            "title": title or "New Organization Session",
            "folder_path": folder_path,
            "created_at": now,
            "updated_at": now,
            "turns": [],
        }
        self.save_session(session_data)
        return session_data

    def save_session(self, session_data: Dict[str, Any]):
        """Saves session data to disk."""
        session_id = session_data.get("id")
        if not session_id:
            session_id = f"session_{uuid.uuid4().hex[:12]}"
            session_data["id"] = session_id

        session_data["updated_at"] = time.time()
        path = self._get_session_path(session_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=2)

    def append_turn(self, session_id: str, turn: Dict[str, Any]) -> Dict[str, Any]:
        """Appends a turn to an existing session or creates a new one."""
        session = self.get_session(session_id)
        if not session:
            session = self.create_session(
                title=turn.get("content", "Session")[:40],
                folder_path=turn.get("folder_path", "")
            )

        # Update title if it's the first user turn
        if len(session.get("turns", [])) == 0 and turn.get("role") == "user":
            content = turn.get("content", "").strip()
            session["title"] = (content[:36] + "...") if len(content) > 36 else content

        if turn.get("folder_path") and not session.get("folder_path"):
            session["folder_path"] = turn.get("folder_path")

        session.setdefault("turns", []).append(turn)
        self.save_session(session)
        return session

    def update_artifact_status(self, session_id: str, artifact_id: str, status: str) -> bool:
        """Updates the status of a specific plan artifact within a session."""
        session = self.get_session(session_id)
        if not session:
            return False

        updated = False
        for turn in session.get("turns", []):
            artifact = turn.get("plan_artifact")
            if artifact and artifact.get("artifact_id") == artifact_id:
                artifact["status"] = status
                updated = True

        if updated:
            self.save_session(session)
        return updated

    def delete_session(self, session_id: str) -> bool:
        """Deletes a session file."""
        path = self._get_session_path(session_id)
        if path.exists():
            try:
                path.unlink()
                return True
            except Exception:
                return False
        return False
