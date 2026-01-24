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
    thread = run_in_background_deferred(task, *args, **kwargs)
    thread.start()
    return thread


def run_in_background_deferred[**P](
    task: Callable[P, None],
    *args: P.args,
    **kwargs: P.kwargs,
) -> threading.Thread:
    thread = threading.Thread(target=task, args=args, kwargs=kwargs, daemon=True)
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
