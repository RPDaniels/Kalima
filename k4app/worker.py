"""Ejecuta las operaciones MIDI en un hilo aparte para no congelar la ventana.

Las tareas se atienden de una en una (el K4 no admite conversaciones
cruzadas) y los resultados vuelven al hilo de Tk mediante root.after().
"""
from __future__ import annotations

import queue
import threading


class Worker:
    def __init__(self, root, poll_ms: int = 40):
        self.root = root
        self.poll_ms = poll_ms
        self._tasks: queue.Queue = queue.Queue()
        self._events: queue.Queue = queue.Queue()
        self.pending = 0
        threading.Thread(target=self._loop, daemon=True, name="k4-midi").start()
        root.after(poll_ms, self._poll)

    @property
    def busy(self) -> bool:
        return self.pending > 0

    def submit(self, fn, on_done=None, on_error=None, on_progress=None):
        """fn(progress) se ejecuta en el hilo MIDI; progress(n, total) informa del avance.
        on_done(resultado), on_error(excepción) y on_progress(n, total) se llaman en el hilo de Tk."""
        self.pending += 1
        self._tasks.put((fn, on_done, on_error, on_progress))

    def _loop(self):
        while True:
            fn, on_done, on_error, on_progress = self._tasks.get()

            def progress(n, total, cb=on_progress):
                if cb:
                    self._events.put((cb, (n, total), False))
            try:
                result = fn(progress)
                self._events.put((on_done, (result,), True))
            except Exception as e:  # noqa: BLE001 - se informa en la interfaz
                self._events.put((on_error, (e,), True))

    def _poll(self):
        try:
            while True:
                cb, args, finished = self._events.get_nowait()
                if finished:
                    self.pending -= 1
                if cb:
                    cb(*args)
        except queue.Empty:
            pass
        self.root.after(self.poll_ms, self._poll)
