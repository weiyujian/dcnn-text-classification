import tensorflow as tf
import numpy as np
from util import highway
import pdb
class TextCNN(object):
    """
    A DCNN for text classification.
    Uses an embedding layer, followed by a cnn, folding_k_max_pooling, cnn, folding_k_max_pooling and softmax layer.
    """
    def __init__(
      self, sequence_length, num_classes, vocab_size,
      embedding_size, filter_sizes=[7,5], num_filters=[8,14], top_k=6, k1=12, l2_reg_lambda=0.0):

        # Placeholders for input, output and dropout
        self.input_x = tf.placeholder(tf.int32, [None, sequence_length], name="input_x")
        self.input_y = tf.placeholder(tf.float32, [None, num_classes], name="input_y")
        self.dropout_keep_prob = tf.placeholder(tf.float32, name="dropout_keep_prob")
        self.is_training = tf.placeholder(tf.bool, name="is_training")
        self.use_region_emb = False
        self.fc_hidden_size = 2048
        self.use_dialate_conv =  False
        # Keeping track of l2 regularization loss (optional)
        l2_loss = tf.constant(0.0)

        # Embedding layer
        with tf.device('/cpu:0'), tf.name_scope("embedding"):
            self.W = tf.Variable(
                tf.random_uniform([vocab_size, embedding_size], -1.0, 1.0),
                name="W")
            if self.use_region_emb:
                self.region_size = 5
                self.region_radius = self.region_size / 2
                self.k_matrix_embedding = tf.Variable(tf.random_uniform([vocab_size, self.region_size, embedding_size], -1.0, 1.0), name="k_matrix")
                self.embedded_chars = self.region_embedding(self.input_x)
                sequence_length = int(self.embedded_chars.shape[1])
            else:
                self.embedded_chars = tf.nn.embedding_lookup(self.W, self.input_x)
            self.embedded_chars_expanded = tf.expand_dims(self.embedded_chars, -1)

        # Create a dcnn + dynamic k max pooling layer
        with tf.name_scope("conv_pooling_layer"):
            if self.use_dialate_conv:
                #first layer
                W1 = tf.Variable(tf.truncated_normal([filter_sizes[0], 2, 1, num_filters[0]], stddev=0.1), name="W1")
                b1 = tf.Variable(tf.constant(0.1, shape=[num_filters[0]]), name="b1")
                conv1 = self.dialate_conv_layer(self.embedded_chars_expanded, W1, b1, rate=2, scope="dialate_conv_1")
                conv_bn1 = tf.layers.batch_normalization(conv1, training=self.is_training)
                pooled1 = self.folding_k_max_pooling(conv_bn1, k1)
            
                #second layer
                W2 = tf.Variable(tf.truncated_normal([filter_sizes[1], 3, num_filters[0], num_filters[1]], stddev=0.1), name="W2")
                b2 = tf.Variable(tf.constant(0.1, shape=[num_filters[1]]), name="b2")
                conv2 = self.dialate_conv_layer(pooled1, W2, b2, rate=2, scope="dialate_conv_2")
                conv_bn2 = tf.layers.batch_normalization(conv2, training=self.is_training)
                pooled2 = self.folding_k_max_pooling(conv_bn2, top_k)
            else:
                W1 = tf.Variable(tf.truncated_normal([filter_sizes[0], embedding_size, 1, num_filters[0]], stddev=0.1), name="W1")
                b1 = tf.Variable(tf.constant(0.1, shape=[num_filters[0], embedding_size]), name="b1")
                conv1 = self.conv1d_layer(self.embedded_chars_expanded, W1, b1, scope="conv1d_1")
                conv_bn1 = tf.layers.batch_normalization(conv1, training=self.is_training)
                pooled1 = self.folding_k_max_pooling(conv_bn1, k1)

                W2 = tf.Variable(tf.truncated_normal([filter_sizes[1], embedding_size, num_filters[0], num_filters[1]], stddev=0.1), name="W2")
                b2 = tf.Variable(tf.constant(0.1, shape=[num_filters[1], embedding_size]), name="b2")
                conv2 = self.conv1d_layer(pooled1, W2, b2, scope="conv1d_2")
                conv_bn2 = tf.layers.batch_normalization(conv2, training=self.is_training)
                pooled2 = self.folding_k_max_pooling(conv_bn2, top_k)

        # Combine all the pooled features
        num_filters_total = int(pooled2.get_shape()[1] * pooled2.get_shape()[2] * pooled2.get_shape()[3])
        self.h_pool_flat = tf.reshape(pooled2, [-1, num_filters_total])
        
        # Fully Connected Layer
        with tf.name_scope("fc"):
            W_fc = tf.Variable(tf.truncated_normal(shape=[num_filters_total, self.fc_hidden_size],\
                stddev=0.1, dtype=tf.float32), name="W_fc")
            self.fc = tf.matmul(self.h_pool_flat, W_fc)
            self.fc_bn = tf.layers.batch_normalization(self.fc, training=self.is_training)
            self.fc_out = tf.nn.relu(self.fc_bn, name="relu")
        # Highway Layer
        self.highway = highway(self.fc_out, self.fc_out.get_shape()[1], num_layers=1, bias=-0.5, scope="Highway")

        # Add dropout
        with tf.name_scope("dropout"):
            self.h_drop = tf.nn.dropout(self.highway, self.dropout_keep_prob)

        # Final (unnormalized) scores and predictions
        with tf.name_scope("output"):
            W_out = tf.Variable(tf.truncated_normal(shape=[self.fc_hidden_size, num_classes],\
                stddev=0.1, dtype=tf.float32), name="W_out")
            b_out = tf.Variable(tf.constant(0.1, shape=[num_classes]), name="b_out")
            l2_loss += tf.nn.l2_loss(W_out)
            l2_loss += tf.nn.l2_loss(b_out)
            self.scores = tf.nn.xw_plus_b(self.h_drop, W_out, b_out, name="scores")
            self.predictions = tf.argmax(self.scores, 1, name="predictions")

        # Calculate mean cross-entropy loss
        with tf.name_scope("loss"):
            losses = tf.nn.softmax_cross_entropy_with_logits(logits=self.scores, labels=self.input_y)
            self.loss = tf.reduce_mean(losses) + l2_reg_lambda * l2_loss

        # Accuracy
        with tf.name_scope("accuracy"):
            correct_predictions = tf.equal(self.predictions, tf.argmax(self.input_y, 1))
            self.accuracy = tf.reduce_mean(tf.cast(correct_predictions, tf.float32), name="accuracy")
            self.correct_pred_num = tf.reduce_sum(tf.cast(correct_predictions, tf.int32), name="correct_num")

    def _max_pooling(self, inputs, filter_size):
        # max pooling
        pooled = tf.nn.max_pool(
            inputs,
            ksize=[1, filter_size, 1, 1],
            strides=[1, 1, 1, 1],
            padding='VALID',
            name="pool")
        return pooled
    
    def folding_k_max_pooling(self, inputs, top_k):
        # dynamic k max pooling
        #inputs : batch_size, sequence_length, hidden_size, chanel_size]
        inputs_unstack = tf.unstack(inputs, axis=2)#list of tensor : batch_size, seq_len, chanel_size
        outputs = []
        with tf.name_scope("folding_k_max_pooling"):
            for i in range(0, len(inputs_unstack), 2):
                tmp_res = tf.add(inputs_unstack[i], inputs_unstack[i+1])
                conv = tf.transpose(tmp_res, [0, 2, 1])
                k_pooled = tf.nn.top_k(conv, top_k, sorted=True).values
                k_pooled = tf.transpose(k_pooled, [0, 2, 1])
                outputs.append(k_pooled)
            final_outputs = tf.stack(outputs, axis=2)
        return final_outputs

    def _k_max_pooling(self, inputs, top_k):
        # k max pooling
        #inputs : batch_size, sequence_length, hidden_size, chanel_size]
        inputs = tf.transpose(inputs, [0,3,2,1]) # [batch_size, chanel_size, hidden_size, sequence_length]
        k_pooled = tf.nn.top_k(inputs, k=top_k, sorted=True, name='top_k')[0] # [batch_size, chanel_size, hidden_size, top_k]
        k_pooled = tf.transpose(k_pooled, [0,3,2,1]) #[batch_size, top_k, hidden_size, chanel_size]
        return k_pooled

    def _chunk_max_pooling(self, inputs, chunk_size):
        #chunk max pooling
        seq_len = inputs.get_shape()[1].values
        inputs_ = tf.split(inputs, chunk_size, axis=1) # seq_len/chunk_size list,element is  [batch_size, seq_len/chunk_size, hidden_size, chanel_size]
        chunk_pooled_list = []
        for i in range(len(inputs_)):
            chunk_ = inputs_[i]
            chunk_pool_ = self._max_pooling(chunk_, seq_len/chunk_size)
            chunk_pooled_list.append(chunk_pool_)
        chunk_pooled = tf.concat(chunk_pooled_list, axis=1)
        return chunk_pooled
    
    def get_seq(self, inputs):
        neighbor_seq = map(lambda i: tf.slice(inputs, [0, i-self.region_radius], [-1, self.region_size]), xrange(self.region_radius, inputs.shape[1] - self.region_radius))
        neighbor_seq = tf.convert_to_tensor(neighbor_seq)
        neighbor_seq = tf.transpose(neighbor_seq, [1,0,2])
        return neighbor_seq
    
    def get_seq_without_loss(self, inputs):
        neighbor_seq = map(lambda i: tf.slice(inputs, [0, i-self.region_radius], [-1, self.region_size]), xrange(self.region_radius, inputs.shape[1] - self.region_radius))
        neighbor_begin = map(lambda i: tf.slice(inputs, [0, 0], [-1, self.region_size]), xrange(0, self.region_radius))
        neighbor_end = map(lambda i: tf.slice(inputs, [0, inputs.shape[1] - self.region_size], [-1, self.region_size]), xrange(0, self.region_radius))
        neighbor_seq = tf.concat([neighbor_begin, neighbor_seq, neighbor_end], 0)
        neighbor_seq = tf.convert_to_tensor(neighbor_seq)
        neighbor_seq = tf.transpose(neighbor_seq, [1,0,2])
        return neighbor_seq

    def region_embedding(self, inputs):
        region_k_seq = self.get_seq(inputs)
        region_k_emb = tf.nn.embedding_lookup(self.W, region_k_seq)
        trimed_inputs = inputs[:, self.region_radius: inputs.get_shape()[1] - self.region_radius]
        context_unit = tf.nn.embedding_lookup(self.k_matrix_embedding, trimed_inputs)
        projected_emb = region_k_emb * context_unit
        embedded_chars = tf.reduce_max(projected_emb, axis=2)
        return embedded_chars
    
    def dialate_conv_layer(self, x, w, b, rate=2, scope="dialate_conv"):
        """dialte conv
            x: batch_size, seq_len, emb_size, in_channels
            w: filter_height, filter_width, in_channels, out_channels
            return : if valid: batch, height - 2 * (filter_width - 1), width - 2 * (filter_height - 1), out_channels
            if same: batch, height, width, out_channels
        """
        conv = tf.nn.atrous_conv2d(x, w, rate, padding='SAME', name=scope)
        return tf.nn.relu(tf.nn.bias_add(conv, b), name="relu")
    
    def conv1d_layer(self, x, w, b, scope="conv_1d"):
        """dialte conv
            x: batch_size, seq_len, emb_size, in_channels
            w: filter_height, filter_width, in_channels, out_channels
            return : if valid: batch, height - filter_width + 1, width, out_channels
            if same: batch, height, width, out_channels
        """
        input_unstack = tf.unstack(x, axis=2)
        w_unstack = tf.unstack(w, axis=1)
        b_unstack = tf.unstack(b, axis=1)
        conv1d = []
        with tf.name_scope(scope):
            for i in range(len(input_unstack)):
                conv = tf.nn.conv1d(input_unstack[i], w_unstack[i], stride=1, padding="SAME")
                conv = tf.nn.relu(tf.nn.bias_add(conv, b_unstack[i]), name="relu")
                conv1d.append(conv)
            final_conv = tf.stack(conv1d, axis=2)
        return final_conv
