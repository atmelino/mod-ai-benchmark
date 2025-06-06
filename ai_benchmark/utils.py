# -*- coding: utf-8 -*-
# Copyright 2019-2020 by Andrey Ignatov. All Rights Reserved.

import sys
import os
from os import path
import subprocess
import platform
import cpuinfo
import time
import multiprocessing
import logging

from psutil import virtual_memory
import numpy as np
import tensorflow as tf
from tensorflow.python.client import device_lib
from pkg_resources import parse_version
from PIL import Image

from ai_benchmark.update_utils import update_info
from ai_benchmark.config import TestConstructor
from ai_benchmark.models import *

MAX_TEST_DURATION = 100
resultCollector=[]

logger = logging.getLogger('ai_benchmark')


class BenchmarkResults:
    def __init__(self):
        self.results_inference_norm = []
        self.results_training_norm = []

        self.results_inference = []
        self.results_training = []

        self.inference_score = 0
        self.training_score = 0

        self.ai_score = 0


class Result:
    def __init__(self, mean, std):
        self.mean = mean
        self.std = std


class PublicResults:
    def __init__(self):
        self.test_results = {}
        self.ai_score = None

        self.inference_score = None
        self.training_score = None


class TestInfo:
    def __init__(self, _type, precision, use_cpu, verbose, cpu_cores, inter_threads, intra_threads):
        from ai_benchmark import __version__
        self._type = _type
        self.version = __version__
        self.py_version = sys.version
        self.tf_version = get_tf_version()
        self.tf_ver_2 = parse_version(self.tf_version) > parse_version('1.99')
        self.platform_info = get_platform_info()
        self.cpu_model = get_cpu_model()
        self.cpu_cores = cpu_cores or get_num_cpu_cores()
        self.inter_threads = inter_threads or self.cpu_cores * 2
        self.intra_threads = intra_threads or self.cpu_cores * 2
        self.cpu_ram = get_cpu_ram()
        self.is_cpu_build = is_cpu_build()
        self.is_cpu_inference = (is_cpu_build() or use_cpu)
        self.gpu_devices = get_gpu_models()
        self.cuda_version, self.cuda_build = get_cuda_info()
        self.precision = precision
        self.verbose_level = verbose
        self.results = None
        self.path = path.dirname(__file__)


def get_time_seconds():
    return int(time.time())


def get_time_ms():
    return int(round(time.time() * 1000))


def resize_image(image, dimensions):

    image = np.asarray(image)

    height = image.shape[0]
    width = image.shape[1]

    aspect_ratio_image = float(width) / height
    aspect_ratio_target = float(dimensions[1]) / dimensions[0]

    if aspect_ratio_target == aspect_ratio_image:
        image = Image.fromarray(image).resize((dimensions[1], dimensions[0]))

    elif aspect_ratio_image < aspect_ratio_target:
        new_height = int(float(width) / aspect_ratio_target)
        offset = int((height - new_height) / 2)
        image = image[offset:offset + new_height, :, :]
        image = Image.fromarray(image).resize((dimensions[1], dimensions[0]))

    else:
        new_width = int(float(height) * aspect_ratio_target)
        offset = int((width - new_width) / 2)
        image = image[:, offset:offset + new_width, :]
        image = Image.fromarray(image).resize((dimensions[1], dimensions[0]))

    return image


def load_data(test_type, dimensions):

    data = None
    if test_type == "classification":

        data = np.zeros(dimensions)
        for j in range(dimensions[0]):

            image = Image.open(path.join(path.dirname(__file__), "data/classification/" + str(j) + ".jpg"))
            image = resize_image(image, [dimensions[1], dimensions[2]])
            data[j] = image

    if test_type == "enhancement":

        data = np.zeros(dimensions)
        for j in range(dimensions[0]):
            image = Image.open(path.join(path.dirname(__file__), "data/enhancement/" + str(j) + ".jpg"))
            image = resize_image(image, [dimensions[1], dimensions[2]])
            data[j] = image

    if test_type == "segmentation":

        data = np.zeros(dimensions)
        for j in range(dimensions[0]):
            image = Image.open(path.join(path.dirname(__file__), "data/segmentation/" + str(j) + ".jpg"))
            image = resize_image(image, [dimensions[1], dimensions[2]])
            data[j] = image

    if test_type == "nlp":
        data = np.random.uniform(-4, 4, (dimensions[0], dimensions[1], dimensions[2]))

    if test_type == "nlp-text":
        data = "This is a story of how a Baggins had an adventure, " \
               "and found himself doing and saying things altogether unexpected."

    return data


def load_targets(test_type, dimensions):

    data = None
    if test_type == "classification" or test_type == "nlp":

        data = np.zeros(dimensions)
        for j in range(dimensions[0]):
            data[j, np.random.randint(dimensions[1])] = 1

    if test_type == "enhancement":

        data = np.zeros(dimensions)
        for j in range(dimensions[0]):
            image = Image.open(path.join(path.dirname(__file__), "data/enhancement/" + str(j) + ".jpg"))
            image = resize_image(image, [dimensions[1], dimensions[2]])
            data[j] = image

    if test_type == "enhancement":

        data = np.zeros(dimensions)
        for j in range(dimensions[0]):
            image = Image.open(path.join(path.dirname(__file__), "data/enhancement/" + str(j) + ".jpg"))
            image = resize_image(image, [dimensions[1], dimensions[2]])
            data[j] = image

    if test_type == "segmentation":

        data = np.zeros(dimensions)
        for j in range(dimensions[0]):
            image = Image.open(path.join(path.dirname(__file__), "data/segmentation/" + str(j) + "_segmented.jpg"))
            image = resize_image(image, [dimensions[1], dimensions[2]])
            data[j] = image

    return data


def construct_optimizer(sess, output_, target_, loss_function, optimizer, learning_rate, tf_ver_2):

    if loss_function == "MSE":
        loss_ = 2 * tf.nn.l2_loss(output_ - target_)

    if optimizer == "Adam":
        if tf_ver_2:
            optimizer = tf.compat.v1.train.AdamOptimizer(learning_rate)
        else:
            optimizer = tf.train.AdamOptimizer(learning_rate)

    train_step = optimizer.minimize(loss_)

    if tf_ver_2:
        sess.run(tf.compat.v1.variables_initializer(optimizer.variables()))
    else:
        sess.run(tf.variables_initializer(optimizer.variables()))

    return train_step


def get_model_src(test, testInfo, session):

    train_vars = None

    if testInfo.tf_ver_2 and test.use_src:

        # Bypassing TensorFlow 2.0+ RNN Bugs

        if test.model == "LSTM-Sentiment":
            input_ = tf.compat.v1.placeholder(tf.float32, [None, 1024, 300], name="input")
            output_ = LSTM_Sentiment(input_)

        if test.model == "Pixel-RNN":
            input_ = tf.compat.v1.placeholder(tf.float32, [None, 64, 64, 3], name="input")
            output_ = PixelRNN(input_)

        target_ = tf.compat.v1.placeholder(tf.float32, test.training[0].get_output_dims())

        train_step_ = construct_optimizer(session, output_, target_,  test.training[0].loss_function,
                                        test.training[0].optimizer,  test.training[0].learning_rate, testInfo.tf_ver_2)

        train_vars = [target_, train_step_]

    else:

        if testInfo.tf_ver_2:
            tf.compat.v1.train.import_meta_graph(test.model_src, clear_devices=True)
            g = tf.compat.v1.get_default_graph()
        else:
            tf.train.import_meta_graph(test.model_src, clear_devices=True)
            g = tf.get_default_graph()

        input_ = g.get_tensor_by_name('input:0')
        output_ = g.get_tensor_by_name('output:0')

    return input_, output_, train_vars


def compute_stats(results):
    if len(results) > 1:
        results = results[1:]
    return np.mean(results), np.std(results)


def print_test_results(prefix, batch_size, dimensions, mean, std):
    if std > 1 and mean > 100:
        prt_str = "%s | batch=%d, size=%dx%d: %.d ± %.d ms" % (
            prefix, batch_size, dimensions[1], dimensions[2], round(mean), round(std))
    else:
        prt_str = "%s | batch=%d, size=%dx%d: %.1f ± %.1f ms" % (
            prefix, batch_size, dimensions[1], dimensions[2], mean, std)
    logger.info(prt_str)


def init_resultCollector(testInfo):
    # hardware=testInfo.cpu_model
    for gpu_id, gpu_info in enumerate(testInfo.gpu_devices):
        hardware=gpu_info[0]
    resultCollector.append({"row1":"hardware","row2":hardware})
    resultCollector.append({"row1":"TF Build","row2":testInfo.tf_version})


def collectResults(test,prefix, batch_size, dimensions, mean, std):
    global resultCollector
    # resultCollector.append({"test":test.model,"prefix":prefix,"mean":mean,"std":std})
    # resultCollector.append({"test":test.model,"mean":mean})
    resultCollector.append({"row1":test.model,"row2":mean})


def finish_resultCollector(testInfo):
    resultCollector.append({"row1":"AI-Score","row2":testInfo.results.ai_score})


def print_intro():
    import ai_benchmark
    logger.info(">>   AI-Benchmark - %s", ai_benchmark.__version__)
    logger.info(">>   Let the AI Games begin")


def print_test_info(testInfo):
    logger.info("*  TF Version: %s", testInfo.tf_version)
    logger.info("*  Platform: %s", testInfo.platform_info)
    logger.info("*  CPU: %s", testInfo.cpu_model)
    logger.info("*  CPU RAM: %s GB", testInfo.cpu_ram)

    if not testInfo.is_cpu_inference:

        for gpu_id, gpu_info in enumerate(testInfo.gpu_devices):
            logger.info("*  GPU/%s: %s", gpu_id, gpu_info[0])
            logger.info("*  GPU RAM: %s GB", gpu_info[1])

        logger.info("*  CUDA Version: %s", testInfo.cuda_version)
        logger.info("*  CUDA Build: %s", testInfo.cuda_build)

    update_info("launch", testInfo)
    logger.warning("The benchmark is running...")
    logger.warning("The tests might take up to 20 minutes")
    logger.warning("Please don't interrupt the script")


def get_tf_version():
    try:
        return tf.__version__
    except:
        pass
    return "N/A"


def get_platform_info():
    platform_info = "N/A"
    try:
        return platform.platform()
    except:
        pass
    return platform_info


def get_cpu_model():
    try:
        return cpuinfo.get_cpu_info()['brand']
    except:
        return "N/A"


def get_num_cpu_cores():
    try:
        return multiprocessing.cpu_count()
    except:
        return -1


def get_cpu_ram():
    try:
        return str(round(virtual_memory().total / (1024. ** 3)))
    except:
        return "N/A"


def is_cpu_build():
    is_cpu_build = True
    try:
        if tf.test.gpu_device_name():
            is_cpu_build = False
    except:
        pass
    return is_cpu_build


def get_gpu_models():
    gpu_models = [["N/A", "N/A"]]
    gpu_id = 0
    try:
        tf_gpus = str(device_lib.list_local_devices())
        while tf_gpus.find('device_type: "GPU"') != -1 or tf_gpus.find('device_type: "XLA_GPU"') != -1:

            device_type_gpu = tf_gpus.find('device_type: "GPU"')
            if device_type_gpu == -1:
                device_type_gpu = tf_gpus.find('device_type: "XLA_GPU"')

            tf_gpus = tf_gpus[device_type_gpu:]
            tf_gpus = tf_gpus[tf_gpus.find('memory_limit:'):]
            gpu_ram = tf_gpus[:tf_gpus.find("\n")]

            gpu_ram = int(gpu_ram.split(" ")[1]) / (1024.**3)
            gpu_ram = str(round(gpu_ram * 10) / 10)

            tf_gpus = tf_gpus[tf_gpus.find('physical_device_desc:'):]
            tf_gpus = tf_gpus[tf_gpus.find('name:'):]
            gpu_model = tf_gpus[6:tf_gpus.find(',')]

            if gpu_id == 0:
                gpu_models = [[gpu_model, gpu_ram]]
            else:
                gpu_models.append([gpu_model, gpu_ram])

            gpu_id += 1
    except:
        pass
    return gpu_models


def get_cuda_info():
    cuda_version = "N/A"
    cuda_build = "N/A"
    try:
        cuda_info = str(subprocess.check_output(["nvcc", "--version"]))
        cuda_info = cuda_info[cuda_info.find("release"):]
        cuda_version = cuda_info[cuda_info.find(" ") + 1:cuda_info.find(",")]
        cuda_build = cuda_info[cuda_info.find(",") + 2:cuda_info.find("\\")]
    except:
        pass
    return cuda_version, cuda_build


def print_scores(testInfo, public_results):

    c_inference = 10000
    c_training = 10000

    if testInfo._type == "full":

        inference_score = geometrical_mean(testInfo.results.results_inference_norm)
        if np.isnan(inference_score):
            inference_score = 0
        training_score = geometrical_mean(testInfo.results.results_training_norm)
        if np.isnan(training_score):
            training_score = 0

        testInfo.results.inference_score = int(inference_score * c_inference)
        testInfo.results.training_score = int(training_score * c_training)

        public_results.inference_score = testInfo.results.inference_score
        public_results.training_score = testInfo.results.training_score

        testInfo.results.ai_score = testInfo.results.inference_score + testInfo.results.training_score
        public_results.ai_score = testInfo.results.ai_score

        update_info("scores", testInfo)

        logger.info("Device Inference Score: %s", testInfo.results.inference_score)
        logger.info("Device Training Score: %s", testInfo.results.training_score)
        logger.info("Device AI Score: %s", testInfo.results.ai_score)
        logger.info("For more information and results, please visit http://ai-benchmark.com/alpha\n")

    if testInfo._type == "inference":

        inference_score = geometrical_mean(testInfo.results.results_inference_norm)
        testInfo.results.inference_score = int(inference_score * c_inference)

        public_results.inference_score = testInfo.results.inference_score

        update_info("scores", testInfo)

        logger.info("Device Inference Score: %s", testInfo.results.inference_score)
        logger.info("For more information and results, please visit http://ai-benchmark.com/alpha\n")

    if testInfo._type == "training":

        training_score = geometrical_mean(testInfo.results.results_training_norm)
        testInfo.results.training_score = int(training_score * c_inference)

        public_results.training_score = testInfo.results.training_score

        update_info("scores", testInfo)

        logger.info("Device Training Score: %s", testInfo.results.training_score)
        logger.info("For more information and results, please visit http://ai-benchmark.com/alpha\n")

    if testInfo._type == "micro":

        inference_score = geometrical_mean(testInfo.results.results_inference_norm)
        testInfo.results.inference_score = int(inference_score * c_inference)

        public_results.inference_score = testInfo.results.inference_score

        update_info("scores", testInfo)

        logger.info("Device Inference Score: %s", testInfo.results.inference_score)
        logger.info("For more information and results, please visit http://ai-benchmark.com/alpha\n")

    return public_results


def geometrical_mean(results):
    results = np.asarray(results)
    try:
        return results.prod() ** (1.0 / len(results))
    except ZeroDivisionError:
        return np.nan


def run_tests(
        training,
        inference,
        micro,
        verbose,
        use_cpu,
        precision,
        _type,
        start_dir,
        test_ids=None,
        cpu_cores=None,
        inter_threads=None,
        intra_threads=None,
    ):

    # print(test_ids)
    testInfo = TestInfo(_type, precision, use_cpu, verbose, cpu_cores, inter_threads, intra_threads)
    testInfo.full_suite = (
        test_ids is None or
        len(test_ids) == len(TestConstructor.BENCHMARK_TESTS)
    )

    print_test_info(testInfo)
    init_resultCollector(testInfo)

    time.sleep(1)

    benchmark_tests = TestConstructor().get_tests(test_ids)
    benchmark_results = BenchmarkResults()
    public_results = PublicResults()
    os.chdir(path.dirname(__file__))

    iter_multiplier = {
        "dry": 0,
        "normal": 1,
        "high": 10,
    }.get(precision, 1)

    ConfigProto = tf.compat.v1.ConfigProto if testInfo.tf_ver_2 else tf.ConfigProto
    if use_cpu:
        config = ConfigProto(
            device_count={'GPU': 0, 'CPU': testInfo.cpu_cores},
            inter_op_parallelism_threads=testInfo.inter_threads,
            intra_op_parallelism_threads=testInfo.intra_threads,
        )
    else:
        config = None

    for test in benchmark_tests:

        if not (micro and len(test.micro) == 0):
            logger.info("\n%s/%s. %s\n", test.id, len(benchmark_tests), test.model)
        sub_id = 1

        tf.compat.v1.reset_default_graph() if testInfo.tf_ver_2 else tf.reset_default_graph()
        session = tf.compat.v1.Session(config=config) if testInfo.tf_ver_2 else tf.Session(config=config)

        with tf.Graph().as_default(), session as sess:

            input_, output_, train_vars_ = get_model_src(test, testInfo, sess)

            if testInfo.tf_ver_2:
                tf.compat.v1.global_variables_initializer().run()
                if test.type == "nlp-text":
                    sess.run(tf.compat.v1.tables_initializer())
            else:
                tf.global_variables_initializer().run()
                if test.type == "nlp-text":
                    sess.run(tf.tables_initializer())

            if inference or micro:

                for subTest in (test.inference if inference else test.micro):

                    time_test_started = get_time_seconds()
                    inference_times = []

                    for i in range(subTest.iterations * iter_multiplier):

                        if get_time_seconds() - time_test_started < subTest.max_duration \
                                or (i < subTest.min_passes and get_time_seconds() - time_test_started < MAX_TEST_DURATION) \
                                or precision == "high":

                            data = load_data(test.type, subTest.get_input_dims())
                            time_iter_started = get_time_ms()
                            sess.run(output_, feed_dict={input_: data})
                            inference_time = get_time_ms() - time_iter_started
                            inference_times.append(inference_time)

                            logger.debug("Inference Time: %s ms", inference_time)

                    time_mean, time_std = compute_stats(inference_times)

                    public_id = "%d.%d" % (test.id, sub_id)
                    public_results.test_results[public_id] = Result(time_mean, time_std)

                    benchmark_results.results_inference.append(time_mean)
                    benchmark_results.results_inference_norm.append(float(subTest.ref_time) / time_mean)

                    prefix = "%d.%d - inference" % (test.id, sub_id)
                    print_test_results(prefix, subTest.batch_size, subTest.get_input_dims(), time_mean, time_std)
                    collectResults(test,prefix, subTest.batch_size, subTest.get_input_dims(), time_mean, time_std)
                    sub_id += 1

            if training:

                for subTest in test.training:

                    if train_vars_ is None:

                        if testInfo.tf_ver_2:
                            target_ = tf.compat.v1.placeholder(tf.float32, subTest.get_output_dims())
                        else:
                            target_ = tf.placeholder(tf.float32, subTest.get_output_dims())

                        train_step = construct_optimizer(sess, output_, target_, subTest.loss_function,
                                                        subTest.optimizer, subTest.learning_rate, testInfo.tf_ver_2)

                    else:

                        target_ = train_vars_[0]
                        train_step = train_vars_[1]

                    time_test_started = get_time_seconds()
                    training_times = []

                    for i in range(subTest.iterations * iter_multiplier):

                        if get_time_seconds() - time_test_started < subTest.max_duration \
                                or (i < subTest.min_passes and get_time_seconds() - time_test_started < MAX_TEST_DURATION) \
                                or precision == "high":

                            data = load_data(test.type, subTest.get_input_dims())
                            target = load_targets(test.type, subTest.get_output_dims())

                            time_iter_started = get_time_ms()
                            sess.run(train_step, feed_dict={input_: data, target_: target})
                            training_time = get_time_ms() - time_iter_started
                            training_times.append(training_time)

                            logger.debug("Training Time: %s ms", training_time)

                    time_mean, time_std = compute_stats(training_times)

                    public_id = "%d.%d" % (test.id, sub_id)
                    public_results.test_results[public_id] = Result(time_mean, time_std)

                    benchmark_results.results_training.append(time_mean)
                    benchmark_results.results_training_norm.append(float(subTest.ref_time) / time_mean)

                    prefix = "%d.%d - training " % (test.id, sub_id)
                    print_test_results(prefix, subTest.batch_size, subTest.get_input_dims(), time_mean, time_std)
                    collectResults(test,prefix, subTest.batch_size, subTest.get_input_dims(), time_mean, time_std)
                    sub_id += 1

        sess.close()

    testInfo.results = benchmark_results
    public_results = print_scores(testInfo, public_results)
    finish_resultCollector(testInfo)

    os.chdir(start_dir)
    # print(resultCollector)
    return testInfo, public_results, resultCollector
