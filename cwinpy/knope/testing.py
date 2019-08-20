"""
Run P-P plot testing for cwinpy_knope.
"""

import os
import sys
import glob
import shutil
from configparser import ConfigParser
from argparse import ArgumentParser
import bilby
import numpy as np
from .knope import knope_dag
from bilby_pipe.pp_test import read_in_result_list
from astropy.coordinates import SkyCoord
import astropy.units as u


def generate_pp_plots(**kwargs):  # pragma: no cover
    """
    Script entry point, or function, to generate P-P plots (see, e.g., [1]_): a
    frequentist-style evaluation to test that the true value of a parameter
    falls with a given Bayesian credible interval the "correct" amount of
    times, provided the trues values are drawn from the same prior as used when
    evaluating the posteriors.

    Parameters
    ----------
    path: str
        Glob-able directory path pattern to a set of JSON format bilby results
        files.
    output: str
        Output filename for the PP plot.
    parameters: list
        A list of the parameters to include in the PP plot.

    References
    ----------

        .. [1] `T. Sidery et al. <https://arxiv.org/abs/1312.6013>`_,
           *PRD*, **89**, 084060 (2014)
    """

    if "path" in kwargs:
        path = kwargs["path"]

        # default output file is a PNG image in the current directory
        outfile = kwargs.get("output", os.path.join(os.getcwd(), "ppplot.png"))

        # default parameters are obtained from the results file prior
        parameters = kwargs.get("parameters", None)
    elif "cwinpy_knope_generate_pp_plots" == os.path.split(sys.argv[0])[-1]:
        parser = ArgumentParser(
            description=(
                "A script to create a PP plot of CW signal parameters"
            )
        )
        parser.add_argument(
            "--path", "-p",
            required=True,
            help=(
                "A glob-able path pattern to a set of bilby JSON results "
                "files for the set of simulations."
            ),
            dest="path",
        )
        parser.add_argument(
            "--output", "-o",
            help=(
                "The output plot file name [default: %(default)s]."
            ),
            default=os.path.join(os.getcwd(), "ppplot.png"),
            dest="outfile",
        )
        parser.add_argument(
            "--parameter",
            action="append",
            help=(
                "The parameters with which to create the PP plots."
            ),
        )

        args = parser.parse_args()
        path = args.path
        outfile = args.outfile
        parameters = args.parameters
    else:
        raise KeyError("A 'path' keyword must be supplied.")

    # get results files
    try:
        resfiles = [
            rfile
            for rfile in glob.glob(path)
            if os.path.splitext(rfile)[1] == ".json"
        ]
    except Exception as e:
        raise IOError("Problem finding results files: {}".format(e))

    if len(resfiles) == 0:
        raise IOError(
            "Problem finding results files. Probably an invalid path!"
        )

    # read in results
    results = read_in_result_list(resfiles)

    if parameters is None:
        # get parameters to use from results file prior
        parameters = [
            name
            for name, p in results[0].priors.items()
            if isinstance(p, str) or p.is_fixed is False
        ]

    # make plots
    try:
        _ = bilby.core.result.make_pp_plot(
            results,
            filename=outfile,
            keys=parameters,
        )
    except Exception as e:
        raise RuntimeError(
            "Problem creating PP plots: {}".format(e)
        )


class KnopePPPlotsDAG(object):
    """
    This class will generate a HTCondor Dagman job to create a number of
    simulated gravitational-wave signals from pulsars in Gaussian noise. These
    will be analysed using the ``cwinpy_knope`` script to sample the posterior
    probability distributions of the required parameter space. For each
    simulation and parameter combination the credible interval (bounded at the
    low end by the lowest sample in the posterior) in which the known true
    signal value lies will be found. The cumulative probability of finding the
    true value within a given credible interval is then plotted.

    Parameters
    ----------
    prior: dict
        A bilby-style prior dictionary giving the prior distributions from
        which to draw the injected signal values, and to use for signal
        recovery.
    ninj: int
        The number of simulated signals to create. Defaults to 100.
    maxamp: float
        A maxmimum on the amplitude parameter(s) to use when drawing the
        injection parameters. If none is given then this will be taken
        from the prior if using an amplitude parameter.
    basedir: str
        The base directory into which the simulations and outputs will be
        placed. If None then the current working directory will be used.
    detector: str, list
        A string, or list of strings, of detector prefixes for the simulated
        data. This defaults to a single detector - the LIGO Hanford
        Observatory - from which the simulated noise will be drawn from the
        advanced detector design sensitivity curve (e.g., [1]_).
    submit: bool
        Set whether to submit the Condor DAG or not.
    accountuser: str
        Value to give to the 'account_user' parameter in the Condor submit
        file. Default is to set no value.
    accountgroup: str
        Value to give to the 'account_user_group' parameter in the Condor
        submit file. Default is to set no value.
    getenv: bool
        Set the value for the 'getenv' parameter in the Condor submit file.
        Default is False.
    sampler: str
        The sampler to use. Defaults to dynesty.
    sampler_kwargs: dict
        A dictionary of keyword arguments for the sampler. Defaults to None.
    freqrange: list, tuple
        A pair of values giving the lower and upper rotation frequency ranges
        (in Hz) for the simulated signals. Defaults to (10, 750) Hz.

    References
    ----------

        .. [1] L. Barsotti, S. Gras, M. Evans, P. Fritschel,
               `LIGO T1800044-v5 <https://dcc.ligo.org/LIGO-T1800044/public>`_ (2018)

    """

    def __init__(self, prior, ninj=100, maxamp=None, basedir=None,
                 detector="AH1", submit=False, accountuser=None,
                 accountgroup=None, getenv=False, sampler="dynesty",
                 sampler_kwargs=None, freqrange=(10.0, 750.0)):

        if isinstance(prior, dict):
            self.prior = bilby.core.prior.PriorDict(dictionary=prior)
        else:
            raise TypeError("Prior must be a dictionary-type object")

        if ninj < 1:
            raise ValueError("A positive number of injection must be given")
        self.ninj = ninj

        # set maximum amplitude if given
        self.maxamp = None
        if isinstance(maxamp, float):
            if maxamp > 0.:
                self.maxamp = int(maxamp)
            else:
                raise ValueError("Maximum amplitude must be positive")

        if basedir is not None:
            self.basedir = basedir
            self.makedirs(basedir)
        else:
            self.basedir = os.getcwd()

        # build output directory structure
        self.detector = detector
        if isinstance(self.detector, str):
            self.detector = [self.detector]
        if not isinstance(self.detector, list):
            raise TypeError("Detector must be a string or list of strings")

        # posterior sample results directory
        self.resultsdir = os.path.join(self.basedir, "results")
        self.makedirs(self.resultsdir)

        # create pulsar parameter files
        self.create_pulsars(freqrange=freqrange)

        # create dag configuration file
        self.accountuser = accountuser
        self.accountgroup = accountgroup
        self.getenv = getenv
        self.submit = submit
        self.sampler = sampler
        self.sampler_kwargs = sampler_kwargs
        self.create_config()

        # create the DAG for cwinpy_knope jobs
        self.dag = knope_dag(config=self.config)
        
        # add PP plot creation DAG
        self.ppplots()

    def makedirs(self, dir):
        """
        Make a directory tree recursively.
        """

        try:
            os.makedirs(dir, exist_ok=True)
        except Exception as e:
            raise IOError("Could not create directory: {}\n{}".format(dir, e))

    def create_pulsars(self, freqrange):
        """
        Create the pulsar parameter files based on the samples from the priors.

        Parameters
        ----------
        freqrange: list, tuple
            A pair of values giving the lower and upper rotation frequency ranges
            (in Hz) for the simulated signals.
        """

        # pulsar parameter file directory
        self.pulsardir = os.path.join(self.basedir, "pulsars")
        self.makedirs(self.pulsardir)

        # "amplitude" parameters
        amppars = ["h0", "c21", "c22", "q22"]

        if not isinstance(freqrange, (list, tuple, np.ndarray)):
            raise TypeError("Frequency range must be a list or tuple")
        else:
            if len(freqrange) != 2:
                raise ValueError("Frequency range must contain an upper and lower value")

        self.pulsars = {}
        for i in range(self.ninj):
            pulsar = {}

            for param in self.prior:
                pulsar[param.upper()] = self.prior[param].sample()

            # draw sky position uniformly from the sky if no prior is given
            if "ra" not in self.prior:
                raval = np.random.uniform(0.0, 2.0 * np.pi)
            else:
                raval = pulsar.pop("ra")

            if "dec" not in self.prior:
                decval = -(np.pi/2.) + np.arccos(np.random.uniform(-1.0, 1.0))
            else:
                decval = pulsar.pop("dec")

            skypos = SkyCoord(raval * u.rad, decval * u.rad)
            pulsar["RAJ"] = skypos.ra.to_string(u.hour, fields=3, sep=":", pad=True)
            pulsar["DECJ"] = skypos.dec.to_string(u.deg, fields=3, sep=":", pad=True)

            # set maximum amplitude if given
            if self.maxamp is not None:
                for amp in amppars:
                    if amp in self.prior:
                        pulsar[amp.upper()] = bilby.core.prior.Uniform(
                            name=amp,
                            minimum=0.,
                            maximum=self.maxamp).sample()

            # set (rotation) frequency upper and lower bounds
            if "f0" not in self.prior:
                pulsar["F0"] = np.random.uniform(freqrange[0], freqrange[1])

            # set pulsar name from sky position
            rastr = skypos.ra.to_string(u.hour, fields=2, sep="", pad=True)
            decstr = skypos.dec.to_string(
                u.deg, fields=2, sep="", pad=True, alwayssign=True
            )
            pname = 'J{}{}'.format(rastr, decstr)
            pnameorig = str(pname)  # copy of original name
            counter = 0
            alphas = ["A", "B", "C", "D", "E", "F", "G"]
            while pname in self.pulsars:
                if counter == len(alphas):
                    raise RuntimeError(
                        "Too many pulsars in the same sky position!"
                    )
                pname = pnameorig + alphas[counter]
                counter += 1

            pulsar["PSRJ"] = pname

            # output file name
            pfile = os.path.join(self.pulsardir, "{}.par".format(pname))

            with open(pfile, "w") as fp:
                for param in pulsar:
                    fp.write("{}\t{}\n".format(param, pulsar[param]))

            self.pulsars[pname] = {}
            self.pulsars[pname]['file'] = pfile
            self.pulsars[pname]['parameters'] = pulsar

    def create_config(self):
        """
        Create the configuration parser for the DAG.
        """

        self.config = ConfigParser()

        self.config["run"] = {"basedir": self.basedir}

        self.config["dag"] = {"submitdag": str(self.submit)}

        self.config["job"] = {}
        self.config["job"]["getenv"] = str(self.getenv)

        if self.accountgroup is not None:
            self.config["accounting_group"] = self.accountgroup
        if self.accountuser is not None:
            self.config["accounting_group_user"] = self.accountuser

        self.config["knope"] = {}
        self.config["knope"]["pulsars"] = self.pulsardir
        self.config["knope"]["injections"] = self.pulsardir

        # set fake data
        if 'h0' in self.prior or 'c22' in self.prior or 'q22' in self.prior:
            self.config["knope"]["fake-asd-2f"] = str(self.detector)
        if 'c21' in self.prior and 'c22' in self.prior:
            self.config["knope"]["fake-asd-1f"] = str(self.detector)
        if 'c21' in self.prior and 'c22 not in self.prior':
            self.config["knope"]["fake-asd-1f"] = str(self.detector)

        # set the prior file
        label = "pp"
        self.priorfile = os.path.join(self.basedir, "{}.prior".format(label))
        self.prior.to_file(outdir=self.basedir, label=label)

        self.config["knope"]["priors"] = self.priorfile
        self.config["knope"]["sampler"] = self.sampler
        if isinstance(self.sampler_kwargs, dict):
            self.config["knope"]["sampler_kwargs"] = str(self.sampler_kwargs)
            
    def ppplots(self):
        """
        Set up job to create PP plots.
        """

        # get executable
        jobexec = shutil.which("cwinpy_knope_generate_pp_plots")
        
        extra_lines = []
        if self.dag.accgroup is not None:
            extra_lines.append("accounting_group = {}".format(self.dag.accgroup))
        if self.dag.accuser is not None:
            extra_lines.append("accounting_group_user = {}".format(self.dag.accuser))
        
        # create cwinpy_knope Job
        job = Job(
            "cwinpy_knope_pp_plots",
            jobexec,
            error=self.dag.error,
            log=self.dag.log,
            output=self.dag.output,
            submit=self.dag.jobsubmit,
            universe=self.dag.universe,
            request_memory=self.dag.reqmem,
            getenv=self.dag.getenv,
            queue=1,
            requirements=self.dag.requirements,
            retry=self.dag.retry,
            extra_lines=extra_lines,
            dag=self.dag,
        )

        job.add_parents(self.dag.job)
        self.dag.build()