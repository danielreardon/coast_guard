#!/usr/bin/env python

"""
Given a PSRCHIVE archive create diagnostic plots.

Patrick Lazarus, Dec. 12, 2011
"""

import sys

import numpy as np
import scipy.signal
import scipy.stats
import scipy.optimize as opt
import matplotlib.cm
import matplotlib.pyplot as plt

import psrchive


def scale(data, weights=slice(None)):
    medfilt = scipy.signal.medfilt(data[weights], kernel_size=5)
    data[weights] -= medfilt
    return data 


def scale_subints(data, weights=slice(None)):
    medfilt = scipy.signal.medfilt(data[weights], kernel_size=5)
    data[weights] -= medfilt
    return data


def scale_chans(data, nchans= 16):
    """ Find the median of each subband and subtract it from
        the data.

        Inputs:
            data: The channel data to scale.
            nchans: The number of channels to combine together for
                each subband (Default: 16)
    """
    scaled = []
    for lochan in range(0, len(data), nchans):
        subscaled = data[lochan:lochan+nchans]
        median = np.median(subscaled)
        subscaled -= median
        scaled.extend(subscaled)
    return np.asarray(scaled)


def get_profile(data):
    return np.sum(data, axis=0)


def remove_profile(data):
    template = get_profile(data)
    num = data.shape[0]
    err = lambda amps: np.ravel(amps[:,np.newaxis]*template - data)
    amps = opt.leastsq(err, np.zeros(num))[0]
    data -= template*amps[:,np.newaxis]
    return data


def get_chan_stats(ar):
    clone = ar.clone()
    clone.remove_baseline()
    clone.dedisperse()
    clone.pscrunch()
    clone.tscrunch()
    nchans = clone.get_nchan()
    data = remove_profile(clone.get_data().squeeze())
    std = scale(data.std(axis=1), get_chan_weights(ar).astype(bool))
    return std/np.std(std)
    

def get_subint_stats(ar):
    clone = ar.clone()
    clone.remove_baseline()
    clone.set_dispersion_measure(0)
    clone.dedisperse()
    clone.pscrunch()
    clone.fscrunch()
    nsubs = clone.get_nsubint()
    data = remove_profile(clone.get_data().squeeze())
    #std = scale(data.std(axis=1), get_subint_weights(ar).astype(bool))
    normtest = scipy.stats.mstats.normaltest(data, axis=1)[0]
    return normtest


def zero_weight_subint(ar, isub):
    subint = ar.get_Integration(int(isub))
    subint.uniform_weight(0.0)


def zero_weight_chan(ar, ichan):
    for isub in range(ar.get_nsubint()):
        subint = ar.get_Integration(int(isub))
        subint.set_weight(int(ichan), 0.0)


def get_subint_weights(ar):
    return ar.get_weights().sum(axis=1)


def get_chan_weights(ar):
    return ar.get_weights().sum(axis=0)


def clean_simple(ar, timethresh=1.0, freqthresh=3.0):
    plot(ar, "before_simple_clean")
    # Get stats for subints
    subint_stats = get_subint_stats(ar)
    
    # Get stats for chans
    chan_stats = get_chan_stats(ar)

    for isub in np.argwhere(subint_stats >= timethresh):
        print "De-weighting subint# %d" % isub
        zero_weight_subint(ar, isub)
    for ichan in np.argwhere(chan_stats >= freqthresh):
        print "De-weighting chan# %d" % ichan
        zero_weight_chan(ar, ichan)
    plot(ar, "after_simple_clean")
    unloadfn = "%s.cleaned" % ar.get_filename()
    print "Unoading cleaned archive as %s" % unloadfn
    ar.unload(unloadfn)


def clean_iterative(ar, threshold=2.0):
    ii = 0
    while True:
        # Get stats for subints
        subint_stats = get_subint_stats(ar)
        worst_subint = np.argmax(subint_stats)
        
        # Get stats for chans
        chan_stats = get_chan_stats(ar)
        worst_chan = np.argmax(chan_stats)

        # Check that at least something should be masked
        if (chan_stats[worst_chan] < threshold) and \
                    (subint_stats[worst_subint] < threshold):
            break
        else:
            if subint_stats[worst_subint] > chan_stats[worst_chan]:
                print "De-weighting subint# %d" % worst_subint
                zero_weight_subint(ar, worst_subint)
            else:
                print "De-weighting chan# %d" % worst_chan
                zero_weight_chan(ar, worst_chan)
        plot(ar, "bogus_%d" % ii)
        ii += 1
    unloadfn = "%s.cleaned" % ar.get_filename()
    print "Unoading cleaned archive as %s" % unloadfn
    ar.unload(unloadfn)


def plot(ar, basename=None):
    """Plot.

        Inputs:
            ar: The archive to make the plot for.
            basename: The basename of the output plots.
                (Default: Do not output plots.)

        Outputs:
            None
    """
    funcs = [lambda data: data.mean(axis=1), \
             lambda data: data.std(axis=1), \
             lambda data: data.ptp(axis=1), \
             lambda data: scipy.stats.skew(data, axis=1), \
             lambda data: scipy.stats.kurtosis(data, axis=1), \
             lambda data: scipy.stats.mstats.normaltest(data, axis=1)[0]]
    labels = ["Mean", "Std dev", "Max-min", "Skew", "Kurtosis", "Normality"]
    thresholds = [1, 1, 1, 1, 1, 5]
    scales = [1, 1, 1, 1, 1, 0]
    width = 0.45
    N = len(funcs)
    dw = width/N

    clone = ar.clone()
    clone.remove_baseline()
    clone.set_dispersion_measure(0)
    clone.dedisperse()
    clone.pscrunch()
    clone.fscrunch()
    nsubs = clone.get_nsubint()
    data = clone.get_data().squeeze()
    data = remove_profile(clone.get_data().squeeze())
    weights = get_subint_weights(ar).astype(bool)

    plt.figure(figsize=(11,8))
    ax = plt.axes([0.1,0.1,0.4,0.7])
    plt.imshow(data, origin='bottom', aspect='auto', \
                cmap=matplotlib.cm.gist_heat, interpolation='nearest')
    plt.ylabel('subint number')
    plt.xlabel('bin number')
    plt.axis('tight')
    
    plt.axes([0.1,0.8,0.4,0.1], sharex=ax)
    plt.plot(np.sum(data, axis=0), 'k-')
    plt.ylabel('Intensity')
    plt.setp(plt.gca().xaxis.get_ticklabels(), visible=False)
    plt.axis('tight')

    for ii, (func, label, thresh, scl) in \
                    enumerate(zip(funcs, labels, thresholds, scales)):
        plt.axes([0.5+dw*ii,0.1,dw,0.7], sharey=ax)
        stat = func(data)
        
        # Print normality info for stat
        print label
        sorted_stat = np.sort(stat)[::-1]
        for jj in range(len(sorted_stat))[:30]:
            normality = scipy.stats.normaltest(sorted_stat[jj:], axis=None)[0]
            print "    %d: %g" % (jj, normality) 
        
        if scl:
            plt.plot(stat/np.std(stat), np.arange(nsubs), 'k-')
        else:
            plt.plot(stat, np.arange(nsubs), 'k-')
        plt.axvline(thresh, c='k', ls='--')
        plt.xlabel(label)
        plt.xticks(rotation=45, size='x-small')
        plt.setp(plt.gca().yaxis.get_ticklabels(), visible=False)
        plt.axis('tight')
    
    if basename is not None:
        plt.savefig(basename+"_time-vs-phase.png")
    
    funcs = [lambda data: scale_chans(data.mean(axis=1)), \
             lambda data: scale_chans(data.std(axis=1)), \
             lambda data: data.ptp(axis=1), \
             lambda data: scipy.stats.skew(data, axis=1), \
             lambda data: scipy.stats.kurtosis(data, axis=1), \
             lambda data: scipy.stats.mstats.normaltest(data, axis=1)[0]]
    
    clone = ar.clone()
    clone.remove_baseline()
    clone.dedisperse()
    clone.pscrunch()
    clone.tscrunch()
    nchans = clone.get_nchan()
    data = remove_profile(clone.get_data().squeeze())
    weights = get_chan_weights(ar).astype(bool)

    plt.figure(figsize=(11,8))
    ax = plt.axes([0.1,0.1,0.4,0.7])
    plt.imshow(data, origin='bottom', aspect='auto', \
                cmap=matplotlib.cm.gist_heat, interpolation='nearest')
    plt.ylabel('chan number')
    plt.xlabel('bin number')
    plt.axis('tight')
    
    plt.axes([0.1,0.8,0.4,0.1], sharex=ax)
    plt.plot(np.sum(data, axis=0), 'k-')
    plt.ylabel('Intensity')
    plt.setp(plt.gca().xaxis.get_ticklabels(), visible=False)
    plt.axis('tight')
    
    for ii, (func, label, thresh, scl) in \
                    enumerate(zip(funcs, labels, thresholds, scales)):
        plt.axes([0.5+dw*ii,0.1,dw,0.7], sharey=ax)
        stat = func(data)
        print stat.shape, nchans
        if scl:
            plt.plot(stat/np.std(stat), np.arange(nchans), 'k-')
        else:
            plt.plot(stat, np.arange(nchans), 'k-')
        plt.axvline(thresh, c='k', ls='--')
        plt.xlabel(label)
        plt.xticks(rotation=45, size='x-small')
        plt.setp(plt.gca().yaxis.get_ticklabels(), visible=False)
        plt.axis('tight')

    if basename is not None:
        plt.savefig(basename+"_freq-vs-phase.png")


def main():
    ar = psrchive.Archive_load(sys.argv[1])
    #clean_simple(ar, timethresh=5.0, freqthresh=3.0)
    plot(ar, "%s.testplot" % ar.get_filename())


if __name__ == '__main__':
    main()