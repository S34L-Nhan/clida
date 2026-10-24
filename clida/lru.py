"""A small cache for the changes view: it forgets the least recently used entries."""

import threading
from collections import OrderedDict


class Lru:
    """A small cache that forgets the least recently used entries: every chat opened adds some.

    weight, if given, measures an entry (a diff: its rows), and the entries together stay under budget.
    """

    def __init__(self, size: int, budget: int = 0, weight=None):
        self._size, self._items, self._lock = size, OrderedDict(), threading.Lock()
        self._budget, self._weight, self._total = budget, weight, 0

    def get(self, slot, key):
        with self._lock:
            hit = self._items.get(slot)
            if hit is None or hit[0] != key:
                return None
            self._items.move_to_end(slot)
            return hit[1]

    def put(self, slot, key, value):
        weigh = self._weight or (lambda value: 0)
        with self._lock:
            old = self._items.pop(slot, None)
            if old is not None:
                self._total -= weigh(old[1])
            self._items[slot] = (key, value)
            self._total += weigh(value)
            while len(self._items) > 1 and (len(self._items) > self._size or (self._budget and self._total > self._budget)):
                _, (_, dropped) = self._items.popitem(last=False)
                self._total -= weigh(dropped)
