# Various utility functions


def clamp(v, minv, maxv):
    """
    Clamps a value between the given minimum and maximum.
    """
    return max(minv, min(maxv, v))


def get_user_agent() -> str:
    """
    Returns the user agent used by the script.
    """
    return "XIVMarketAnalyzer/1.0.1 https://github.com/lyao6104/XIVMarketAnalyzer"


class MinMax(object):
    """
    Class for easily calculating the minimum and maximum value in a collection,
    as well as some additional utilities.
    """

    def __init__(self) -> None:
        self.minimum = float("inf")
        self.maximum = float("-inf")

    def add_value(self, v) -> None:
        if v > self.maximum:
            self.maximum = v
        if v < self.minimum:
            self.minimum = v

    def get_t(self, v) -> float:
        """
        Calculates the linear interpolation point of the given value.
        Note that this does *not* update the `MinMax` bounds, so results
        aren't clamped between 0 and 1.
        """
        if abs(v - self.maximum) < 1e-6:
            return 1
        elif abs(v - self.minimum) < 1e-6:
            return 0
        else:
            return (v - self.minimum) / (self.maximum - self.minimum)
