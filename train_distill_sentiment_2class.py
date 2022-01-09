import torch
import torch.nn as nn
import numpy as np
from GPT2 import GPT2Model, GPT2Tokenizer
import json
from GPT2.samplers import RandomSampler
from torch.utils.data import TensorDataset
from tqdm import tqdm
import transformers

import os
os.environ['CUDA_VISIBLE_DEVICES'] = '0'
device = 'cuda' #'cuda'

class GPT2classification(nn.Module):
    def __init__(self):
        super(GPT2classification, self).__init__()
        
        self.GPT2model = GPT2Model(
                            vocab_size=30000,
                            layer_size=12,
                            block_size=1024,
                            embedding_dropout=0.0,
                            embedding_size=768,
                            num_attention_heads=12,
                            attention_dropout=0.0,
                            residual_dropout=0.0)

        self.mlp =  nn.Sequential(
                nn.Linear(30000, 512),
                nn.ReLU(),
                nn.Linear(512, 256),
                nn.ReLU(),
                nn.Linear(256, 2),
            )

    def forward(self, x):
        x = self.GPT2model(x)
        x = x[:,-1]
        x = self.mlp(x)
        return x


def load_data(data_path, data_type, tokenizer, few_shot=False, seq_length=1024):

    filename = os.path.join(data_path, data_type+'.json')
    objs = []
    with open(filename, 'r', encoding='utf-8') as fin:
        for line in fin:
            objs.append(json.loads(line.strip()))

    pad_id = tokenizer.encoder['<pad>']

    all_tokens = []
    all_last_idx = []
    all_labels = []
    
    for _, obj in enumerate(tqdm(objs)):
        sentence = obj['sentence']
        tokenized_sentence = tokenizer.encode(sentence)[:seq_length-20]
        
        if obj['label_desc'] == 'positive':
            label = 1
        else:
            label = 0
        
        all_labels.append(label)

        tokens = tokenized_sentence
        token_length = len(tokens)
        front_pad = [pad_id] * (seq_length - token_length)
        front_pad.extend(tokens)
        tokens = front_pad

        all_last_idx.append(token_length)
        all_tokens.append(tokens)
    
    all_tokens = torch.tensor(all_tokens, dtype=torch.long)
    all_last_idx = torch.tensor(all_last_idx, dtype=torch.long)
    all_labels = torch.tensor(all_labels, dtype=torch.long)
    dataset = TensorDataset(all_tokens, all_last_idx, all_labels)

    return dataset
  
def collect_fcn(batch):
    bs = len(batch)
    batch_tokens = []
    batch_idx = []
    batch_labels = []
    for i in range(bs):
        batch_tokens.append(batch[i][0])
        batch_idx.append(batch[i][1])
        batch_labels.append(batch[i][2])
    batch_tokens = torch.stack(batch_tokens)
    batch_idx = torch.stack(batch_idx)
    batch_labels = torch.stack(batch_labels)

    return batch_tokens, batch_idx, batch_labels

def train(model, train_dataloader):
    model.mlp.train()
    bar = tqdm(train_dataloader)
    num = 0
    for batch in bar:
        num = num + batch_size
        token, last_idx, label = (x.to(device) for x in batch)
        output = model(token)
        loss = loss_fcn(output, label)
        # bar.set_description("train loss %s" % str(loss.item()))
        loss.backward()
        if num == 32:
            optimizer.step()
            optimizer.zero_grad()
            num = 0

def eval(model, test_datalodar):
    model.mlp.eval()
    bar = tqdm(test_datalodar)
    num = 0
    loss_sum = 0
    for batch in bar:
        num = num + batch_size
        token, last_idx, label = (x.to(device) for x in batch)
        output = model(token)
        loss = loss_fcn(output, label)
        loss_sum = loss_sum + loss.item()
        # bar.set_description("eval loss %s" % str(loss.item()))
    print('eval loss', loss_sum/num)


state_dict = torch.load('../models/model_pretrain_distill.pth', map_location='cpu')

tokenizer = GPT2Tokenizer(
    'GPT2/bpe/vocab.json',
    'GPT2/bpe/chinese_vocab.model',
    max_len=512)

batch_size = 1

train_set = load_data('../dataset/csdn_processed', 'train_fincpm', tokenizer)
train_sampler = RandomSampler(train_set)
train_dataloader = torch.utils.data.DataLoader(train_set,
                                                batch_size = batch_size,
                                                sampler=train_sampler,
                                                num_workers=0,
                                                collate_fn = collect_fcn,
                                                pin_memory=True)

test_set = load_data('../dataset/csdn_processed', 'test_fincpm', tokenizer)
test_sampler = RandomSampler(test_set)                                               
test_dataloader = torch.utils.data.DataLoader(test_set,
                                                batch_size = batch_size,
                                                sampler=test_sampler,
                                                num_workers=0,
                                                collate_fn = collect_fcn,
                                                pin_memory=True)

model = GPT2classification()
model.GPT2model.load_state_dict(state_dict)
model.GPT2model.eval()
model.to(device)

# optimizer = transformers.AdamW(model.mlp.parameters(), lr=1e-4, eps=1.0e-6)
optimizer = transformers.AdamW(model.parameters(), lr=1e-6, eps=1.0e-8)

loss_fcn = nn.CrossEntropyLoss()
loss_fcn.to(device)

eval(model, test_dataloader)
for epoch in range(10):
    train(model, train_dataloader)
    eval(model, test_dataloader)
    torch.save(model, "../models/financial_sentiment_" + str(epoch+1) + ".pth")

