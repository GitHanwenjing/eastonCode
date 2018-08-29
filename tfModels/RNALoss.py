import tensorflow as tf

from tfModels.math_tf import sum_log, batch_pad


LOG_ZERO = tf.convert_to_tensor(-1e29) # can not be too small in tf
LOG_ONE = tf.convert_to_tensor(0.0)


def rna_loss(logits, labels, len_logits, len_labels):

    def right_shift_rows(p, shift, pad):
        assert type(shift) is int
        return tf.concat([tf.ones((tf.shape(p)[0], shift), dtype=tf.float32)*pad,
                          p[:, :-shift]], axis=1)

    def step(forward_vars, probs):
        add_2 = right_shift_rows(forward_vars, 1, LOG_ZERO)
        return probs + sum_log(forward_vars, add_2)

    blank = tf.shape(logits)[1]
    size_batch = tf.shape(logits)[0]

    logits_log = tf.log(logits)
    labels_blanked = batch_pad(labels, 1, blank, direct='head')
    len_blanked = tf.shape(labels_blanked)[1]

    seqs_probs = activations2seqs_probs(logits_log, labels_blanked)

    seqs_probs_timeMajor = tf.transpose(seqs_probs, ((1, 0, 2)))

    tail = tf.ones((size_batch, len_blanked-1), dtype=tf.float32) * LOG_ZERO
    head = tf.ones((size_batch, 1), dtype=tf.float32) * LOG_ONE
    forward_vars_init = tf.concat([head, tail], -1)

    forward_vars = tf.scan(step, seqs_probs_timeMajor, forward_vars_init)

    indices_batch = tf.range(size_batch)
    indices_time = len_logits-1
    final_state = tf.gather_nd(forward_vars, tf.stack([indices_time, indices_batch, len_labels+1], -1))

    return -final_state


def activations2seqs_probs(logits, labels):
    """
    [[[ 0.06390443  0.21124858  0.27323887  0.06870235  0.0361254   0.18184413 0.16493624]
      [ 0.03309247  0.22866108  0.24390638  0.09699597  0.31895462  0.0094893  0.06890021]
      [ 0.218104    0.19992557  0.18245131  0.08503348  0.14903535  0.08424043 0.08120984]
      [ 0.12094152  0.19162472  0.01473646  0.28045061  0.24246305  0.05206269 0.09772094]
      [ 0.1333387   0.00550838  0.00301669  0.21745861  0.20803985  0.41317442 0.01946335]
      [ 0.16468227  0.1980699   0.1906545   0.18963251  0.19860937  0.04377724 0.01457421]]

     [[ 0.08034842  0.22671944  0.05799633  0.36814645  0.11307441  0.04468023 0.10903471]
      [ 0.09742457  0.12959763  0.09435383  0.21889204  0.15113123  0.10219457 0.20640612]
      [ 0.45033529  0.09091417  0.15333208  0.07939558  0.08649316  0.12298585 0.01654384]
      [ 0.02512238  0.22079203  0.19664364  0.11906379  0.07816055  0.22538587 0.13483174]
      [ 0.17928453  0.06065261  0.41153005  0.1172041   0.11880313  0.07113197 0.04139363]
      [ 0.15882358  0.1235788   0.23376776  0.20510435  0.00279306  0.05294827 0.22298418]]]

     np.array([[0,1,1,3],
               [0,2,2,0]])
     convert to:

     array([[[ 0.06390443,  0.21124858,  0.21124858,  0.06870235],
             [ 0.03309247,  0.22866108,  0.22866108,  0.09699597],
             [ 0.218104  ,  0.19992557,  0.19992557,  0.08503348],
             [ 0.12094152,  0.19162472,  0.19162472,  0.28045061],
             [ 0.1333387 ,  0.00550838,  0.00550838,  0.21745861],
             [ 0.16468227,  0.1980699 ,  0.1980699 ,  0.18963251]],

            [[ 0.08034842,  0.05799633,  0.05799633,  0.08034842],
             [ 0.09742457,  0.09435383,  0.09435383,  0.09742457],
             [ 0.45033529,  0.15333208,  0.15333208,  0.45033529],
             [ 0.02512238,  0.19664364,  0.19664364,  0.02512238],
             [ 0.17928453,  0.41153005,  0.41153005,  0.17928453],
             [ 0.15882358,  0.23376776,  0.23376776,  0.15882358]]], dtype=float32)
    """
    size_batch, len_time= tf.shape(logits)[0], tf.shape(logits)[1]
    len_seq = tf.shape(labels)[1]
    # size_batch, len_time, num_classes = logits.get_shape()
    # size_batch, len_seq = labels.get_shape()

    # Is there any auto broadcast mechanism which can simplify the caode here??
    m = tf.tile(tf.expand_dims(tf.range(len_time, dtype=tf.int32), 1), [1, len_seq])
    index_time = tf.tile(tf.expand_dims(m, 0), [size_batch, 1, 1])
    index_seqs_labels = tf.tile(tf.expand_dims(labels, 1), [1, len_time, 1])
    n = tf.expand_dims(tf.expand_dims(tf.range(size_batch, dtype=tf.int32), 1), 1)
    index_batch = tf.tile(n, [1, len_time, len_seq])
    # if not index_time.get_shape() == index_seqs_labels.get_shape() == index_batch.get_shape():
    #     raise Exception(index_seqs_labels.get_shape(), index_batch.get_shape())
    seqs_probs = tf.gather_nd(logits, tf.stack((index_batch, index_time, index_seqs_labels), -1))

    return seqs_probs


def testActivations2seqs_probs():
    size_batch = tf.convert_to_tensor(2)
    len_seq = tf.convert_to_tensor(8)
    len_labels = tf.convert_to_tensor(4)
    labels = tf.constant([[0, 1, 1, 0], [0, 2, 1, 3]], dtype=tf.int32)

    activations = tf.reshape(tf.range(size_batch*len_seq*len_labels),
                             (size_batch, len_seq, len_labels))
    probs = activations2seqs_probs(activations, labels)

    with tf.Session() as sess:
        sess.run(tf.global_variables_initializer())
        print(sess.run(activations))
        print(sess.run(labels))
        print(sess.run(probs))


def testCost():
    num_class = 5
    num_lables = 4
    inputs = tf.constant(
        [[[0.633766, 0.221185, 0.0917319],
          [0.111121, 0.588392, 0.278779],
          [0.0357786, 0.633813, 0.321418],
          [0.0663296, 0.643849, 0.280111],
          [0.458235, 0.396634, 0.123377],
          [0.633766, 0.221185, 0.0917319],
          [0.111121, 0.588392, 0.278779],
          [0.0357786, 0.633813, 0.321418],
          [0.0663296, 0.643849, 0.280111],
          [0.458235, 0.396634, 0.123377]],
         [[0.30176, 0.28562, 0.0831517],
          [0.24082, 0.397533, 0.0557226],
          [0.230246, 0.450868, 0.0389607],
          [0.280884, 0.429522, 0.0326593],
          [0.423286, 0.315517, 0.0338439],
          [0.30176, 0.28562, 0.0831517],
          [0.24082, 0.397533, 0.0557226],
          [0.230246, 0.450868, 0.0389607],
          [0, 0, 0],
          [0, 0, 0]]],
        dtype=tf.float32)

    labels = tf.constant([[1, 1, 2, 1],
                               [1, 2, 0, 0]], dtype=tf.int32)

    len_logits = tf.constant([10, 8], dtype=tf.int32)
    len_labels = tf.constant([4, 2], dtype=tf.int32)

    loss = ctc_loss(inputs, labels, len_logits, len_labels)
    with tf.Session() as sess:
        sess.run(tf.global_variables_initializer())

        print(sess.run(loss))


if __name__ == '__main__':
    # testActivations2seqs_probs()
    testCost()
