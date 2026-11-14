"""Scene timeline normalisation.

LLMs are unreliable at arithmetic: a "30-second" script often sums to 27 or 34 seconds.
Rather than trusting the model, we recompute the timeline deterministically: scale the
scene durations to hit the requested total exactly, then derive start/end times.
"""

from typing import Protocol


class TimedScene(Protocol):
    scene_number: int
    duration_seconds: float
    start_time: float
    end_time: float


def normalize_timeline(scenes: list[TimedScene], target_seconds: float) -> bool:
    """Make scene timings contiguous and sum to `target_seconds`. Returns True if the
    model's durations had to be changed."""
    durations = [max(float(s.duration_seconds), 0.1) for s in scenes]
    total = sum(durations)
    adjusted = abs(total - target_seconds) > 0.05

    if adjusted:
        scaled = [round(d * target_seconds / total, 1) for d in durations]
        scaled[-1] = round(target_seconds - sum(scaled[:-1]), 1)
        if scaled[-1] <= 0:  # rounding pushed the last scene negative: split evenly
            even = round(target_seconds / len(scenes), 1)
            scaled = [even] * (len(scenes) - 1)
            scaled.append(round(target_seconds - sum(scaled), 1))
        durations = scaled

    clock = 0.0
    for number, (scene, duration) in enumerate(zip(scenes, durations, strict=True), start=1):
        scene.scene_number = number
        scene.duration_seconds = duration
        scene.start_time = round(clock, 1)
        clock += duration
        scene.end_time = round(clock, 1)
    return adjusted
