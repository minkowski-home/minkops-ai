import tensorflow as tf
from transformers import TFDistilBertModel, BertConfig, TFBertForTokenClassification
from tensorflow import keras
from all_legacy_code.src.preprocess import ner_prep


def create_intent_classifier(compile=False, init_lr=0.00001, dropout=0.3):
    # Define input layers
    input_ids = tf.keras.layers.Input(shape=(40,), dtype=tf.int32, name='input_ids')
    attention_mask = tf.keras.layers.Input(shape=(40,), dtype=tf.int32, name='attention_mask')

    # Load the DistilBERT model
    # Ensure that you have already loaded or downloaded the model as needed
    model = TFDistilBertModel.from_pretrained('distilbert-base-uncased')

    # Use the DistilBERT model
    distilbert_output = model(input_ids, attention_mask=attention_mask)[0]

    # Get the output for the [CLS] token (first token)
    pooled_output = distilbert_output[:, 0]

    # Additional dropout layer for regularization
    dropout = tf.keras.layers.Dropout(dropout)(pooled_output)

    # Classifier layer for your 3 classes
    classifier = tf.keras.layers.Dense(3, activation='softmax')(dropout)

    # Final model
    final_model = tf.keras.models.Model(inputs=[input_ids, attention_mask], outputs=classifier)

    if compile:
        optimizer = keras.optimizers.Adam(learning_rate=init_lr)
        final_model.compile(optimizer=optimizer, loss='categorical_crossentropy',
                            metrics=['accuracy', keras.metrics.Precision(), keras.metrics.Recall(), ner_prep.F1Score()])

    return final_model


def trained_intent_classifier():
    model = create_intent_classifier()
    model.load_weights('resources/bert/saved/ir_trained_weights.h5')
    return model


def create_entity_classifier(compile=False, lr=5e-5):
    num_labels = 15
    config = BertConfig.from_pretrained('bert-base-uncased', num_labels=num_labels)
    model = TFBertForTokenClassification.from_pretrained('bert-base-uncased', config=config)

    if compile:
        optimizer = keras.optimizers.Adam(learning_rate=lr)
        loss = keras.losses.CategoricalCrossentropy(from_logits=True)
        metrics = [keras.metrics.Precision(), keras.metrics.Recall(), ner_prep.F1Score()]
        model.compile(optimizer, loss=loss, metrics=metrics)

    return model


def trained_entity_classifier():
    model = create_entity_classifier()
    model.load_weights('resources/bert/saved/ner_trained_weights.h5')
    return model


def create_cnn_model(compile=False, lr=0.001):
    # Input layer for images
    input_img = keras.layers.Input(shape=(200, 200, 3))

    # Convolutional layers with Batch Normalization and Dropout for regularization
    x = keras.layers.Conv2D(32, (3, 3), activation='relu')(input_img)
    x = keras.layers.BatchNormalization()(x)
    x = keras.layers.MaxPooling2D((2, 2))(x)
    x = keras.layers.Dropout(0.4)(x)

    x = keras.layers.Conv2D(64, (3, 3), activation='relu')(x)
    x = keras.layers.BatchNormalization()(x)
    x = keras.layers.MaxPooling2D((2, 2))(x)
    x = keras.layers.Dropout(0.4)(x)

    x = keras.layers.Conv2D(128, (3, 3), activation='relu')(x)
    x = keras.layers.BatchNormalization()(x)
    x = keras.layers.MaxPooling2D((2, 2))(x)
    x = keras.layers.Dropout(0.4)(x)

    # Flatten the output for the dense layers
    x = keras.layers.Flatten()(x)

    # Dense layers for different outputs with Dropout
    # Age prediction (regression)
    age_x = keras.layers.Dense(128, activation='relu')(x)
    age_x = keras.layers.Dropout(0.5)(age_x)
    age_output = keras.layers.Dense(1, name='age_output')(age_x)

    # Gender prediction (binary classification)
    gender_x = keras.layers.Dense(128, activation='relu')(x)
    gender_x = keras.layers.Dropout(0.5)(gender_x)
    gender_output = keras.layers.Dense(1, activation='sigmoid', name='gender_output')(gender_x)

    # Race prediction (multi-class classification)
    race_x = keras.layers.Dense(128, activation='relu')(x)
    race_x = keras.layers.Dropout(0.5)(race_x)
    race_output = keras.layers.Dense(5, activation='softmax', name='race_output')(race_x)

    # Create the model
    model = keras.models.Model(inputs=input_img, outputs=[age_output, gender_output, race_output])

    if compile:
        optimizer = keras.optimizers.Adam(learning_rate=lr)
        loss_weights = {'age_output': 0.05,
                        'gender_output': 0.75,
                        'race_output': 1.0}
        model.compile(optimizer=optimizer,
                      loss={'age_output': 'mse',
                            'gender_output': 'binary_crossentropy',
                            'race_output': 'categorical_crossentropy'},
                      loss_weights=loss_weights,
                      metrics={'age_output': ['mae'],
                               'gender_output': ['accuracy'],
                               'race_output': ['accuracy']})

    return model


def trained_cnn():
    model = keras.models.load_model('resources/age_gender/saved/age_gender_best_yet.h5')
    return model

def create_cnn_vgg(compile=False):
    # Define input tensor
    input_tensor = keras.Input(shape=(200, 200, 3))

    # Block 1
    x = keras.layers.Conv2D(64, (3, 3), padding='same')(input_tensor)
    x = keras.layers.BatchNormalization()(x)
    x = keras.layers.Activation('relu')(x)
    x = keras.layers.Conv2D(64, (3, 3), padding='same')(x)
    x = keras.layers.BatchNormalization()(x)
    x = keras.layers.Activation('relu')(x)
    x = keras.layers.MaxPooling2D((2, 2), strides=(2, 2))(x)

    # Block 2
    x = keras.layers.Conv2D(128, (3, 3), padding='same')(x)
    x = keras.layers.BatchNormalization()(x)
    x = keras.layers.Activation('relu')(x)
    x = keras.layers.Conv2D(128, (3, 3), padding='same')(x)
    x = keras.layers.BatchNormalization()(x)
    x = keras.layers.Activation('relu')(x)
    x = keras.layers.MaxPooling2D((2, 2), strides=(2, 2))(x)

    # Block 3
    x = keras.layers.Conv2D(256, (3, 3), padding='same')(x)
    x = keras.layers.BatchNormalization()(x)
    x = keras.layers.Activation('relu')(x)
    x = keras.layers.Conv2D(256, (3, 3), padding='same')(x)
    x = keras.layers.BatchNormalization()(x)
    x = keras.layers.Activation('relu')(x)
    x = keras.layers.Conv2D(256, (3, 3), padding='same')(x)
    x = keras.layers.BatchNormalization()(x)
    x = keras.layers.Activation('relu')(x)
    x = keras.layers.MaxPooling2D((2, 2), strides=(2, 2))(x)
    x = keras.layers.Dropout(0.4)(x)

    # Block 4
    x = keras.layers.Conv2D(512, (3, 3), padding='same')(x)
    x = keras.layers.BatchNormalization()(x)
    x = keras.layers.Activation('relu')(x)
    x = keras.layers.Conv2D(512, (3, 3), padding='same')(x)
    x = keras.layers.BatchNormalization()(x)
    x = keras.layers.Activation('relu')(x)
    x = keras.layers.Conv2D(512, (3, 3), padding='same')(x)
    x = keras.layers.BatchNormalization()(x)
    x = keras.layers.Activation('relu')(x)
    x = keras.layers.MaxPooling2D((2, 2), strides=(2, 2))(x)
    x = keras.layers.Dropout(0.5)(x)

    # # Block 5
    # x = keras.layers.Conv2D(512, (3, 3), padding='same')(x)
    # x = keras.layers.BatchNormalization()(x)
    # x = keras.layers.Activation('relu')(x)
    # x = keras.layers.Conv2D(512, (3, 3), padding='same')(x)
    # x = keras.layers.BatchNormalization()(x)
    # x = keras.layers.Activation('relu')(x)
    # x = keras.layers.Conv2D(512, (3, 3), padding='same')(x)
    # x = keras.layers.BatchNormalization()(x)
    # x = keras.layers.Activation('relu')(x)
    # x = keras.layers.MaxPooling2D((2, 2), strides=(2, 2))(x)
    # x = keras.layers.Dropout(0.4)(x)

    # Flatten for Dense layers
    x = keras.layers.Flatten()(x)

    # Common Dense layer
    x = keras.layers.Dense(4096, activation='relu')(x)
    x = keras.layers.Dropout(0.5)(x)

    # Separate Dense layers for each output
    x_age = keras.layers.Dense(128, activation='relu')(x)
    x_gender = keras.layers.Dense(128, activation='relu')(x)
    x_race = keras.layers.Dense(128, activation='relu')(x)

    # Output layers for each task
    age_output = keras.layers.Dense(1, name='age_output')(x_age)  # Regression (age)
    gender_output = keras.layers.Dense(1, activation='sigmoid', name='gender_output')(
        x_gender)  # Binary classification (gender)
    race_output = keras.layers.Dense(5, activation='softmax', name='race_output')(
        x_race)  # Multi-class classification (race)

    # Create model
    model = keras.Model(inputs=input_tensor, outputs=[age_output, gender_output, race_output])

    # Compile model
    if compile:
        model.compile(optimizer='adam',
                      loss={'age_output': 'mse', 'gender_output': 'binary_crossentropy',
                            'race_output': 'categorical_crossentropy'},
                      metrics={'age_output': ['mae'], 'gender_output': ['accuracy'], 'race_output': ['accuracy']})
    return model


def trained_cnn_model():
    pass
