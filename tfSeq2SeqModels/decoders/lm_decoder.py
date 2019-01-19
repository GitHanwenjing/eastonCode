'''@file asr_decoder.py
contains the EDDecoder class'''
import tensorflow as tf
from tensorflow.python.util import nest

class LM_Decoder(object):
    '''a general decoder for an encoder decoder system
    converts the high level features into output logits
    '''
    def __init__(self, args, is_train, embed_table=None, name=None):
        '''EDDecoder constructor
        Args:
            conf: the decoder configuration as a configparser
            outputs: the name of the outputs of the model
            constraint: the constraint for the variables

            self.start_token is used in the infer_graph, for auto feed the first
            <sos> tokens to the decoder, while in the train_graph, you need to
            pad the <sos> for the decoder input manually!
            Also, in the infer_graph, decoder should know when to stop, so the
            decoder need to specify the <eos> in the helper or BeamSearchDecoder.
        '''
        self.args = args
        self.name = name
        self.is_train = is_train
        self.num_cell_units = args.model.decoder.num_cell_units
        self.dropout = args.model.decoder.dropout
        self.keep_prob = 1 - args.model.decoder.dropout
        self.cell_type = args.model.decoder.cell_type
        self.num_layers = args.model.decoder.num_layers
        self.init_scale = args.model.decoder.init_scale
        self.rnn_mode = args.model.decoder.rnn_mode
        self.size_embedding = args.model.decoder.size_embedding
        self.dim_output = args.dim_output
        self.embed_table = embed_table

        self.cell = self.make_multi_cell(args.num_layers)

    def __call__(self, inputs, len_inputs):
        '''
        Create the variables and do the forward computation to decode an entire
        sequence
        Inputs:
            inputs.set_shape([None, None, self.size_embedding])
        Returns:
            - the output logits of the decoder as a dictionary of
                [batch_size x time x ...] tensors
            - the logit sequence_lengths as a dictionary of [batch_size] vectors
            - the final state of the decoder as a possibly nested tupple
                of [batch_size x ... ] tensors
        '''
        with tf.variable_scope(self.name or 'decoder'):
            self.scope = tf.get_variable_scope()
            if self.is_train and self.keep_prob < 1.0:
                inputs = tf.nn.dropout(inputs, self.keep_prob)

            hidden_output, final_state = tf.nn.dynamic_rnn(
                cell=self.cell,
                inputs=inputs,
                sequence_length=len_inputs,
                dtype=tf.float32)

        return hidden_output, final_state

    def _get_lstm_cell(self):
        if self.rnn_mode == 'BASIC':
            return tf.contrib.rnn.BasicLSTMCell(
                self.num_cell_units, forget_bias=0.0, state_is_tuple=True,
                reuse=not self.is_train)
        if self.rnn_mode == 'BLOCK':
            return tf.contrib.rnn.LSTMBlockCell(
                self.num_cell_units, forget_bias=0.0)
        if self.rnn_mode == 'CUDNN':
            return tf.contrib.cudnn_rnn.CudnnCompatibleLSTMCell(self.num_cell_units)
        raise ValueError("rnn_mode %s not supported" % self.rnn_mode)

    def make_cell(self):
        cell = self._get_lstm_cell()
        if self.is_train and self.keep_prob < 1:
            cell = tf.contrib.rnn.DropoutWrapper(
                cell, output_keep_prob=self.keep_prob)
        return cell

    def make_multi_cell(self, num_layers):
        list_cells = [self.make_cell() for _ in range(self.num_layers-1)]
        cell_proj = tf.contrib.rnn.OutputProjectionWrapper(
            cell=self.make_cell(),
            output_size=self.dim_output)
        list_cells.append(cell_proj)
        multi_cell = tf.contrib.rnn.MultiRNNCell(list_cells, state_is_tuple=True)

        return multi_cell

    def embedding(self, ids):
        if self.embed_table:
            embeded = tf.nn.embedding_lookup(self.embed_table, ids)
        else:
            embeded = tf.one_hot(ids, self.args.dim_output, dtype=tf.float32)

        return embeded

    def zero_state(self, batch_size, dtype=tf.float32):
        return self.cell.zero_state(batch_size, dtype=tf.float32)

    def forward(self, input, state, stop_gradient=False, list_state=False):
        if input.get_shape().ndims <2:
            input = tf.nn.embedding_lookup(self.embed_table, input)
        output, state = tf.contrib.legacy_seq2seq.rnn_decoder(
            decoder_inputs=[input],
            initial_state=state,
            cell=self.cell)

        if stop_gradient:
            output = tf.stop_gradient(output)

        if list_state:
            list_cells = []
            for cell in state:
                cell = tf.nn.rnn_cell.LSTMStateTuple(tf.stop_gradient(cell[0]), tf.stop_gradient(cell[1]))
                list_cells.append(cell)
            state = tuple(list_cells)

        return output[0], state

    def sample(self, token_init=None, state_init=None, max_length=50):
        def step(i, preds, state_decoder):
            output, state_output = self.forward(preds[:, -1], state_decoder)
            sampled_id = tf.distributions.Categorical(logits=output).sample()
            sampled_ids = tf.concat([preds, tf.expand_dims(sampled_id, 1)], axis=1)

            return i+1, sampled_ids, state_output

        num_samples = tf.placeholder(tf.int32, [], name='num_samples')

        if token_init is None:
            token_init = tf.ones([num_samples, 1], dtype=tf.int32) * self.args.sos_idx
        if state_init is None:
            state_init = self.zero_state(num_samples)

        _, sampled, _ = tf.while_loop(
            cond=lambda i, *_: tf.less(i, max_length),
            body=step,
            loop_vars=[0, token_init, state_init],
            shape_invariants=[tf.TensorShape([]),
                              tf.TensorShape([None, None]),
                              nest.map_structure(lambda t: tf.TensorShape(t.shape), state_init)
                              ]
            )
        return sampled, num_samples