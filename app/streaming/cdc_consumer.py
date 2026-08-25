import threading
import time
from typing import Callable, Optional, Dict, Any
from app.streaming.ring_buffer import InvertedRingBuffer

class CDCConsumer:
    """Consumer for Database Change Data Capture (CDC) events feeding the in-memory streaming buffer."""

    def __init__(self, buffer: InvertedRingBuffer):
        self.buffer = buffer
        self.is_running = False
        self._thread: Optional[threading.Thread] = None

    def start_mock_stream(self, event_generator: Callable[[], Dict[str, Any]], interval_sec: float = 0.1):
        self.is_running = True
        def _loop():
            while self.is_running:
                try:
                    event = event_generator()
                    if event:
                        self.buffer.append_event(event)
                except Exception:
                    pass
                time.sleep(interval_sec)

        self._thread = threading.Thread(target=_loop, daemon=True, name="CDCConsumerThread")
        self._thread.start()

    def stop(self):
        self.is_running = False
