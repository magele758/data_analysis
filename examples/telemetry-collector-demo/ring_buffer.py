import threading
import time
from typing import List, Dict, Any, Optional
import pyarrow as pa

class InvertedRingBuffer:
    """Thread-safe in-memory ring buffer for streaming real-time events with micro-batch Arrow conversion."""

    def __init__(self, capacity: int = 100000):
        self.capacity = capacity
        self.buffer: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def push(self, event: Dict[str, Any]):
        self.append_event(event)

    def append_event(self, event: Dict[str, Any]):
        with self._lock:
            if len(self.buffer) >= self.capacity:
                self.buffer.pop(0)  # Evict oldest
            event["_ingest_time"] = time.time()
            self.buffer.append(event)

    def append_batch(self, events: List[Dict[str, Any]]):
        with self._lock:
            for ev in events:
                ev["_ingest_time"] = time.time()
                self.buffer.append(ev)
            if len(self.buffer) > self.capacity:
                self.buffer = self.buffer[-self.capacity:]

    def get_latest(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return list(reversed(self.buffer[-limit:]))

    def dump_to_arrow(self, since_timestamp: Optional[float] = None) -> Optional[pa.Table]:
        with self._lock:
            if not self.buffer:
                return None
            if since_timestamp:
                records = [e for e in self.buffer if e.get("_ingest_time", 0) >= since_timestamp]
            else:
                records = list(self.buffer)
            if not records:
                return None
            return pa.Table.from_pylist(records)

    def clear(self):
        with self._lock:
            self.buffer.clear()
