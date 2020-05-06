#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""

Helper functions for CASCADE:
  
  define_model():
    defines the architecture of the deep network 
    
  calculate_noise_levels():
    computes the noise level for dF/F traces
    
  preprocess_traces():
    converts calcium data to a format that can be used by the deep network
    
  calibrated_ground_truth_artificial_noise():
    resamples ground truth datasets at a given noise level and frame rate
    
  preprocess_groundtruth_artificial_noise_balanced():
    converts the resampled ground truth in a format that can be used by the deep network for training


  Created in Aug 2019
  Modified in May 2020

  @authors: Peter Rupprecht (p.t.r.rupprecht+cascade@gmail.com) and Adrian Hoffmann


"""


""""
Import dependencies.
os, glob, numpy and scipy are standard libraries contained in Anaconda.
Keras is a high-level user interface for the deep learning framework TensorFlow. 

"""

import os
import glob as glob

import numpy as np

import scipy.io as sio
from scipy.ndimage.filters import gaussian_filter
from scipy.signal import resample, convolve
from scipy.interpolate import interp1d
from scipy.stats import invgauss
          
from keras.layers import Dense, Flatten, MaxPooling1D, Conv1D, Input




def define_model(filter_sizes,filter_numbers,dense_expansion,windowsize,loss_function,optimizer, conv_filter=Conv1D):
  
  """"
  Defines the model using the API of Keras.
  
  The model consists of 3 convolutional layers ('conv_filter'), 2 downsampling layers
  ('MaxPooling1D') and 1 dense layer ('Dense').
  
  To modify the architecture of the network, only the define_model() function needs to be modified.
  
  Example: model = define_model(filter_sizes,filter_numbers,dense_expansion,windowsize,loss_function,optimizer)
  
  """
  inputs = Input(shape=(windowsize,1))

  outX = conv_filter(filter_numbers[0], filter_sizes[0], strides=1, activation='relu')(inputs)
  outX = conv_filter(filter_numbers[1], filter_sizes[1], activation='relu')(outX)
  outX = MaxPooling1D(2)(outX)
  outX = conv_filter(filter_numbers[2], filter_sizes[2], activation='relu')(outX)
  outX = MaxPooling1D(2)(outX)

  outX = Dense(dense_expansion, activation='relu')(outX) # 'linear' units work here as well!
  outX = Flatten()(outX)
  predictions = Dense(1,activation='linear')(outX)
  model = Model(inputs=[inputs],outputs=predictions)
  model.compile(loss=loss_function, optimizer=optimizer)

  return model



        
def calculate_noise_levels(neurons_x_time, frame_rate):
  
    """"
    Computes the noise levels for each neuron of the input matrix 'dF_traces'.
    
    The noise level is computed as the median absolute dF/F difference 
    between two subsequent time points. This is a outlier-robust measurement
    that converges to the simple standard deviation of the dF/F trace for 
    uncorrelated and outlier-free dF/F traces.
    
    Afterwards, the value is divided by the square root of the frame rate
    in order to make it comparable across recordings with different frame rates.
    
    
    input: dF_traces (matrix with nb_neurons x time_points)
    output: vector of noise levels for all neurons
    
    """
    dF_traces = neurons_x_time

    nb_neurons = dF_traces.shape[0]
    noise_levels = np.zeros( nb_neurons )

    for neuron in range(nb_neurons):
        noise_levels[neuron] = np.nanmedian( np.abs(np.diff(dF_traces[neuron,:])))/np.sqrt(frame_rate)

    return noise_levels * 100     # scale noise levels to percent




def preprocess_traces(neurons_x_time, before_frac, window_size):
    
    """
    Transform dF/F data into a format that can be used by the deep network.
    
    For each time point, a window of the size 'window_size' of the dF/F is extracted.

    input:  dF/F traces (matrix with nb_neurons x time_points)
            window_size (size of the receptive window of the deep network)
            before_frac (positioning of the window around the current time point; 0.5 means center position)
    output: X, a matrix with nb_neurons x time_points x window_size

    """
    before = int( before_frac * window_size )

    dF_traces = neurons_x_time

    nb_neurons = dF_traces.shape[0]
    nb_timepoints = dF_traces.shape[1]

    X = np.zeros( (nb_neurons,nb_timepoints,window_size) ) * np.nan

    for neuron in range(nb_neurons):
        for timepoint in range(nb_timepoints-window_size):

            X[neuron,timepoint+before,:] = dF_traces[neuron, timepoint:(timepoint+window_size)]

    return X




def calibrated_ground_truth_artificial_noise(ground_truth_folder,noise_level,sampling_rate,omission_list=[], verbose=3):
  
    """
    sub_traces_all, sub_traces_events_all, frame_rate = calibrated_ground_truth(ground_truth_folder,noise_level,sampling_rate)
    
    Inputs:
    
      Folder with ground truth pixel traces (dF/F) in *.mat files
      Noise level at which the ground truth should be resampled
      >> The noise level is defined as the median different between subsequent samples (i.e., high-frequency noise)
      Temporal sampling rate at which the ground truth should be resampled
    
    Outputs:
    
      The extracted subtraces as a matrix ('sub' refers to the subset of ROI pixels used for the respective subtrace)
      The simultaneously recorded spikes, with the same time bins
      The frame rate, usually identical to the input target sampling rate
      >> If the input sampling rate does not differ >5% from the original sampling rate of the ground truth, there will be no resampling
    
    """
  
    # Iterate through all ground truth files of the selected dataset
    fileList = sorted(list(set(glob.glob( os.path.join(ground_truth_folder,'*_mini.mat')))))
  
    # Omit neurons from the training data, if indicated in the omission_list
    # This is useful if the network is tested with a leave-one-out strategy
    for index in sorted(omission_list, reverse=True):
        del fileList[index]
  
    # Initialize lists which will later contain the resampled ground truth
    sub_traces_all = [None] * len(fileList)
    sub_traces_events_all = [None] * len(fileList)
    events_all = [None] * len(fileList)
    framerate_all = [None] * len(fileList)
  
    # for loop over all mat files / neurons in this dataset
    for file_index,neuron_file in enumerate(fileList):
  
      if verbose > 2: print('Resampling neuron '+str(file_index+1)+' from a total of '+str(len(fileList))+' neurons.')
  
      # Load mat file; the file contains a Matlab struct
      dataset_neuron_all = sio.loadmat(neuron_file)['CAttached'][0]
  
      # Initialize arrays that will contain the ground truth extracted from this neuron
      sub_traces = None
      sub_traces_events = None
      events_all[file_index] = [None] * 100000
      counter = 0
  
      # For loop over all trials of this neuron; trial is an uninterrupted
      # ground truth recording of a single neuron
      for i,trial in enumerate(dataset_neuron_all):
  
        # Find the relevant elements in the data structure
        # (dF/F traces; spike events; time stamps of fluorescence recording)
        keys = trial[0][0].dtype.descr
        keys_unfolded = list(sum(keys, ()))
  
        traces_index = int(keys_unfolded.index("fluo_mean")/2)
        fluo_time_index = int(keys_unfolded.index("fluo_time")/2)
        events_index = int(keys_unfolded.index("events_AP")/2)
  
        events = trial[0][0][events_index]
        events = events[~np.isnan(events)] # exclude NaN entries for the Theis et al. data sets
        ephys_sampling_rate = 1e4
  
        fluo_times = np.squeeze(trial[0][0][fluo_time_index])
        frame_rate = 1/np.nanmean(np.diff(fluo_times))
  
        traces_mean = np.squeeze(trial[0][0][traces_index])
        traces_mean = traces_mean[:fluo_times.shape[0]]
  
        traces_mean = traces_mean[~np.isnan(fluo_times)]
        fluo_times = fluo_times[~np.isnan(fluo_times)]
        
        # Compute the baseline noise level for this recording
        base_noise = np.nanmedian(np.abs(np.diff(traces_mean)))*100/np.sqrt(frame_rate)
        # Test how much artificial noise must be added to reach the target noise level
        # THe output of this procedure is 'noise_std'
        test_noise = np.zeros((20,))
        for test_i in np.arange(20):
          noise_trace = np.random.normal(0,test_i/100*np.sqrt(frame_rate), traces_mean.shape)
          test_noise[test_i] = np.nanmedian(np.abs(np.diff(noise_trace+traces_mean)))*100/np.sqrt(frame_rate)
  
        interpolating_function = interp1d(test_noise,np.arange(20), kind='linear')
  
        if noise_level >= test_noise[0]:
  
          noise_std = interpolating_function(noise_level)/100*np.sqrt(frame_rate)
          # Get as many artificial noisified replica traces such that natural noise (which
          # is correlated across replicas is not dominant; this is a heuristic procedure.
          # Limit the maximum number of replicas per ground truth trace to 500.
          nb_subROIs = np.minimum(500,np.ceil( 1.2*(noise_level/base_noise)**2 ))
  
        else:
  
          nb_subROIs = 0
  
        if nb_subROIs >= 1:
  
          # Resampling is not necessary if sampling rates of ground truth and
          # target sampling rate are similar (<5% relative difference)
          if np.abs(sampling_rate - frame_rate)/frame_rate > 0.05:
  
            num_samples = int(round(traces_mean.shape[0]*sampling_rate/frame_rate))
            (traces_mean,fluo_times_resampled) = resample(traces_mean,num_samples,np.squeeze(fluo_times),axis=0)
            noise_std = noise_std*np.sqrt(sampling_rate/frame_rate)
  
          else:
  
            fluo_times_resampled = fluo_times
  
          frame_rate = 1/np.nanmean(np.diff(fluo_times_resampled))
  
          # Bin the ground truth (spike times) into time bins determined by the resampled calcium recording
          fluo_times_bin_centers = fluo_times_resampled
          fluo_times_bin_edges = np.append(fluo_times_bin_centers,fluo_times_bin_centers[-1]+1/frame_rate/2) - 1/frame_rate/2
  
          [events_binned,event_bins] = np.histogram(events/ephys_sampling_rate, bins=fluo_times_bin_edges)
  
          # Generate a noisified trace in each iteration of the for-loop
          # Noise is scaled with the square root of the mean fluorescence (fluo_level),
          # corresponding to POisson noise
          for iii in range(int(nb_subROIs)):
  
            fluo_level = np.sqrt(np.abs(traces_mean + 1))
            fluo_level /= np.median(fluo_level)
            
            noise_additional = np.random.normal(0,noise_std*fluo_level, traces_mean.shape)
            sub_traces_single = traces_mean + noise_additional
            
            # 'sub_traces' are sub-sampled replica traces from the same mean trace 'traces_mean';
            # 'sub_traces_events' are the corresponding ground truth action potentials
            
            # If 'sub_traces' exists already, append the subROI-trace; else, generate it
            # The nested if-clause covers edge cases in some ground truth data sets where
            # different trials of the same neuron have variable numbers of time points
            if np.any(sub_traces):
  
              if sub_traces.shape[0]-len(sub_traces_single) >= 0:
  
                sub_traces_single = np.append(sub_traces_single, np.zeros(sub_traces.shape[0]-len(sub_traces_single)) + np.nan )
                events_binned = np.append(events_binned, np.zeros(sub_traces_events.shape[0]-len(events_binned)) + np.nan )
  
              else:
                sub_traces = np.append(sub_traces,np.zeros((len(sub_traces_single)-sub_traces.shape[0],sub_traces.shape[1])) + np.nan, axis=0)
                sub_traces_events = np.append(sub_traces_events,np.zeros((len(events_binned)-sub_traces_events.shape[0],sub_traces_events.shape[1])) + np.nan, axis=0)
  
              sub_traces = np.append(sub_traces,sub_traces_single.reshape(-1, 1),axis=1)
              sub_traces_events = np.append(sub_traces_events,events_binned.reshape(-1, 1),axis=1)
  
            else:
  
              sub_traces = sub_traces_single.reshape(-1, 1)
              sub_traces_events = events_binned.reshape(-1, 1)
  
            events_all[file_index][counter] = events/ephys_sampling_rate
            counter += 1
  
          # Write the subROI-traces for each neuron into a list item of 'sub_traces_all'
          # (calcium) and 'sub_traces_events_all' (spikes)
          sub_traces_all[file_index] = sub_traces
          sub_traces_events_all[file_index] = sub_traces_events
      
      # Optional output: ground truth spike times; not needed to generate a training data set
      try:
        events_all[file_index] = events_all[file_index][0:sub_traces.shape[1]]
      except:
        pass
      
      framerate_all[file_index] = frame_rate
  
    return sub_traces_all, sub_traces_events_all, framerate_all, events_all





def preprocess_groundtruth_artificial_noise_balanced(ground_truth_folders,before_frac,windowsize,after_frac,noise_level,sampling_rate,smoothing,omission_list=[],permute=1,maximum_traces=5000000,verbose=3,causal_kernel=0):

    """
    The calcium traces are extracted, brought to a desired 'noise_level' and
    resampled at the 'sampling_rate' in the function 'calibrated_ground_truth_artificial_noise()',
    
    The function 'preprocess_groundtruth_artificial_noise()' goes through all
    'ground_truth_folders' and extracts the ground truth in a way that can be
    used to train the deep network.
    
    As output, this function creates a large matrix 'X' that contains for each
    timepoint of each calcium trace a vector of length 'windowsize' around the timepoint.
    
    The function also creates a vector Y that contains the corresponding spikes/non-spikes.
    Random permutations ('permute = 1') un-do the original sequence of the timepoints.
    
    The number of samples is limited to 5 million. 
    
    """

    sub_traces_all = [None]*500
    sub_traces_events_all = [None]*500
    events_all = [None]*500
  
    neuron_counter = 0
    nbx_datapoints = [None]*500
    dataset_sizes = np.zeros(len(ground_truth_folders),)
    dataset_indices = [None]*500
    
    # Go through all ground truth data sets and extract re-sampled ground truth
    for dataset_index,training_dataset in enumerate(ground_truth_folders):
  
      base_folder = os.getcwd()
      
      # Exception handling ('try') is used here to catch errors that arise if for example
      # some of the datasets contribute zero samples because they do not contain 
      # recordings with sufficiently low noise levels (must be lower than 'noise_level')
      # or sufficiently long trials (must be significantly longer than 'window_size').
      try:
          if verbose > 1: print('Preprocessing dataset number', dataset_index)
  
          sub_traces_allX, sub_traces_events_allX, frame_rate, events_allX = calibrated_ground_truth_artificial_noise(ground_truth_folders[dataset_index],noise_level,sampling_rate,omission_list, verbose)
  
          datapoint_counter = 0
          for k in range(len(sub_traces_allX)):
            try:
               datapoint_counter += sub_traces_allX[k].shape[1]*sub_traces_allX[k].shape[0]
            except:
              if verbose > 2: print('No things for k={}'.format(k))
  
          dataset_sizes[dataset_index] = datapoint_counter
  
          nbx_datapoints[neuron_counter:neuron_counter+len(sub_traces_allX)] = datapoint_counter*np.ones(len(sub_traces_allX),)
          sub_traces_all[neuron_counter:neuron_counter+len(sub_traces_allX)] = sub_traces_allX
          sub_traces_events_all[neuron_counter:neuron_counter+len(sub_traces_allX)] = sub_traces_events_allX
          events_all[neuron_counter:neuron_counter+len(sub_traces_allX)] = events_allX
          dataset_indices[neuron_counter:neuron_counter+len(sub_traces_allX)] = dataset_index*np.ones(len(sub_traces_allX),)
  
          neuron_counter += len(sub_traces_allX)
  
      except:
           sub_traces_allX = None
           dataset_sizes[dataset_index] = np.NaN
      os.chdir(base_folder)
  
    mininum_traces = 15e6/len(ground_truth_folders)
    
    # Reduce the number of data points for relatively large data sets to avoid bias
    reduction_factors = dataset_sizes/mininum_traces
  
    if np.nanmax(reduction_factors) > 1:
      oversampling = 1
    else:
      oversampling = 0
  
    if verbose>1: print('Reducing ground truth by a factor of approximately '+str(int(3*np.nanmean(reduction_factors)))+'.')
  
    nbx_datapoints = nbx_datapoints[:neuron_counter]
    sub_traces_all = sub_traces_all[:neuron_counter]
    sub_traces_events_all = sub_traces_events_all[:neuron_counter]
    events_all = events_all[:neuron_counter]
    dataset_indices = dataset_indices[:neuron_counter]
  
    if verbose>1: print('Number of neurons in the ground truth: '+str(len(sub_traces_events_all)))
  
    before = int(before_frac*windowsize)
    after = int(after_frac*windowsize)
  
    X = np.zeros((15000000,windowsize,))
    Y = np.zeros((15000000,))
  
    # For-loop to generate the outputs 'X' and 'Y'
    counter = 0
    for neuron_ix,(sub_traces,sub_traces_events) in enumerate(zip(sub_traces_all,sub_traces_events_all)):
  
      if sub_traces is not None:
  
        for trace_index in range(sub_traces.shape[1]):
  
          single_trace = sub_traces[:,trace_index]
          single_spikes = sub_traces_events[:,trace_index]
          
          # Optional: Generates ground truth with causally smoothed kernel (see paper for details)
          if causal_kernel:
            
            xx = np.arange(0,199)/sampling_rate
            yy = invgauss.pdf(xx,smoothing/sampling_rate*2,101/sampling_rate,1)
            ix = np.argmax(yy)
            yy = np.roll(yy,int((99-ix)/1.5))
            yy = yy/np.sum(yy)
            single_spikes = convolve(single_spikes,yy,mode='same')
            
          else:
            
            single_spikes = gaussian_filter(single_spikes.astype(float), sigma=smoothing)
            
          recording_length = np.sum(~np.isnan(single_trace))
  
          datapoints_used = np.minimum(len(single_spikes)-windowsize,recording_length-windowsize)
  
          # Discarding (randomly chosen) samples to reduce ground truth dataset size
          if oversampling:
  
            datapoints_used_rand = np.random.permutation(datapoints_used)
            reduce_samples = reduction_factors[int(dataset_indices[neuron_ix])]
            datapoints_used_rand = datapoints_used_rand[0:int(len(datapoints_used_rand)/( max(reduce_samples,1)  ))]
  
          else:
  
            datapoints_used_rand = np.arange(datapoints_used)
  
          for time_points in datapoints_used_rand:
  
            Y[counter,] = single_spikes[time_points+before]
            X[counter,:,] = single_trace[time_points:(time_points+before+after)]
            counter += 1
  
    Y = np.expand_dims(Y[:counter],axis=1)
    X = np.expand_dims(X[:counter,:],axis=2)
    
    # Permute the ordering of the output for improved gradient descent during learning
    if permute == 1:
  
      p = np.random.permutation(len(X))
      X = X[p,:,:]
      Y = Y[p,:]
  
      # Maximum of 5e6 training samples
      X = X[:5000000,:,:]
      Y = Y[:5000000,:]
  
    os.chdir(base_folder)
  
    if verbose > 1: print('Shape of training dataset X: {}    Y: {}'.format(X.shape, Y.shape))
    return X,Y