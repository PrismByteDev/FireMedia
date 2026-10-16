"""Queue traversal with finite shuffle passes and explicit repeat behavior."""
import random

class PlaybackOrder:
    def __init__(self):
        self.order = []
        self.signature = None

    def reset(self):
        self.signature = None

    def next(self, current, count, shuffle='Off', loop='Off', automatic=False):
        if not count:
            return None
        if automatic and loop == 'Track' and current >= 0:
            return current
        signature = (count, shuffle)
        if signature != self.signature:
            self.order = list(range(count))
            if shuffle != 'Off':
                rest = [i for i in self.order if i != current]
                random.shuffle(rest)
                self.order = ([current] if current >= 0 else []) + rest
            self.signature = signature
        position = self.order.index(current) if current in self.order else -1
        if position + 1 < count:
            return self.order[position + 1]
        if automatic and loop != 'Playlist':
            return None
        if shuffle == 'Every loop':
            rest = [i for i in range(count) if i != current]
            random.shuffle(rest)
            self.order = rest + ([current] if current >= 0 else [])
        return self.order[0]
