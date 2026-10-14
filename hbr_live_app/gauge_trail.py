"""Presentation-only damage trail; never changes measured resources."""
from collections import deque


class GaugeTrail:
    threshold = 0.12
    window = 0.7
    hold = 0.35
    duration = 0.7

    def __init__(self):
        self.value = self.reference = self.start = 0
        self.until = 0
        self.samples = deque()

    def reset(self, value, reference, now):
        self.value = self.start = value
        self.reference = reference
        self.until = now - self.duration
        self.samples = deque([(now, value)])

    def display(self, now):
        elapsed = max(0, now - self.until)
        ratio = min(1, elapsed / self.duration)
        return self.value + (self.start-self.value) * (1-ratio)**2

    def active(self, now):
        return self.start > self.value and now < self.until+self.duration

    def update(self, value, reference, now):
        if not self.samples or reference != self.reference or value > self.value:
            self.reset(value, reference, now)
            return
        while self.samples and now-self.samples[0][0] > self.window:
            self.samples.popleft()
        if value == self.value:
            # Keep a recent baseline without extending an existing animation.
            self.samples.append((now, value))
            return
        peak = max([self.value] + [v for _, v in self.samples])
        previous_display = self.display(now)
        was_active = self.active(now)
        self.value = value
        if was_active or peak-value >= max(1, reference)*self.threshold:
            self.start = max(previous_display, peak if not was_active else value)
            self.until = now+self.hold
        else:
            self.start = value
        self.samples.append((now, value))
