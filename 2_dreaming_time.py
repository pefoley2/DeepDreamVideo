#!/usr/bin/python2
__author__ = 'graphific'

import argparse
import os
import errno

# imports and basic notebook setup
import numpy as np
import scipy.ndimage as nd
import PIL.Image
import sys
sys.path.append('../caffe/distribute/python')
import caffe

# Load DNN
model_path = '../caffe/models/bvlc_googlenet/'  # substitute your path here
net_fn = model_path + 'deploy.prototxt'
param_fn = model_path + 'bvlc_googlenet.caffemodel'

net = caffe.Classifier(net_fn, param_fn,
                       # ImageNet mean, training set dependent
                       mean=np.float32([104.0, 116.0, 122.0]),
                       channel_swap=(2, 1, 0))  # the reference model has channels in BGR order instead of RGB

# a couple of utility functions for converting to and from Caffe's input
# image layout


def preprocess(net, img):
    return np.float32(np.rollaxis(img, 2)[::-1]) - net.transformer.mean['data']


def deprocess(net, img):
    return np.dstack((img + net.transformer.mean['data'])[::-1])


# Make dreams
def make_step(net, step_size=1.5, end='inception_4c/output', jitter=32, clip=True):
    '''Basic gradient ascent step.'''

    src = net.blobs['data']  # input image is stored in Net's 'data' blob
    dst = net.blobs[end]

    ox, oy = np.random.randint(-jitter, jitter + 1, 2)
    # apply jitter shift
    src.data[0] = np.roll(np.roll(src.data[0], ox, -1), oy, -2)

    net.forward(end=end)
    dst.diff[:] = dst.data  # specify the optimization objective
    net.backward(start=end)
    g = src.diff[0]
    # apply normalized ascent step to the input image
    src.data[:] += step_size / np.abs(g).mean() * g

    src.data[0] = np.roll(
        np.roll(src.data[0], -ox, -1), -oy, -2)  # unshift image

    if clip:
        bias = net.transformer.mean['data']
        src.data[:] = np.clip(src.data, -bias, 255 - bias)


def deepdream(net, base_img, iter_n=10, octave_n=4, octave_scale=1.4, end='inception_4c/output', clip=True, **step_params):
    # prepare base images for all octaves
    octaves = [preprocess(net, base_img)]
    for i in range(octave_n - 1):
        octaves.append(
            nd.zoom(octaves[-1], (1, 1.0 / octave_scale, 1.0 / octave_scale), order=1))

    src = net.blobs['data']
    # allocate image for network-produced details
    detail = np.zeros_like(octaves[-1])
    for octave, octave_base in enumerate(octaves[::-1]):
        h, w = octave_base.shape[-2:]
        if octave > 0:
            # upscale details from the previous octave
            h1, w1 = detail.shape[-2:]
            detail = nd.zoom(detail, (1, 1.0 * h / h1, 1.0 * w / w1), order=1)

        src.reshape(1, 3, h, w)  # resize the network's input image size
        src.data[0] = octave_base + detail
        print("octave %d %s" % (octave, end))
        for i in range(iter_n):
            make_step(net, end=end, clip=clip, **step_params)
            sys.stdout.write("%d " % i)
            sys.stdout.flush()
        print("")

        # extract details produced on the current octave
        detail = src.data[0] - octave_base
    # returning the resulting image
    return deprocess(net, src.data[0])

# own functions


def morphPicture(filename1, img2):
    img1 = PIL.Image.open(filename1)
    img2 = PIL.Image.fromarray(np.uint8(img2))
    return PIL.Image.blend(img1, img2, 0.5)

layersloop = ['inception_4c/output', 'inception_4d/output',
              'inception_4e/output', 'inception_5a/output',
              'inception_5b/output', 'inception_5a/output',
              'inception_4e/output', 'inception_4d/output',
              'inception_4c/output']


def make_sure_path_exists(path):
    '''
    make sure input and output directory exist, if not create them.
    If another error (permission denied) throw an error.
    '''
    try:
        os.makedirs(path)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise


def main(input, output):
    make_sure_path_exists(input)
    make_sure_path_exists(output)

    frame = np.float32(PIL.Image.open(input + '/0001.jpg'))
    frame_i = 1
    for i in range(frame_i, 2149):
        frame = deepdream(
            net, frame, end=layersloop[frame_i % len(layersloop)], iter_n=5)
        saveframe = input + "/%04d.jpg" % frame_i
        newframe = output + "/%04d.jpg" % frame_i
        frame = morphPicture(saveframe, frame)
        frame.save(newframe)
        frame = np.float32(frame)
        frame_i += 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Dreaming in videos.')
    parser.add_argument(
        '-i', '--input', help='Input directory where extracted frames are stored', required=True)
    parser.add_argument(
        '-o', '--output', help='Output directory where processed frames are to be stored', required=True)
    args = parser.parse_args()

    main(args.input, args.output)
