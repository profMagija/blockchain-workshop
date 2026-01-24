import logging
from typing import Callable
import threading
import socket


class EventHandler[*T]:
    def __init__(self):
        self.listeners: list[Callable[[*T], None]] = []

    def register(self, listener: Callable[[*T], None]) -> None:
        self.listeners.append(listener)

    def unregister(self, listener: Callable[[*T], None]) -> None:
        self.listeners.remove(listener)

    def notify(self, *args: *T) -> None:
        for listener in self.listeners:
            safe_invoke(listener, *args)


def run_in_background[**P](
    task: Callable[P, None],
    *args: P.args,
    **kwargs: P.kwargs,
) -> threading.Thread:
    thread = threading.Thread(target=task, args=args, kwargs=kwargs, daemon=True)
    thread.start()
    return thread


def recv_exact(sock: socket.socket, n: int) -> bytes | None:
    """Receive exactly n bytes from the socket."""
    data = bytearray()
    while len(data) < n:
        try:
            packet = sock.recv(n - len(data))
        except Exception:
            return None
        if not packet:
            return None
        data.extend(packet)
    return bytes(data)


def safe_invoke[**P, T](
    func: Callable[P, T], *args: P.args, **kwargs: P.kwargs
) -> T | None:
    try:
        return func(*args, **kwargs)
    except Exception:
        logging.exception("Error invoking function %s", func, stack_info=True)


class InfiniteLoop:
    def __init__(self, handler: Callable[[], None], sleep_time: float | None = None):
        self.handler = handler
        self.sleep_time = sleep_time
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stopped.set()
        if self._thread is not threading.current_thread():
            self._thread.join()

    def _loop(self):
        while not self._stopped.is_set():
            safe_invoke(self.handler)
            if self.sleep_time is not None:
                self._stopped.wait(self.sleep_time)
