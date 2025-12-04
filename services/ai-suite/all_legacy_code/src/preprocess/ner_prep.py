from typing import List, Tuple
import re
import tensorflow as tf
import numpy as np


def convert_to_IOB(dataset, lookup):
    iob_data = []

    # Split entities into one-word and two-word groups
    one_word_entities = {}
    two_word_entities = {}
    for type, values in lookup['entities'].items():
        one_word_entities[type] = []
        two_word_entities[type] = []
        for value in values:
            entity_split = value.split(' ')
            if len(entity_split) == 1:
                one_word_entities[type].append(entity_split[0].lower())
            else:
                two_word_entities[type].append(' '.join(entity_split).lower())

    for instance in dataset['instances']:
        original_sentence = instance['sentence']
        # Remove punctuation for matching, but keep the original sentence for output
        sentence = re.sub(r'[^\w\s]', '', original_sentence).lower()
        words = sentence.split(' ')
        words_lower = [word.lower() for word in words]
        this_sentence_tags = ['O'] * len(words)

        # Function to update tags for a given entity type
        def update_tags(entity_values, tag_prefix):
            for entity in entity_values:
                start_index = 0
                while start_index < len(words_lower):
                    try:
                        start_index = words_lower.index(entity.split(' ')[0], start_index)
                        end_index = start_index + len(entity.split(' '))
                        if ' '.join(words_lower[start_index:end_index]) == entity:
                            this_sentence_tags[start_index] = f'B-{tag_prefix}'
                            for i in range(start_index + 1, end_index):
                                this_sentence_tags[i] = f'I-{tag_prefix}'
                        start_index = end_index
                    except ValueError:
                        break

        # Check for two-word entities
        for entity_type, values in two_word_entities.items():
            update_tags(values, entity_type)

        # Check for one-word entities
        for entity_type, values in one_word_entities.items():
            for i, word in enumerate(words_lower):
                if word in values and this_sentence_tags[i] == 'O':
                    this_sentence_tags[i] = f'B-{entity_type}'

        # Pair the original words (with punctuation) with their IOB tags
        iob_data.append((sentence, this_sentence_tags))

    return iob_data


def align_tokens_and_tags(sentence: str, tags: List[str], tokenizer) -> List[Tuple[str, str, int]]:
    words = sentence.split(' ')
    tokenized_input = tokenizer(words, return_tensors="tf", is_split_into_words=True)
    tokens = tokenized_input.tokens()
    token_ids = tokenized_input['input_ids'][0].numpy() # Extracting the token IDs

    aligned_tags = []
    current_word = 0

    for idx, token in enumerate(tokens):
        if token in ["[CLS]", "[SEP]"]:
            continue

        if token.startswith("##"):
            base_tag = aligned_tags[-1][1]
            if base_tag.startswith('B-'):
                tag = 'I-' + base_tag[2:]
            else:
                tag = base_tag
        else:
            tag = tags[current_word]
            current_word += 1

        # Append the token, its tag, and its integer token ID to the list
        aligned_tags.append((token, tag, token_ids[idx]))

    return aligned_tags


def preprocess_for_training(final_data, max_seq_length, batch_size=32, shuffle_buffer_size=10000):
    # Initialize arrays for input IDs, attention masks, and labels
    input_ids = []
    attention_masks = []
    labels = []

    # Unique label mapping, including -100 for ignored index (padding)
    unique_labels = sorted(set(tag for sentence in final_data for _, tag, _ in sentence))
    label_map = {label: i for i, label in enumerate(unique_labels)}
    label_map[-100] = -100

    # Process each sentence in the dataset
    for sentence in final_data:
        sentence_ids = [token_id for token, tag, token_id in sentence]
        sentence_labels = [label_map[tag] for token, tag, token_id in sentence]
        padding_length = max_seq_length - len(sentence_ids)

        # Pad the sequences
        sentence_ids.extend([0] * padding_length)
        sentence_labels.extend([-100] * padding_length)  # -100 is used to ignore padding in loss computation
        attention_mask = [1] * len(sentence) + [0] * padding_length

        # Truncate if necessary and append to the lists
        input_ids.append(sentence_ids[:max_seq_length])
        labels.append(sentence_labels[:max_seq_length])
        attention_masks.append(attention_mask[:max_seq_length])

    # Convert to TensorFlow Dataset
    train_dataset = tf.data.Dataset.from_tensor_slices(({
                                                            'input_ids': input_ids,
                                                            'attention_mask': attention_masks,
                                                        }, tf.one_hot(labels, depth=15)))

    return train_dataset.batch(batch_size).prefetch(1), label_map


class F1Score(tf.keras.metrics.Metric):
    def __init__(self, name='f1_score', **kwargs):
        super(F1Score, self).__init__(name=name, **kwargs)
        self.precision = tf.keras.metrics.Precision()
        self.recall = tf.keras.metrics.Recall()
        self.f1_score = self.add_weight(name='f1', initializer='zeros')

    def update_state(self, y_true, y_pred, sample_weight=None):
        self.precision.update_state(y_true, y_pred, sample_weight)
        self.recall.update_state(y_true, y_pred, sample_weight)
        precision = self.precision.result()
        recall = self.recall.result()
        self.f1_score.assign(2 * ((precision * recall) / (precision + recall + 1e-6)))

    def result(self):
        return self.f1_score

    def reset_state(self):
        self.precision.reset_states()
        self.recall.reset_states()
        self.f1_score.assign(0)


def preprocess_for_prediction(text, tokenizer, label_map, max_seq_length=26):
    def tokenize_and_align_labels(sentence, tokenizer, label_map):
        # Split the sentence into words
        words = sentence.split(' ')
        tokenized_input = tokenizer(words, return_tensors="tf", truncation=True, padding=True, max_length=26, is_split_into_words=True)
        tokens = tokenized_input.tokens()
        token_ids = tokenized_input['input_ids'][0].numpy()

        # Initialize the tags as 'O' for each token
        tags = ['O'] * len(words)
        aligned_tags = []

        current_word = 0
        for idx, token in enumerate(tokens):
            if token in ["[CLS]", "[SEP]"]:
                continue

            if token.startswith("##"):
                tag = aligned_tags[-1][1]
            else:
                tag = tags[current_word]
                current_word += 1

            aligned_tags.append((token, tag, token_ids[idx]))

        return aligned_tags

    # Clean and prepare the text
    clean_text = re.sub(r'[^\w\s]', '', text).lower()
    aligned_sentence = tokenize_and_align_labels(clean_text, tokenizer, label_map)

    # Prepare the data for prediction
    sentence_ids = [token_id for token, _, token_id in aligned_sentence]
    padding_length = max_seq_length - len(sentence_ids)

    # Pad the sequences
    sentence_ids.extend([0] * padding_length)
    attention_mask = [1] * len(aligned_sentence) + [0] * padding_length

    # Truncate if necessary
    input_ids = sentence_ids[:max_seq_length]
    attention_mask = attention_mask[:max_seq_length]

    # Convert to the appropriate format for the model
    prediction_input = {
        'input_ids': tf.expand_dims(tf.constant(input_ids, dtype=tf.int32), 0),
        'attention_mask': tf.expand_dims(tf.constant(attention_mask, dtype=tf.int32), 0)
    }

    return prediction_input
