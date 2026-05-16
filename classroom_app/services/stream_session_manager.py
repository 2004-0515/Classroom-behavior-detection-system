from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from typing import Any

from config import Config


@dataclass
class VideoStreamSession:
    task_id: str
    input_path: str
    output_path: str
    output_filename: str
    filename: str
    frame_queue: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=Config.PREVIEW_QUEUE_SIZE))
    done_event: threading.Event = field(default_factory=threading.Event)
    stop_event: threading.Event = field(default_factory=threading.Event)
    stats: dict[str, Any] = field(default_factory=dict)
    latest_original_frame: Any = None
    latest_processed_frame_number: int = 0


class StreamSessionManager:
    def __init__(self):
        self._video_sessions: dict[str, VideoStreamSession] = {}
        self._lock = threading.Lock()

    def create_video_session(self, task_id: str, input_path: str, output_path: str, output_filename: str, filename: str, stats: dict[str, Any]):
        session = VideoStreamSession(
            task_id=task_id,
            input_path=input_path,
            output_path=output_path,
            output_filename=output_filename,
            filename=filename,
            stats=stats,
        )
        with self._lock:
            self._video_sessions[task_id] = session
        return session

    def get_video_session(self, task_id: str):
        with self._lock:
            return self._video_sessions.get(task_id)

    def pop_video_session(self, task_id: str):
        with self._lock:
            return self._video_sessions.pop(task_id, None)

    def cleanup_video_session(self, task_id: str):
        with self._lock:
            session = self._video_sessions.get(task_id)
            if session and session.done_event.is_set():
                self._video_sessions.pop(task_id, None)

    def update_video_session(self, task_id: str, **kwargs):
        with self._lock:
            session = self._video_sessions.get(task_id)
            if not session:
                return None
            for key, value in kwargs.items():
                setattr(session, key, value)
            return session
