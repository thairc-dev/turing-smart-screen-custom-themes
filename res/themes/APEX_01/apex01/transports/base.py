from __future__ import annotations

from abc import ABC, abstractmethod


class TransportError(RuntimeError):
    pass


class DisplayTransport(ABC):
    @abstractmethod
    def open(self) -> None:
        ...

    @abstractmethod
    def write(self, data: bytes | bytearray | memoryview, timeout_ms: int = 1000) -> None:
        ...

    @abstractmethod
    def close(self) -> None:
        ...

    def __enter__(self) -> "DisplayTransport":
        self.open()
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()
