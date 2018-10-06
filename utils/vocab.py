"""
June 2017 by kyubyong park.
kbpark.linguist@gmail.com.
Modified by Easton.
"""

import codecs
import os
import logging
from argparse import ArgumentParser
from collections import Counter, defaultdict


def load_vocab(path, vocab_size=None):
    vocab = [line.split('\n')[0].split()[0] for line in codecs.open(path, 'r', 'utf-8')]
    vocab = vocab[:vocab_size] if vocab_size else vocab
    id_unk = vocab.index('<unk>')
    token2idx = defaultdict(lambda: id_unk)
    idx2token = defaultdict(lambda: '<unk>')
    token2idx.update({token: idx for idx, token in enumerate(vocab)})
    idx2token.update({idx: token for idx, token in enumerate(vocab)})
    if '<space>' in vocab:
        idx2token[token2idx['<space>']] = ' '
    if '<blk>' in vocab:
        idx2token[token2idx['<blk>']] = ''
    # if '<pad>' in vocab:
    #     idx2token[token2idx['<pad>']] = ''
    if '<unk>' in vocab:
        idx2token[token2idx['<unk>']] = '<UNK>'

    assert len(token2idx) == len(idx2token)

    return token2idx, idx2token


def make_vocab(fpath, fname):
    """Constructs vocabulary.
    Args:
      fpath: A string. Input file path.
      fname: A string. Output file name.

    Writes vocabulary line by line to `fname`.
    """
    word2cnt = Counter()
    for l in codecs.open(fpath, 'r', 'utf-8'):
        words = l.split()
        word2cnt.update(Counter(words))
    word2cnt.update({"<pad>": 10000000000,
                     "<sos>": 1000000000,
                     "<unk>": 100000000})
    with codecs.open(fname, 'w', 'utf-8') as fout:
        for word, cnt in word2cnt.most_common():
            fout.write(u"{}\n".format(word))
    logging.info('Vocab path: {}\t size: {}'.format(fname, len(word2cnt)))


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('--output', type=str, dest='src_vocab')
#    parser.add_argument('--dst_vocab', type=str, dest='dst_vocab')
    parser.add_argument('--input', type=str, dest='src_path')
#    parser.add_argument('--dst_path', type=str, dest='dst_path')
    args = parser.parse_args()
    # Read config
    logging.basicConfig(level=logging.INFO)
    if os.path.exists(args.src_vocab):
        logging.info('Source vocab already exists at {}'.format(args.src_vocab))
    else:
        make_vocab(args.src_path, args.src_vocab)
    logging.info("Done")
