import numpy as np
import os
import torch
from torch.utils.data import Dataset


class SNLIData(object):
    def __init__(self, config):
        self.config = config
        self.num_classes = config.num_classes

        self.ngram2idx = dict()
        self.idx2ngram = dict()
        self.ngram2idx['PAD'] = 0
        self.idx2ngram[0] = 'PAD'
        self.ngram2idx['UNK'] = 1
        self.idx2ngram[1] = 'UNK'

        # label num order
        self.label_dict = {'entailment': 0, 'contradiction': 1, 'neutral': 2}

        self.word_set = set()
        self.build_word_set()
        print('#SNLI words', len(self.word_set))

        self.word_embeds = self.get_glove()
        # print('word_count_dict size', len(self.word_count_dict))

        self.unseen_word_dict = dict()
        self.unseen_word_count_dict = dict()

        self.train_data, self.valid_data, self.test_data = self.get_total()

    def build_word_set(self):
        def update_dict(data_path):
            with open(data_path, 'r', newline='', encoding='utf-8') as f:
                for idx, line in enumerate(f):
                    # skip the first line
                    if idx == 0:
                        continue
                    cols = line.rstrip().split('\t')
                    # print(cols)

                    if cols[0] == '-':
                        continue

                    premise = [w for w in cols[1].split(' ')
                               if w != '(' and w != ')']
                    hypothesis = [w for w in cols[2].split(' ')
                                  if w != '(' and w != ')']
                    for w in premise+hypothesis:
                        self.word_set.add(w)

        update_dict(self.config.train_data_path)
        update_dict(self.config.valid_data_path)
        update_dict(self.config.test_data_path)

    def get_glove(self):
        print('Loading GloVe .. {}'.format(self.config.glove_path))
        word2vec = dict()
        with open(self.config.glove_path, 'r', encoding='utf-8') as f:
            for line in f:
                cols = line.split(' ')
                if cols[0] in self.word_set:
                    word2vec[cols[0]] = [float(l) for l in cols[1:]]
        print('SNLI - GloVe intersection size', len(word2vec),
              '({:.1f}%)'.format(100*len(word2vec)/len(self.word_set)))
        return word2vec

    def get_total(self):
        train_data = self.load(self.config.train_data_path)
        valid_data = self.load(self.config.valid_data_path)
        test_data = self.load(self.config.test_data_path)

        print('#unseen_words', len(self.unseen_word_dict))

        # an approximation of the embedding of an unseen words
        for w in self.unseen_word_dict:
            if w in self.unseen_word_count_dict:
                self.unseen_word_dict[w] /= self.unseen_word_count_dict[w]
                self.word_embeds[w] = self.unseen_word_dict[w]
            else:
                print(w)

        return train_data, valid_data, test_data

    def load(self, data_path):
        data = list()

        def approximate_unseen(sentence):
            sentence_len = len(sentence)
            for w_idx, w in enumerate(sentence):
                if w not in self.word_embeds:
                    if w not in self.unseen_word_dict:
                        self.unseen_word_dict[w] = \
                            np.zeros(self.config.embedding_dim)
                    for r in range(-self.config.window_size,
                                   self.config.window_size + 1):
                        if r != 0 and 0 <= w_idx + r < sentence_len \
                                and sentence[w_idx + r] in self.word_embeds:
                            self.unseen_word_dict[w] = \
                                np.add(self.unseen_word_dict[w],
                                       self.word_embeds[sentence[w_idx + r]])
                            if w in self.unseen_word_count_dict:
                                self.unseen_word_count_dict[w] += 1
                            else:
                                self.unseen_word_count_dict[w] = 1

        with open(data_path, 'r', newline='', encoding='utf-8') as f:
            for idx, line in enumerate(f):
                # skip the first line
                if idx == 0:
                    continue

                cols = line.rstrip().split('\t')
                # print(cols)

                if cols[0] == '-':
                    continue

                premise = [w for w in cols[1].split(' ')
                           if w != '(' and w != ')']
                hypothesis = [w for w in cols[2].split(' ')
                              if w != '(' and w != ')']
                y = self.label_dict[cols[0]]

                approximate_unseen(premise)
                approximate_unseen(hypothesis)

                data.append([premise, hypothesis, y])

                if idx + 1 % 10000 == 0:
                    print(idx + 1)

        return data

    def get_dataloaders(self, batch_size=32, shuffle=True, num_workers=4):
        train_loader = torch.utils.data.DataLoader(
            SNLIDataset(self.train_data),
            shuffle=shuffle,
            batch_size=batch_size,
            num_workers=num_workers,
            collate_fn=self.batchify,
            pin_memory=True
        )

        valid_loader = torch.utils.data.DataLoader(
            SNLIDataset(self.valid_data),
            batch_size=batch_size,
            num_workers=num_workers,
            collate_fn=self.batchify,
            pin_memory=True
        )

        test_loader = torch.utils.data.DataLoader(
            SNLIDataset(self.test_data),
            batch_size=batch_size,
            num_workers=num_workers,
            collate_fn=self.batchify,
            pin_memory=True
        )
        return train_loader, valid_loader, test_loader

    @staticmethod
    def batchify(b):
        x = [e[0] for e in b]
        y = [e[2] for e in b]

        x = torch.tensor(x, dtype=torch.int64)
        y = torch.tensor(y, dtype=torch.int64)

        return x, y


class SNLIDataset(Dataset):
    def __init__(self, examples):
        self.examples = examples

    def __len__(self):
        return len(self.examples)

    def __getitem__(self, index):
        return self.examples[index]


if __name__ == '__main__':
    import argparse
    from datetime import datetime
    import pickle
    import pprint

    home_dir = os.path.expanduser('~')
    parser = argparse.ArgumentParser()
    parser.add_argument('--train_data_path', type=str,
                        default='./data/snli_1.0_train.txt')
    parser.add_argument('--valid_data_path', type=str,
                        default='./data/snli_1.0_dev.txt')
    parser.add_argument('--test_data_path', type=str,
                        default='./data/snli_1.0_test.txt')
    parser.add_argument('--glove_path', type=str,
                        default=home_dir + '/common/glove/glove.840B.300d.txt')
    parser.add_argument('--pickle_path', type=str, default='./data/snli.pkl')
    parser.add_argument('--embedding_dim', type=int, default=300)
    parser.add_argument('--window_size', type=int, default=4)
    parser.add_argument('--seed', type=int, default=2018)
    parser.add_argument('--num_classes', type=int, default=3)
    args = parser.parse_args()

    pprint.PrettyPrinter().pprint(args.__dict__)

    import os
    if os.path.exists(args.pickle_path):
        with open(args.pickle_path, 'rb') as f_pkl:
            snlidata = pickle.load(f_pkl)
    else:
        snlidata = SNLIData(args)
    #     with open(args.pickle_path, 'wb') as f_pkl:
    #         pickle.dump(snlidata, f_pkl)
    #
    # tr_loader, _, _ = snlidata.get_dataloaders(batch_size=256, num_workers=4)
    # # print(len(tr_loader.dataset))
    # for batch_idx, batch in enumerate(tr_loader):
    #     if (batch_idx + 1) % 100 == 0 or (batch_idx + 1) == len(tr_loader):
    #         print(datetime.now(), 'batch', batch_idx + 1)
