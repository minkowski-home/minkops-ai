import os
import tensorflow as tf
import numpy as np
import cv2


def parse_filename(filename):
    try:
        parts = filename.split('_')
        if len(parts) < 3:
            return None, None, None
        age = int(parts[0])
        gender = int(parts[1])
        race = int(parts[2].split('.')[0])
        return age, gender, race
    except (ValueError, IndexError):
        return None, None, None


def process_image(file_path):
    img = tf.io.read_file(file_path)
    img = tf.image.decode_jpeg(img, channels=3)
    img = tf.image.resize(img, [200, 200])
    img = img / 255.0
    return img


def preprocess_labels(age, gender, race):
    return (tf.cast(age, tf.float32),
            gender,
            tf.one_hot(race, depth=5))


@tf.function
def load_and_preprocess_image(file_path, label):
    age = label[0]
    gender = label[1]
    race = label[2]
    return process_image(file_path), preprocess_labels(age, gender, race)


def preprocess_for_training(dir, batch_size, shuffle_buffer_size):
    file_paths = []
    labels = []

    for file in os.listdir(dir):
        age, gender, race = parse_filename(file)
        if age is not None:
            file_paths.append(os.path.join(dir, file))
            labels.append((age, gender, race))

    dataset = tf.data.Dataset.from_tensor_slices((file_paths, labels))
    dataset = dataset.map(load_and_preprocess_image, num_parallel_calls=tf.data.AUTOTUNE)
    dataset = dataset.shuffle(shuffle_buffer_size).batch(batch_size).prefetch(tf.data.AUTOTUNE)
    return dataset


def preprocess_for_prediction(frame):
    frame_resized = cv2.resize(frame, (200, 200))
    frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
    frame_normalized = frame_rgb / 255.0
    frame_tensor = tf.convert_to_tensor(frame_normalized, dtype=tf.float32)
    frame_batch = tf.expand_dims(frame_tensor, 0)
    return frame_batch
