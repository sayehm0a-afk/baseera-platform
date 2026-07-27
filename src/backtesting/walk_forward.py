"""Walk-forward window splitting -- Phase 4's "do not calibrate and
evaluate on the same historical period," made mechanical rather than
a discipline a caller has to remember.

Pure date arithmetic, no database, no randomness (nothing here needs a
random seed; CalibrationEngine's own parameter search is where
reproducible seeding actually matters -- see its module docstring).

The anti-leakage guarantee this module provides: `generate_walk_forward_windows()`
always reserves the *last* `test_days` days of the full range as an
untouched test period, and every (train, validation) window it
produces is strictly contained in the days *before* that reserved
period -- there is no code path that can accidentally let a
calibration decision see the test period's data, because this
function never returns a window that overlaps it.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional


@dataclass(frozen=True)
class WalkForwardWindow:
    train_start: date
    train_end: date
    validation_start: date
    validation_end: date


@dataclass(frozen=True)
class WalkForwardSplit:
    windows: List[WalkForwardWindow]
    test_start: date
    test_end: date

    @property
    def final_validation_end(self) -> Optional[date]:
        """The last validation window's end date -- must always be
        strictly before `test_start`; asserted by every test in
        test_walk_forward.py, not just assumed."""
        return self.windows[-1].validation_end if self.windows else None


def generate_walk_forward_windows(
    start_date: date,
    end_date: date,
    train_days: int,
    validation_days: int,
    test_days: int,
    mode: str = "rolling",
    step_days: Optional[int] = None,
) -> WalkForwardSplit:
    """Splits [start_date, end_date] into a sequence of (train,
    validation) windows plus one reserved, untouched test period at
    the end.

    `mode="rolling"`: each window's training period is a fixed-size
    `train_days` slice that slides forward by `step_days` (default:
    `validation_days`, i.e. non-overlapping validation windows) each
    iteration -- older training data is dropped as newer data enters.

    `mode="expanding"`: the training period's start date never moves;
    each iteration's training period absorbs the previous iteration's
    validation period, so training data only grows.

    Raises `ValueError` if the range is too short to fit even one
    window plus the reserved test period, or if any window/step size
    isn't positive -- there is no such thing as a silently-empty walk-
    forward split.
    """
    if mode not in ("rolling", "expanding"):
        raise ValueError("mode must be 'rolling' or 'expanding'")
    if train_days <= 0 or validation_days <= 0 or test_days <= 0:
        raise ValueError("train_days, validation_days, and test_days must all be positive")

    step = step_days if step_days is not None else validation_days
    if step <= 0:
        raise ValueError("step_days must be positive")

    total_days = (end_date - start_date).days + 1
    if total_days < train_days + validation_days + test_days:
        raise ValueError(
            f"date range too short ({total_days} days, {start_date}..{end_date}) for "
            f"train={train_days} + validation={validation_days} + test={test_days} days"
        )

    test_start = end_date - timedelta(days=test_days - 1)
    pre_test_end = test_start - timedelta(days=1)

    windows: List[WalkForwardWindow] = []
    train_start = start_date
    train_end = start_date + timedelta(days=train_days - 1)

    while True:
        validation_start = train_end + timedelta(days=1)
        validation_end = validation_start + timedelta(days=validation_days - 1)
        if validation_end > pre_test_end:
            break

        windows.append(
            WalkForwardWindow(
                train_start=train_start, train_end=train_end,
                validation_start=validation_start, validation_end=validation_end,
            )
        )

        if mode == "rolling":
            train_start = train_start + timedelta(days=step)
            train_end = train_start + timedelta(days=train_days - 1)
        else:  # expanding
            train_end = validation_end  # train_start stays fixed; the window only grows

    return WalkForwardSplit(windows=windows, test_start=test_start, test_end=end_date)
