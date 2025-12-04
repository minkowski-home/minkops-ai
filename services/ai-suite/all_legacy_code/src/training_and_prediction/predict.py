import numpy as np
from all_legacy_code.src.preprocess import text_prep
from all_legacy_code.src.preprocess import image_prep, ner_prep


def predict_intent(text, model, tokenizer):
    dic = {0: 'order', 1: 'complain about', 2: 'get info about'}
    preprocessed_text = text_prep.preprocess_for_intent(text, intents=None, tokenizer=tokenizer, train=False)
    probas = model.predict(preprocessed_text)
    return dic[np.argmax(probas)]


def predict_entities(text: str, model, tokenizer, label_map: dict, max_seq_length: int):
    # Preprocess the text
    prediction_input = ner_prep.preprocess_for_prediction(text, tokenizer, label_map, max_seq_length)

    # Predict using the model
    prediction_output = model.predict(prediction_input)

    # Extract logits and get the highest probability labels
    logits = prediction_output[0]
    label_indices = np.argmax(logits, axis=-1)

    # Reverse the label_map to get labels from indices
    reverse_label_map = {v: k for k, v in label_map.items()}

    # Tokens and labels
    tokens = tokenizer.tokenize(tokenizer.decode(prediction_input['input_ids'][0]))
    predicted_labels = [reverse_label_map[idx] for idx in label_indices[0][:len(tokens)]]

    tokens = tokenizer.tokenize(tokenizer.decode(prediction_input['input_ids'][0]))
    predicted_labels = [reverse_label_map[idx] for idx in label_indices[0][:len(tokens)]]

    word_label_pairs = []
    current_word = ''
    current_label = None

    for token, label in zip(tokens, predicted_labels):
        if token != '[PAD]':
            if token.startswith('##'):
                current_word += token[2:]
            else:
                if current_word:
                    # Only add non-'O' labels
                    if current_label != 'O':
                        word_label_pairs.append((current_word, current_label))
                current_word = token
                current_label = label

    # Add the last word if it's not empty and its label is not 'O'
    if current_word and current_label != 'O':
        word_label_pairs.append((current_word, current_label))

    return word_label_pairs


def generate_text(prompt, tokenizer, model, max_length=50):
    # Preprocess the prompt for inference
    preprocessed_input = text_prep.preprocess_for_gpt2(prompt, tokenizer, train=False)

    # Extract input_ids and attention_mask from the preprocessed input
    input_ids = preprocessed_input['input_ids']
    attention_mask = preprocessed_input['attention_mask']

    # Generate text using both input_ids and attention_mask
    output = model.generate(input_ids, attention_mask=attention_mask, max_length=max_length,
                            num_return_sequences=1, no_repeat_ngram_size=2)

    # Decode the generated text
    return tokenizer.decode(output[0], skip_special_tokens=True)


def chat_with_assistant(user_prompt, messages, client, model, fresh=False):
    if fresh:
        messages = []

    # Append user's message
    messages.append({"role": "user", "content": user_prompt})

    # Get response from the model
    response = client.chat.completions.create(
        model=model,
        messages=messages
    )

    assistant_message = response.choices[0].message.content

    # Append assistant's response
    messages.append({"role": "assistant", "content": assistant_message})

    return assistant_message, messages


def predict_age_gender_race(frame, model):
    prepped_frame = image_prep.preprocess_for_prediction(frame)
    age, gender, race = model.predict(prepped_frame)
    age, gender, race = np.round(age[0][0],2), int(np.round(gender[0][0])), np.argmax(race[0], axis=-1)
    return age, gender, race
