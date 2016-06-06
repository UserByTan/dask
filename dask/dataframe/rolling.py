from __future__ import absolute_import, division, print_function

from functools import partial, wraps

from toolz import merge
import pandas as pd

from ..base import tokenize


def rolling_chunk(func, part1, part2, window, *args):
    if part1.shape[0] < window:
        raise NotImplementedError("Window larger than partition size")
    if window > 1:
        extra = window - 1
        combined = pd.concat([part1.iloc[-extra:], part2])
        applied = func(combined, window, *args)
        return applied.iloc[extra:]
    else:
        return func(part2, window, *args)


def wrap_rolling(func):
    """Create a chunked version of a pandas.rolling_* function"""
    @wraps(func)
    def rolling(arg, window, *args, **kwargs):
        if not isinstance(window, int):
            raise TypeError('Window must be an integer')
        if window < 0:
            raise ValueError('Window must be a positive integer')
        if 'freq' in kwargs or 'how' in kwargs:
            raise NotImplementedError('Resampling before rolling computations '
                                      'not supported')
        old_name = arg._name
        token = tokenize(func, arg, window, args, kwargs)
        new_name = 'rolling-' + token
        f = partial(func, **kwargs)
        dsk = {(new_name, 0): (f, (old_name, 0), window) + args}
        for i in range(1, arg.npartitions + 1):
            dsk[(new_name, i)] = (rolling_chunk, f, (old_name, i - 1),
                                  (old_name, i), window) + args
        return arg._constructor(merge(arg.dask, dsk), new_name,
                                arg, arg.divisions)
    return rolling


rolling_count = wrap_rolling(pd.rolling_count)
rolling_sum = wrap_rolling(pd.rolling_sum)
rolling_mean = wrap_rolling(pd.rolling_mean)
rolling_median = wrap_rolling(pd.rolling_median)
rolling_min = wrap_rolling(pd.rolling_min)
rolling_max = wrap_rolling(pd.rolling_max)
rolling_std = wrap_rolling(pd.rolling_std)
rolling_var = wrap_rolling(pd.rolling_var)
rolling_skew = wrap_rolling(pd.rolling_skew)
rolling_kurt = wrap_rolling(pd.rolling_kurt)
rolling_quantile = wrap_rolling(pd.rolling_quantile)
rolling_apply = wrap_rolling(pd.rolling_apply)
rolling_window = wrap_rolling(pd.rolling_window)

def call_pandas_rolling_method_single(this_partition, rolling_kwargs,
        method_name, method_args, method_kwargs):
    # used for the start of the df/series
    if this_partition.shape[0] < rolling_kwargs['window']:
        raise NotImplementedError("Window larger than partition size")

    method = getattr(this_partition.rolling(**rolling_kwargs), method_name)
    return method(*method_args, **method_kwargs)

def call_pandas_rolling_method_with_neighbor(prev_partition, this_partition,
        rolling_kwargs, method_name, method_args, method_kwargs):
    # used for everything except for the start

    window = rolling_kwargs['window']
    if prev_partition.shape[0] < window:
        raise NotImplementedError("Window larger than partition size")

    if window > 1:
        extra = window - 1
        combined = pd.concat([prev_partition.iloc[-extra:], this_partition])

        method = getattr(combined.rolling(window), method_name)
        applied = method(*method_args, **method_kwargs)
        return applied.iloc[extra:]
    else:
        method = getattr(this_partition.rolling(window), method_name)
        return method(*method_args, **method_kwargs)

class Rolling(object):
    # What you get when you do ddf.rolling(...) or similar
    """Provides rolling window calculcations.

    """

    def __init__(self, obj, kwargs):
        self.obj = obj # dataframe or series
        self.rolling_kwargs = kwargs

    def _call_method(self, method_name, *args, **kwargs):
        args = list(args) # make sure dask does not mistake this for a task

        old_name = self.obj._name
        new_name = 'rolling-' + tokenize(
            self.obj, self.rolling_kwargs, method_name, args, kwargs)

        dsk = {(new_name, 0): (
            call_pandas_rolling_method_single, (old_name, 0),
            self.rolling_kwargs, method_name, args, kwargs)}
        for i in range(1, self.obj.npartitions + 1):
            dsk[new_name, i] = (
                call_pandas_rolling_method_with_neighbor,
                (old_name, i-1), (old_name, i),
                self.rolling_kwargs, method_name, args, kwargs)

        return self.obj._constructor(
            merge(self.obj.dask, dsk),
            new_name,
            self.obj,
            self.obj.divisions)

    def count(self, *args, **kwargs):
        return self._call_method('count', *args, **kwargs)

    def sum(self, *args, **kwargs):
        return self._call_method('sum', *args, **kwargs)

    def mean(self, *args, **kwargs):
        return self._call_method('mean', *args, **kwargs)

    def median(self, *args, **kwargs):
        return self._call_method('median', *args, **kwargs)

    def min(self, *args, **kwargs):
        return self._call_method('min', *args, **kwargs)

    def max(self, *args, **kwargs):
        return self._call_method('max', *args, **kwargs)

    def std(self, *args, **kwargs):
        return self._call_method('std', *args, **kwargs)

    def var(self, *args, **kwargs):
        return self._call_method('var', *args, **kwargs)

    def skew(self, *args, **kwargs):
        return self._call_method('skew', *args, **kwargs)

    def kurt(self, *args, **kwargs):
        return self._call_method('kurt', *args, **kwargs)

    def quantile(self, *args, **kwargs):
        return self._call_method('quantile', *args, **kwargs)

    def apply(self, *args, **kwargs):
        return self._call_method('apply', *args, **kwargs)
