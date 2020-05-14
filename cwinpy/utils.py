"""
General utility functions.
"""

import ctypes
import os
import string
import subprocess
from functools import reduce
from math import gcd

import numpy as np
from lalpulsar.PulsarParametersWrapper import PulsarParametersPy
from numba import jit, njit
from numba.extending import get_cython_function_address

# create a numba-ified version of scipy's gammaln function (see, e.g.
# https://github.com/numba/numba/issues/3086#issuecomment-403469308)
addr = get_cython_function_address("scipy.special.cython_special", "gammaln")
functype = ctypes.CFUNCTYPE(ctypes.c_double, ctypes.c_double, ctypes.c_int)
gammaln_fn = functype(addr)


@njit
def gammaln(x):
    return gammaln_fn(x, 0)  # 0 is for the required int!


@jit(nopython=True)
def logfactorial(n):
    """
    The natural logarithm of the factorial of an integer using the fact that

    .. math::

        \\ln{(n!)} = \\ln{\\left(\\Gamma (n+1)\\right)}

    Parameters
    ----------
    n: int
        An integer for which the natural logarithm of its factorial is
        required.

    Returns
    -------
    float
    """

    return gammaln(n + 1)


def gcd_array(denominators):
    """
    Function to calculate the greatest common divisor of a list of values.
    """

    if not isinstance(denominators, (tuple, list, np.ndarray)):
        raise TypeError("Must have a list or array")

    denoms = np.asarray(denominators).flatten()  # 1d array
    denoms = denoms.astype(np.int)

    if len(denoms) < 2:
        raise ValueError("Must have more than two values")

    return reduce(lambda a, b: gcd(a, b), denoms)


def is_par_file(parfile):
    """
    Check if a TEMPO-style pulsar parameter file is valid.

    Parameters
    ----------
    parfile: str
        The path to a file.

    Returns
    -------
    ispar: bool
        Returns True is if it is a valid parameter file.
    """

    # check that the file is ASCII text (see, e.g.,
    # https://stackoverflow.com/a/1446571/1862861)

    if os.path.isfile(parfile):
        msg = subprocess.Popen(
            ["file", "--mime", parfile], stdout=subprocess.PIPE
        ).communicate()[0]
        if "text/plain" in msg.decode():
            psr = PulsarParametersPy(parfile)
            # file must contain a frequency, right ascension, declination and
            # pulsar name
            # file must contain right ascension and declination
            if (
                psr["F"] is None
                or (psr["RAJ"] is None and psr["RA"] is None)
                or (psr["DECJ"] is None and psr["DEC"] is None)
                or (
                    psr["PSRJ"] is None
                    and psr["PSRB"] is None
                    and psr["PSR"] is None
                    and psr["NAME"] is None
                )
            ):
                return False

            return True

    return False


def alphanum(pos, case="upper"):
    """
    For an integer number generate a corresponding alphabetical string
    following the mapping: 1 -> "A", 2 -> "B", ..., 27 -> "AA", 28 -> "AB", ...

    Parameters
    ----------
    pos: int
        A positive integer greater than 0.
    case: str
        Set whether to use upper or lower case. Default is "upper".

    Returns
    -------
    alpha: str
        The alphabetical equivalent
    """

    if case == "lower":
        alphas = list(string.ascii_lowercase)
    else:
        alphas = list(string.ascii_uppercase)

    if not isinstance(pos, int):
        raise TypeError("Value must be an integer")

    if pos < 1:
        raise ValueError("Value must be greater than zero")

    count = pos - 1
    result = ""
    while count >= 0:
        result = alphas[int(count) % len(alphas)] + result
        count /= len(alphas)
        count -= 1

    return result
