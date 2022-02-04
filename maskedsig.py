from cwinpy.signal import HeterodynedCWSimulator
from cwinpy import PulsarParameters
from astropy.time import Time
from astropy.coordinates import SkyCoord
import numpy as np
from cwinpy import HeterodynedData

par = PulsarParameters("Custom1.par")

# set the GPS times of the data
times = np.arange(1000000000.0, 1000086400.0, 3600, dtype=np.float128)

# set the detector
det = "H1"  # the LIGO Hanford Observatory

# create the HeterodynedCWSimulator object
het = HeterodynedCWSimulator(par, det, times=times)

# get the model complex strain time series
model = het.model()

hd = HeterodynedData(data = model, times = times, det = det, parfile = par)

fig = hd.plot(which = "both")
fig.show()