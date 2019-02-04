"""
Functions to deal with heterodyned data.
"""

from __future__ import division, print_function

import os
import numpy as np
import warnings

# import lal and lalpulsar
import lal
import lalpulsar


class MultiDetectorHeterdynedData(object):

    def __init__(self, window=30, inject=False, inpar=None, **kwargs):
        """
        A class to contain time series' of heterodyned data, using the
        :class:`~cwinpy.HeterodynedData` class, for multiply detectors.
        """

        raise NotImplementedError


class HeterodynedData(object):

    def __init__(self, data=None, times=None, par=None, detector=None,
                 window=30, inject=False, injpar=None, freqfactor=2.0):
        """
        A class to contain a time series of heterodyned data.
        
        If a file containing heterodyned data is passed to the object it should
        have the one of the follow forms:
        
        Three columns with:
        
        time (GPS), real component, imaginary component

        Four columns with:

        time (GPS), real component, imaginary component, standard deviation

        It can have comments lines started with a '#' or '%'.

        Parameters
        ----------
        data: (str, array_like)
            A file (plain ascii text, or gzipped ascii text) containing a time
            series of heterodyned data, or an array containing the complex
            heterodyned data.
        times: array_like
            If the data was passed using the `data` argument, then the
            associated time stamps should be passed using this argument.
        par: (str, lalpulsar.PulsarParametersPy)
            A parameter file, or `lalpulsar.PulsarParametersPy` object
            containing the parameters with which the data was heterodyned.
        detector: (str, lal.Detector)
            A string, or lal.Detector object, identifying the detector from
            which the data was generated.
        window: int, 30
            The length of a window used for calculating a running median over
            the data.
        inject: bool, False
            Set to `True` to add a simulated signal to the data based on the
            parameters supplied in `injpar`, or `par` if `injpar` is not given.
        injpar: (str, lalpulsar.PulsarParametersPy)
            A parameter file containing values for the injected signal. A `par`
            file must also have been provided, and the injected signal will
            assume that the data has already been heterdyned using the
            parameters from `par`, which could be different.
        injtimes: list, None
            A list containing pairs of times between which to add the simulated
            signal. By default the signal will be added into the whole data
            set.
        freqfactor: float, 2.0
            The frequency scale factor for the data signal, e.g., a value
            of two for emission from the l=m=2 mode at twice the rotation
            frequency of the source.
        """

        self.window = window  # set the window size

        # set the data
        self.data = (data, times)

        # set the parameter file
        self.par = par

        # set the detector from which the data came
        self.detector = detector

        # set the frequency scale factor
        self.freq_factor = freqfactor

        # set and add a simulated signal
        self.injection = bool(inject)
        if self.injection:
            # inject the signal
            if injpar is None:
                self.inject_signal(injtimes=injtimes)
            else:
                self.inject_signal(injpar=injpar, injtimes=injtimes)

    @property
    def window(self):
        return self.__window

    @window.setter
    def window(self, window):
        if isinstance(window, int):
            if window < 2:
                raise ValueError("Window length must be greater than 2")
            else:
                self.__window = window
        else:
            raise TypeError("Window must be an integer")

    @property
    def data(self):
        return self.__data
    
    @data.setter
    def data(self, data):
        """
        Set the data.
        """
        
        if isinstance(data, tuple):
            try:
                dataval, times = data
            except ValueError:
                raise ValueError("Tuple of data must have two items")
        else:
            dataval = data
            times = None
        
        if isinstance(dataval, str):
            # read in data from a file
            try:
                dataarray = np.loadtxt(dataval, comments=['#', '%'])
            except Exception as e:
                raise IOError("Problem reading in data: {}".format(e))
            
            if len(dataarray.shape) != 2:
                raise ValueError("Data array is the wrong shape for "
                                 "heterodyned data.")

            self.times = dataarray[:,0]  # set time stamps
        else:
            if times is None:
                raise ValueError("Time stamps must also be supplied")
            else:
                # use supplied time stamps
                self.times = times

            if data is None:
                # set data to zeros
                dataarray = np.zeros((len(times), 1))
            else:
                dataarray = np.atleast_2d(np.asarray(data))
                if dataarray.shape[0] == 1:
                    dataarray = dataarray.T

        self.__stds = None  # initialise stds to None
        if dataarray.shape[1] == 1 and dataarray.dtype == np.complex:
            self.__data = dataarray.flatten()
        elif dataarray.shape[1] == 2:
            # real and imaginary components are separate
            self.__data = dataarray[:,0] + 1j*dataarray[:,1]
        elif dataarray.shape[1] == 3 or dataarray.shape[1] == 4:
            self.__data = dataarray[:,1] + 1j*dataarray[:,2]
            if dataarray.shape[1] == 4:
                # set pre-calculated data standard deviations
                self.__stds = dataarray[:,3]
        else:
            raise ValueError("Data array is the wrong shape")
        
        if len(self.times) != len(self.data):
            raise ValueError("Data and time stamps are not the same length")

        # set the (minimum) time step and sampling frequency
        if len(self.times) > 1:
            self.__dt = np.min(np.diff(self.times))
            self.__fs = 1./self.dt
        else:
            warnings.warn("Your data is only one data point long!")
            self.__dt = None
            self.__fs = None

        # initialise the running median
        _ = self.compute_running_median(N=self.window)
        _ = self.compute_variance(N=self.window)

    @property
    def times(self):
        return self.__times

    @times.setter
    def times(self, times):
        """
        Set the data time stamps.
        """

        self.__times = np.asarray(times, dtype='float64')

    @property
    def par(self):
        return self.__par

    @par.setter
    def par(self, par):
        self.__par = self._parse_par(par)

    @property
    def injpar(self):
        return self.__injpar

    @injpar.setter
    def injpar(self, par):
        self.__injpar = self._parse_par(par)

    def _parse_par(self, par):
        """
        Parse a pulsar parameter file or lalpulsar.PulsarParametersPy object.

        Parameters
        ----------
        par: (str, lalpulsar.PulsarParametersPy)
            A file or object containing a set of pulsar parameters.

        Returns
        -------
        A lalpulsar.PulsarParametersPy object
        """

        if par is not None:
            from lalpulsar.PulsarParametersWrapper import PulsarParametersPy

            if isinstance(par, PulsarParametersPy):
                return par
            elif isinstance(par, str):
                try:
                    newpar = PulsarParametersPy(par)
                except Exception as e:
                    raise IOError("Could not read in pulsar parameter "
                                  "file: {}".format(e))
        else:
            newpar = None

        return newpar

    @property
    def detector(self):
        return self.__detector
    
    @property
    def laldetector(self):
        return self.__laldetector

    @detector.setter
    def detector(self, detector):
        if detector is None:
            self.__detector = None
            self.__laldetector = None
        else:
            if isinstance(detector, lal.Detector):
                self.__detector = detector.frDetector.prefix
                self.__laldetector = detector
            elif isinstance(detector, string_types):
                self.__detector = detector

                try:
                    self.__laldetector = lalpulsar.GetSiteInfo(detector)
                except RuntimeError:
                    raise ValueError("Could not set LAL detector!")

    @property
    def running_median(self):
        return self.__running_median

    def compute_running_median(self, N=30):
        """
        Calculate a running median from the data. The running median will be
        calculated using a window of samples of a given number. This does not
        account for any gaps in the data, so could contain discontinuities.

        Parameters
        ----------
        N: int, 30
            the window length of the running median. Defaults to 30 points.

        Returns
        -------
        runningmedian: array_like
            an array containing the data with with running median subtracted. 
        """

        if N < 2:
            raise ValueError("The running median window must be greater "
                             "than 1")

        # create copy of data with buffers prepended and appended
        datacopy = np.hstack((self.data[:N//2], self.data, self.data[-N//2:]))

        self.__running_median = np.zeros(len(self))
        for i in range(len(self)):
            self.__running_median[i] = np.median(datacopy[i:i+N])

        return self.running_median

    def subtract_running_median(self):
        """
        Subtract the running median from the data.

        Returns
        -------
        newdata: array_like
            an array containing the data with with running median subtracted. 
        """

        return self.data - self.running_median

    @property
    def vars(self):
        return self.__vars

    @property
    def stds(self):
        return np.sqrt(self.__vars)

    def compute_variance(self, change_points=None, N=30):
        """
        Compute the (sample) variance of the data within a set of change
        points. The variance will be calculated after subtraction of a running
        median. As the data is complex, we calculate the variance of a vector
        in which the real and imaginary components are concatenated. This is
        equivalent to a two-sided power spectral density.

        Parameters
        ----------
        change_points: array_like, None
            An array of indices of statistical change points within the data
        N: int, 30
            The window size (in terms of data point number) of the running
            median.

        Returns
        -------
        vars: array_like
            An array of variances for each data point.
        """

        if self.__stds is not None:
            self.__vars = self.__stds**2
            return self.vars
        else:
            self.__vars = np.zeros(len(self))

        # subtract running median from the data
        datasub = self.subtract_running_median(N=N)

        if change_points is None:
            # return the (sample) variance (hence 'ddof=1')
            self.__vars = np.full(len(self),
                                  np.hstack(datasub.real,
                                            datasub.imag).var(ddof=1))

        else:
            cps = np.concatenate(([0], np.asarray(change_points, dtype=np.int),
                                  [len(datasub)]))

            if self.stds is None:
                self.stds = np.zeros(len(self))

            for i in range(len(cps)-1):
                if cps[i+1] < 1 or cps[i+1] > len(datasub)-2:
                    raise ValueError("Change point index is out of bounds")

                if cps[i+1] <= cps[i]:
                    raise ValueError("Change point order is wrong")

                datachunk = datasub[cps[i]:cps[i+1]]

                # get (sample) variance of chunk
                self.__vars[cps[i]:cps[i+1]] = np.hstack(datachunk.real,
                                                         datachunk.imag).var(ddof=1)

        return self.vars

    def inject_signal(self, injpar=None, injtimes=None, freqfactor=2.):
        """
        Inject a simulated signal into the data.

        Parameters
        ----------
        injpar: (str, lalpulsar.PulsarParametersPy)
            A parameter file or object containing the parameters for the
            simulated signal.
        injtimes: list
            A list of pairs of time values between which to inject the signal.
        freqfactor: float, 2.0
            A the frequency scaling for the signal model, i.e., "2.0" for
            emission from the l=m=2 mass quadrupole mode.
        """

        from lalpulsar.simulateHeterodynedCW import HeterodynedCWSimulator

        if self.par is None:
            raise ValueError("To perform an injection a parameter file "
                             "must be supplied")

        # set the times between which the injection will be added
        self.injtimes = injtimes

        # initialise the injection
        het = HeterodynedCWSimulator(self.par, self.detector, times=self.times)

        if freqfactor != self.freq_factor:
            self.freq_factor = freqfactor

        # initialise the injection to zero
        inj_data = np.ones_like(self.data)

        # get the injection
        if injpar is None:
            # use self.par for the injection parameters
            self.injpar = self.par
            inj = het.model(usephase=True, freqfactor=self.freq_factor)
        else:
            self.injpar = injpar
            inj = het.model(self.injpar, updateSSB=True, updateBSB=True,
                            usephase=True, freqfactor=self.freq_factor)
        
        for timerange in self.injtimes:
            timeidxs = (self.times >= timerange[0]) & (self.times <= timerange[1])
            inj_data[timeidxs] = inj[timeidxs]

        # add injection to data
        self.__data = self.data + inj_data

        # save injection data
        self.__inj_data = inj_data

    @property
    def injtimes(self):
        return self.__injtimes

    @injtimes.setter
    def injtimes(self, injtimes):
        if injtimes is None:
            # include all time
            timelist = np.array([[self.times[0], self.times[-1]]])

        try:
            timelist = np.atleast_2d(injtimes)
        except:
            raise ValueError("Could not parse list of injection times")

        for timerange in timelist:
            if timerange[0] >= timerange[1]:
                raise ValueError("Injection time ranges are incorrect")

        self.__injtimes = timelist

    @property
    def injection_data(self):
        return self.__inj_data

    @property
    def freq_factor(self):
        return self.__freq_factor

    @freq_factor.setter
    def freq_factor(self, freqfactor):
        if not isinstance(freqfactor, (float, int)):
            raise TypeError("Frequency scale factor must be a number")

        if freqfactor <= 0.:
            raise ValueError("Frequency scale factor must be a positive "
                             "number")

        self.__freq_factor = float(freqfactor)

    def __len__(self):
        return len(self.data)
