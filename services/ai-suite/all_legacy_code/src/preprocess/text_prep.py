import tensorflow as tf
import os
import joblib
import json
import re
import os
import numpy as np
import nltk
from nltk.translate.bleu_score import sentence_bleu


def convert_to_sets(file_path, length=2, split_speaker=False):
    """
    Processes a dialogue file to create sets of dialogues. If split_speaker is True,
    it returns a list of tuples, where each tuple contains one 'customer' dialogue and its
    corresponding 'system' dialogue. If split_speaker is False, it returns lists of dialogues
    with the specified length.

    Parameters:
    file_path (str): Path to the file containing dialogues.
    length (int): The length of dialogue sets to return when split_speaker is False.
    split_speaker (bool): Flag to determine the format of the output (tuples or lists).

    Returns:
    list: A list of tuples (when split_speaker=True) or lists (when split_speaker=False)
    containing dialogue sets.
    """
    sets_of_lines = []
    current_set = []

    with open(file_path, 'r', encoding='utf-8') as f:
        all_lines = [line.rstrip('\n') for line in f]

    for line in all_lines:
        # Lowercase and clean the line
        line = line.lower().replace(',', '').replace('.', '')
        line = re.sub(r'\$\d+(\.\d{2})?', '<price>', line)

        if split_speaker:
            if line.startswith('customer:'):
                if current_set and len(current_set) == 1:
                    sets_of_lines.append(current_set)
                current_set = [line]
            elif line.startswith('system:'):
                if current_set:
                    current_set.append(line)
                    sets_of_lines.append(current_set)
                    current_set = []
        else:
            # Original functionality for unsplit dialogues
            if line.startswith('customer:') and not current_set:
                current_set.append(line)
            elif line.startswith('system:') and current_set:
                current_set.append(line)
                if len(current_set) >= length:
                    sets_of_lines.append(current_set)
                    current_set = []
            elif current_set:
                current_set.append(line)

            if len(current_set) == length + 1:
                last_line = current_set.pop()
                sets_of_lines.append(current_set)
                current_set = [last_line]

    # Add any leftover lines as a final set for unsplit dialogues
    if not split_speaker and current_set:
        sets_of_lines.append(current_set)

    return sets_of_lines


def file_to_sequences(file_path, intent, split_speaker=False, length=2):
    """
    Processes a dialogue file to create sequences of dialogues. If split_speaker is True,
    it returns two lists, one with 'customer' dialogues and another with corresponding 'system' dialogues.
    Each index in the 'customer' list corresponds to the same index in the 'system' list.

    Parameters:
    file_path (str): Path to the file containing dialogues.
    intent (str): The intent label for the dialogues.
    split_speaker (bool): Flag to determine if dialogues should be split by speaker.

    Returns:
    tuple: Two lists, one for 'customer' dialogues and one for 'system' dialogues, along with the intent list.
    """
    sets_of_lines = convert_to_sets(file_path, length=length, split_speaker=split_speaker)

    customer_sequences = []
    system_sequences = []
    intents = []

    for set_ in sets_of_lines:
        if split_speaker:
            # Ensure the set has exactly two elements (customer and system pair)
            if len(set_) == 2 and set_[0].startswith('customer:') and set_[1].startswith('system:'):
                customer_sequence, system_sequence = set_
                customer_sequences.append(customer_sequence)
                system_sequences.append(system_sequence)
                intents.append(intent)
        else:
            # Concatenate the lines in the set into a single string for non-split sequences
            concatenated_sequence = " ".join(set_)
            sequence_with_token = f"{concatenated_sequence}"  # GPT-2 end-of-text token can be added if needed
            customer_sequences.append(sequence_with_token)  # In non-split mode, all sequences go here
            intents.append(intent)

    if split_speaker:
        return customer_sequences, system_sequences, intents
    else:
        return customer_sequences, intents


def preprocess_for_gpt2(final_sequences, tokenizer, train=True, one_shift=True, max_length=20, batch_size=16):
    """
    Preprocesses data for training or inference with options for sequence shifting.

    Parameters:
    final_sequences (tuple or list): Customer and system dialogues or single list of sequences.
    tokenizer: Tokenizer to be used for encoding the dialogues.
    train (bool): Flag to determine if the function is used for training or inference.
    one_shift (bool): If True, Y sequence is shifted by one from X; if False, X and Y are separate dialogues.

    Returns:
    tf.data.Dataset or dict: TensorFlow Dataset for training or tokenized data for inference.
    """
    if train:
        if one_shift:
            # Tokenize and prepare dataset with shifted sequences
            tokenized_data = tokenizer(final_sequences, max_length=max_length, truncation=True, padding='max_length',
                                       return_tensors="tf")
            input_ids_X = tokenized_data['input_ids'][:, :-1]
            input_ids_Y = tokenized_data['input_ids'][:, 1:]
            attention_mask_X = tokenized_data['attention_mask'][:, :-1]
            dataset = tf.data.Dataset.from_tensor_slices(
                ({'input_ids': input_ids_X, 'attention_mask': attention_mask_X}, input_ids_Y))
        else:
            # Unpack dialogues and tokenize separately
            customer_dialogues, system_dialogues = final_sequences
            tokenized_customers = tokenizer(customer_dialogues, max_length=max_length, truncation=True,
                                            padding='max_length',
                                            return_tensors="tf")
            tokenized_systems = tokenizer(system_dialogues, max_length=max_length, truncation=True,
                                          padding='max_length',
                                          return_tensors="tf")
            dataset = tf.data.Dataset.from_tensor_slices(({'input_ids': tokenized_customers['input_ids'],
                                                           'attention_mask': tokenized_customers['attention_mask']},
                                                          tokenized_systems['input_ids']))

        return dataset.shuffle(10000).batch(batch_size).prefetch(tf.data.experimental.AUTOTUNE)

    else:
        # For inference
        tokenized_customers = tokenizer(final_sequences, return_tensors="tf", padding='max_length', truncation=True,
                                        max_length=max_length) if tokenizer else final_sequences
        return tokenized_customers


def preprocess_for_gpt3(dialogues, to_file=False, filename="output.json"):
    customer_dialogues, system_responses = dialogues

    if len(customer_dialogues) != len(system_responses):
        raise ValueError("The number of customer dialogues and system responses must be the same.")

    formatted_conversations = []
    for customer, system in zip(customer_dialogues, system_responses):
        formatted_conversation = {
            "messages": [
                {
                    "role": "user",
                    "content": customer.split(':', 1)[1].strip()
                },
                {
                    "role": "assistant",
                    "content": system.split(':', 1)[1].strip()
                }
            ]
        }
        formatted_conversations.append(formatted_conversation)

    if to_file:
        with open(filename, 'w') as file:
            for conv in formatted_conversations:
                file.write(json.dumps(conv) + '\n')
    else:
        return formatted_conversations


def ordinal_encode(intents, intent_to_label=None):
    """
    Preprocess a list of intent strings into integer labels using tf.lookup.

    Args:
    - intents (list of str): List of intent strings.
    - intent_to_label (tf.lookup.StaticVocabularyTable, optional): Vocabulary table for mapping intents to labels.
      If not provided, a default table will be created.

    Returns:
    - intent_labels (tf.Tensor): Tensor of integer labels corresponding to the input intents.
    - intent_to_label (tf.lookup.StaticVocabularyTable): Vocabulary table used for mapping intents to labels.
    """

    if intent_to_label is None:
        # Create a default vocabulary table if not provided
        lookup_init = tf.lookup.KeyValueTensorInitializer(
            keys=[b'order', b'complain', b'enquiry'],
            values=[0, 1, 2],
            key_dtype=tf.string,
            value_dtype=tf.int64,
        )
        intent_to_label = tf.lookup.StaticVocabularyTable(
            lookup_init,
            num_oov_buckets=1,
        )

    # Convert intent strings to integer labels
    intent_labels = intent_to_label.lookup(tf.constant(intents, dtype=tf.string))

    return intent_labels, intent_to_label


def preprocess_for_intent(final_sequences, intents=None, tokenizer=None, train=True):
    if tokenizer:
        tokenized_data = tokenizer(final_sequences, max_length=40, truncation=True, padding='max_length',
                                   return_tensors="tf")
    else:
        tokenized_data = final_sequences

    input_ids = tokenized_data['input_ids']
    attention_mask = tokenized_data['attention_mask']

    dataset = tf.data.Dataset.from_tensor_slices({
        "input_ids": input_ids,
        "attention_mask": attention_mask
    })

    # at prediction time
    if not train:
        return dataset.shuffle(10000).batch(16).prefetch(1)

    # at training time
    intents, _ = ordinal_encode(intents)
    intents = tf.data.Dataset.from_tensor_slices(intents).map(lambda intent: tf.one_hot(intent, 3))
    dataset = tf.data.Dataset.zip((dataset, intents))
    return dataset.shuffle(10000).batch(16).prefetch(1)


def save_file(filepath, value):
    with open(filepath, 'wb') as f:
        joblib.dump(value, f)


class OneCycleLRSchedule(tf.keras.callbacks.Callback):
    def __init__(self, max_lr, total_steps, lr_start=1e-5, lr_end=1e-6, div_factor=25, pct_start=0.3):
        super(OneCycleLRSchedule, self).__init__()

        self.max_lr = max_lr  # Maximum learning rate (peak)
        self.lr_start = lr_start  # Initial learning rate
        self.lr_end = lr_end  # Final learning rate
        self.div_factor = div_factor  # Factor to divide max_lr for the minimum
        self.pct_start = pct_start  # Phase 1 percentage
        self.total_steps = total_steps  # Total steps in the cycle

        self.phase_1_steps = np.floor(pct_start * total_steps)  # Steps in the first phase
        self.phase_2_steps = total_steps - self.phase_1_steps  # Steps in the second phase

    def on_train_begin(self, logs=None):
        self.set_lr(self.lr_start)

    def on_train_batch_begin(self, batch, logs=None):
        if batch < self.phase_1_steps:
            # Phase 1: Linearly increase the learning rate
            lr = (self.max_lr - self.lr_start) / self.phase_1_steps * batch + self.lr_start
        else:
            # Phase 2: Cosine annealing to the final learning rate
            progress = (batch - self.phase_1_steps) / self.phase_2_steps
            lr = self.lr_end + 0.5 * (self.max_lr - self.lr_end) * (1 + np.cos(np.pi * progress))
        self.set_lr(lr)

    def on_epoch_end(self, epoch, logs=None):
        print(self.model.optimizer.lr)

    def set_lr(self, lr):
        tf.keras.backend.set_value(self.model.optimizer.lr, lr)

    def get_lr(self):
        return tf.keras.backend.get_value(self.model.optimizer.lr)


def piecewise_scheduler(initial_lr=5e-4, change_epoch=10, decay_ratio=0.1):
    """
    Creates a learning rate scheduler function.

    Parameters:
    initial_lr (float): The initial learning rate.
    change_epoch (int): The epoch at which the learning rate changes.
    decay_ratio (float): The factor by which the learning rate is decayed after change_epoch.

    Returns:
    function: A scheduler function that takes an epoch index and current learning rate and returns the new learning rate.
    """

    def lr_scheduler(epoch, lr):
        # If the current epoch is less than the change_epoch, use the initial learning rate
        if epoch < change_epoch:
            return initial_lr
        # Otherwise, decay the learning rate by the specified decay_ratio
        else:
            return initial_lr * decay_ratio

    return lr_scheduler
