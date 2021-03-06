import time
import argparse

import torch
from transformers import GPT2LMHeadModel, GPT2Tokenizer
from transformers import AdamW

from unlikelihood_util import *


def prepare_training_data(file_path, tokenizer, seq_len):
    train_data = []
    with open(file_path, encoding="utf-8") as f:
        text = f.read()

    block_size = seq_len - tokenizer.num_special_tokens_to_add(pair=False)
    tokenized_text = tokenizer.convert_tokens_to_ids(tokenizer.tokenize(text))

    for i in range(0, len(tokenized_text) - block_size + 1, block_size):  # Truncate in block of block_size
        train_data.append(
            tokenizer.build_inputs_with_special_tokens(tokenized_text[i: i + block_size])
        )

    train_data = torch.tensor(train_data)
    return train_data


def train(epochs, train_data, optimizer, lr, batch_size, save_path, training_type='mle', prefix_length=20, completion_length=100):
    model.train()  # Turn on the train mode

    for epoch in range(1, epochs+1):
        total_loss = 0.
        start_time = time.time()
        for batch, i in enumerate(range(0, train_data.size(0) - 1, batch_size)):
            if training_type == 'mle':
                inputs = train_data[i:i + batch_size, 0:]
                inputs = inputs.to(device)
                optimizer.zero_grad()
                outputs = model(inputs, labels=inputs)
                loss = outputs[0]
                loss.backward()
                optimizer.step()
            elif training_type == 'unlikelihood':
                if torch.rand(1).item() < 0.5:
                    inputs, targets = train_data[i:i + batch_size, 0:-1], train_data[i:i + batch_size, 1:]
                    inputs, targets = inputs.to(device), targets.to(device)
                    optimizer.zero_grad()
                    outputs = model(inputs)
                    logits = outputs[0]
                    loss = token_unlikelihood_loss(logits, targets, padding_idx=tokenizer.eos_token_id)
                    loss.backward()
                    optimizer.step()
                else:
                    prefixes = train_data[i:i+batch_size, 0:prefix_length]
                    prefixes = prefixes.to(device)
                    predicted_tokens, all_logits = generate_completion_greedy_training(model, prefixes, completion_length)
                    loss = sequence_unlikelihood_loss(predicted_tokens, all_logits, 4)

                    loss.backward()
                    optimizer.step()
            else:
                raise Exception('{} training type is not supported'.format(training_type))

            total_loss += loss.item()
            log_interval = (train_data.size(0) // batch_size) // 10
            if batch % log_interval == 0 and batch > 0:
                cur_loss = total_loss / log_interval
                elapsed = time.time() - start_time
                print('| epoch {:3d} | {:5d}/{:5d} batches | '
                      'lr {:02.6f} | ms/batch {:5.2f} | '
                      'loss {:5.2f}'.format(
                        epoch, batch, train_data.size(0) // batch_size, lr,
                        elapsed * 1000 / log_interval,
                        cur_loss))
                total_loss = 0
                start_time = time.time()

        # Save the model
        # TODO: Only save the model if the validation loss is getting better
        torch.save(model, save_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-pre", "--pretrained_path", help="Path to pretrained model", type=str)
    parser.add_argument("-f", "--file", help="Path to training data file", type=str)
    parser.add_argument("-s", "--seq_len", help="The length of each sequence", type=int)
    parser.add_argument("-e", "--epochs", help="Number of epochs", type=int)
    parser.add_argument("-b", "--batch_size", help="Number of batch size", type=int)
    parser.add_argument("-lr", "--learning_rate", help="Learning rate", type=float)
    parser.add_argument("-c", "--completion_length", help="Completion length", type=int)
    parser.add_argument("-p", "--prefix_length", help="Prefix length", type=int)
    parser.add_argument("-t", "--training_type", help="Training type", type=str)
    parser.add_argument("-sa", "--save_path", help="Model save path", type=str)
    args = parser.parse_args()

    # Get tokenizer and model
    tokenizer = GPT2Tokenizer.from_pretrained(args.pretrained_path)
    model = GPT2LMHeadModel.from_pretrained(args.pretrained_path, pad_token_id=tokenizer.eos_token_id)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)

    seq_len = args.seq_len
    train_data = prepare_training_data(args.file, tokenizer, seq_len)

    epochs = args.epochs
    batch_size = args.batch_size
    lr = args.learning_rate
    optimizer = AdamW(model.parameters(), lr=lr)
    completion_length = args.completion_length
    prefix_length = args.prefix_length

    train(epochs=epochs, train_data=train_data, optimizer=optimizer, lr=lr, batch_size=batch_size,
          training_type=args.training_type, prefix_length=prefix_length, completion_length=completion_length,
          save_path=args.save_path)
