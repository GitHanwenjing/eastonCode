'''@file model.py
contains de Model class
During the training , using greadysearch decoder, there is loss.
During the dev/infer, using beamsearch decoder, there is no logits, therefor loss, only predsself.
because we cannot access label during the dev set and need to depend on last time decision.

so, there is only infer and training
'''

import tensorflow as tf
import logging
from collections import namedtuple

from tfSeq2SeqModels.seq2seqModel import Seq2SeqModel
from tfModels.tools import choose_device, smoothing_cross_entropy


class Transformer(Seq2SeqModel):
    '''a general class for an encoder decoder system
    '''

    def __init__(self, tensor_global_step, encoder, decoder, is_train, args,
                 batch=None, embed_table_encoder=None, embed_table_decoder=None,
                 name='transformer'):
        '''Model constructor

        Args:
        '''
        self.name = name
        self.size_embedding = args.model.decoder.size_embedding
        self.embedding_tabel = self.get_embedding(
            embed_table=None,
            size_input=args.dim_output,
            size_embedding=self.size_embedding)
        super().__init__(tensor_global_step, encoder, decoder, is_train, args,
                         batch,
                         embed_table_encoder=None,
                         embed_table_decoder=None,
                         name=name)

    def build_single_graph(self, id_gpu, name_gpu, tensors_input):

        with tf.device(lambda op: choose_device(op, name_gpu, self.center_device)):
            encoder = self.gen_encoder(
                is_train=self.is_train,
                embed_table=None,
                args=self.args)
            decoder = self.gen_decoder(
                is_train=self.is_train,
                embed_table=self.embedding_tabel,
                global_step=self.global_step,
                args=self.args)

            _, (len_encoded, encoded) = encoder(
                features=tensors_input.feature_splits[id_gpu],
                len_feas=tensors_input.len_fea_splits[id_gpu])

            with tf.variable_scope(decoder.name or 'decoder'):
                decoder_input = decoder.build_input(
                    id_gpu=id_gpu,
                    tensors_input=tensors_input)
                
                if (not self.is_train) or (self.args.model.loss_type == 'OCD'):
                    # infer phrases
                    if self.args.dirs.lm_checkpoint and self.args.beam_size>1:
                        logging.info('beam search with language model ...')
                        logits, preds, len_decoded = decoder.beam_decode_rerank(
                            encoded,
                            len_encoded)
                    else:
                        logging.info('gready search ...')
                        logits, preds, len_decoded = decoder.decoder_with_caching(
                            encoded,
                            len_encoded)
                else:
                    logging.info('teacher-forcing training ...')
                    decoder_input_labels = decoder_input.input_labels * tf.sequence_mask(
                        decoder_input.len_labels,
                        maxlen=tf.shape(decoder_input.input_labels)[1],
                        dtype=tf.int32)
                    logits, preds, _ = decoder.decode(
                        encoded=encoded,
                        len_encoded=len_encoded,
                        decoder_input=decoder_input_labels)

            if self.is_train:
                if self.args.model.loss_type == 'OCD':
                    """
                    constrain the max decode length for ocd training since model
                    will decode to that long at beginning. Recommend 30.
                    """
                    loss, _ = self.ocd_loss(
                        logits=logits,
                        len_logits=len_decoded,
                        labels=tensors_input.label_splits[id_gpu],
                        preds=preds)
                    # loss = self.ce_loss(
                    #     logits=logits,
                    #     labels=preds,
                    #     len_labels=len_decoded)
                elif self.args.model.loss_type == 'CE':
                    # logits = tf.Print(logits, [preds[:, 0]], message='preds: ', summarize=1000)
                    loss = self.ce_loss(
                        logits=logits,
                        labels=decoder_input.output_labels,
                        len_labels=decoder_input.len_labels)

                elif self.args.model.loss_type == 'Premium_CE':
                    table_targets_distributions = tf.nn.softmax(tf.constant(self.args.table_targets))
                    loss = self.premium_ce_loss(
                        logits=logits,
                        labels=tensors_input.label_splits[id_gpu],
                        table_targets_distributions=table_targets_distributions,
                        len_labels=tensors_input.len_label_splits[id_gpu])
                else:
                    raise NotImplemented('NOT found loss type!')

                with tf.name_scope("gradients"):
                    assert loss.get_shape().ndims == 1
                    loss = tf.reduce_mean(loss)
                    gradients = self.optimizer.compute_gradients(loss)

        self.__class__.num_Model += 1
        logging.info('\tbuild {} on {} succesfully! total model number: {}'.format(
            self.__class__.__name__, name_gpu, self.__class__.num_Model))

        if self.is_train:
            # no_op is preserved for debug info to pass
            # return loss, gradients, tf.no_op()
            return loss, gradients, [tf.no_op(), preds, tensors_input.label_splits[id_gpu]]
        else:
            return logits, len_decoded, preds
