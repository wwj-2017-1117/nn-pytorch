# -*- coding: utf-8 -*-
# author: kmrocki

import numpy as np
import argparse, sys
import datetime, time
import random
from random import uniform

def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))

gradchecklogname = 'gradcheck.log'
samplelogname = 'sample.log'

# gradient checking
def gradCheck(inputs, target, cprev, hprev):
  global Wxh, Whh, Why, bh, by
  num_checks, delta = 50, 1e-5
  _, dWxh, dWhh, dWhy, dbh, dby, _, _ = lossFun(inputs, targets, cprev, hprev)
  print 'GRAD CHECK\n'
  with open(gradchecklogname, "w") as myfile: myfile.write("-----\n")

  for param,dparam,name in zip([Wxh, Whh, Why, bh, by], [dWxh, dWhh, dWhy, dbh, dby], ['Wxh', 'Whh', 'Why', 'bh', 'by']):
    s0 = dparam.shape
    s1 = param.shape
    assert s0 == s1, 'Error dims dont match: %s and %s.' % (`s0`, `s1`)
    min_error, mean_error, max_error = 1,0,0
    min_numerical, max_numerical = 1e10, -1e10
    min_analytic, max_analytic = 1e10, -1e10
    valid_checks = 0
    for i in xrange(num_checks):
      ri = int(uniform(0,param.size))
      # evaluate cost at [x + delta] and [x - delta]
      old_val = param.flat[ri]
      param.flat[ri] = old_val + delta
      cg0, _, _, _, _, _, _ , _ = lossFun(inputs, targets, cprev, hprev)
      param.flat[ri] = old_val - delta
      cg1, _, _, _, _, _, _ , _ = lossFun(inputs, targets, cprev, hprev)
      param.flat[ri] = old_val # reset old value for this parameter
      # fetch both numerical and analytic gradient
      grad_analytic = dparam.flat[ri]
      grad_numerical = (cg0 - cg1) / ( 2 * delta )
      rel_error = 0
      vdiff = abs(grad_analytic - grad_numerical)
      vsum = abs(grad_numerical + grad_analytic)
      min_numerical = min(grad_numerical, min_numerical)
      max_numerical = max(grad_numerical, max_numerical)
      min_analytic = min(grad_analytic, min_analytic)
      max_analytic = max(grad_analytic, max_analytic)

      if vsum > 0:
          rel_error = vdiff / vsum
          min_error = min(min_error, rel_error)
          max_error = max(max_error, rel_error)
          mean_error = mean_error + rel_error
          valid_checks += 1

    mean_error /= num_checks
    #print '%s:\n\t min %e, max %e, mean %e # %d/%d\n\n\tn = [%e, %e]\n\ta = [%e, %e]' % (name, min_error, max_error, mean_error, num_checks, valid_checks, min_numerical, max_numerical, min_analytic, max_analytic)
      # rel_error should be on order of 1e-7 or less
    entry = '%s:\n\t min %e, max %e, mean %e # %d/%d\n\n\tn = [%e, %e]\n\ta = [%e, %e]\n' % (name, min_error, max_error, mean_error, num_checks, valid_checks, min_numerical, max_numerical, min_analytic, max_analytic)
    with open(gradchecklogname, "a") as myfile: myfile.write(entry)

### parse args
parser = argparse.ArgumentParser(description='')
parser.add_argument('--fname', type=str, default = './logs/' + sys.argv[0] + '.dat', help='log filename')
parser.add_argument('--batchsize', type=int, default = 1, help='batch size')
parser.add_argument('--hidden', type=int, default = 64, help='hiddens')
parser.add_argument('--seqlength', type=int, default = 25, help='seqlength')
parser.add_argument('--timelimit', type=int, default = 100, help='time limit (s)')

opt = parser.parse_args()
print(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sys.argv[0], opt)
logname = opt.fname
B = opt.batchsize
S = opt.seqlength
T = opt.timelimit

start = time.time()
with open(logname, "a") as myfile:
    entry = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sys.argv[0], opt
    myfile.write("# " + str(entry))
    myfile.write("\n#  ITER\t\tTIME\t\tTRAIN LOSS\n")

# data I/O
data = open('./ptb/ptb.train.txt', 'r').read() # should be simple plain text file
chars = list(set(data))
data_size, vocab_size = len(data), len(chars)
print 'data has %d characters, %d unique.' % (data_size, vocab_size)
char_to_ix = { ch:i for i,ch in enumerate(chars) }
ix_to_char = { i:ch for i,ch in enumerate(chars) }

# hyperparameters
hidden_size = opt.hidden # size of hidden layer of neurons
seq_length = opt.seqlength # number of steps to unroll the RNN for
learning_rate = 1e-1
B = opt.batchsize

# model parameters
Wxh = np.random.randn(4*hidden_size, vocab_size)*0.01 # input to hidden
Whh = np.random.randn(4*hidden_size, hidden_size)*0.01 # hidden to hidden
Why = np.random.randn(vocab_size, hidden_size)*0.01 # hidden to output
bh = np.zeros((4*hidden_size, 1)) # hidden bias
by = np.zeros((vocab_size, 1)) # output bias

N = hidden_size
M = vocab_size

# i o f c
# init f gates biases higher
bh[2*N:3*N,:] = 1

def lossFun(inputs, targets, cprev, hprev):
  """
  inputs,targets are both list of integers.
  cprev is Hx1 array of initial memory cell state
  hprev is Hx1 array of initial hidden state
  returns the loss, gradients on model parameters, and last hidden state
  """
  xs, hs, ys, ps, gs, cs = {}, {}, {}, {}, {}, {}
  hs[-1] = np.copy(hprev)
  cs[-1] = np.copy(cprev)
  loss = 0
  # forward pass
  for t in xrange(len(inputs)):
    xs[t] = np.zeros((vocab_size, B)) # encode in 1-of-k representation
    for b in range(0,B):
        xs[t][:,b][inputs[t][b]] = 1

    #print Wxh.shape #256, 50
    #print Whh.shape #64, 256
    #print Why.shape #50, 256
    #print xs[t].shape #50, 4
    #print hs[t-1].shape #64, 4
    #print bh.shape #256, 4

    # gates linear part
    gs[t] = np.dot(Wxh, xs[t]) + np.dot(Whh, hs[t-1]) + bh
    # gates nonlinear part
    #i, o, f gates - sigmoid
    gs[t][0:3*N,:] = sigmoid(gs[t][0:3*N,:])
    #c gate - tanh
    gs[t][3*N:4*N, :] = np.tanh(gs[t][3*N:4*N,:])
    #mem(t) = c gate * i gate + f gate * mem(t-1)
    cs[t] = gs[t][3*N:4*N,:] * gs[t][0:N,:] + gs[t][2*N:3*N,:] * cs[t-1]
    #mem(t) nonlinearity
    cs[t] = np.tanh(cs[t])
    #update hs
    hs[t] = gs[t][N:2*N,:] * cs[t] # hidden state
    ys[t] = np.dot(Why, hs[t]) + by # unnormalized log probabilities for next chars
    ps[t] = np.exp(ys[t]) / np.sum(np.exp(ys[t]), axis=0) # probabilities for next chars

    for b in range(0,B):
        loss += -np.log(ps[t][targets[t,b],b]) # softmax (cross-entropy loss)
  # backward pass: compute gradients going backwards
  dWxh, dWhh, dWhy = np.zeros_like(Wxh), np.zeros_like(Whh), np.zeros_like(Why)
  dbh, dby = np.zeros_like(bh), np.zeros_like(by)
  dcnext = np.zeros_like(cs[0])
  dhnext = np.zeros_like(hs[0])
  dg = np.zeros_like(gs[0])

  for t in reversed(xrange(len(inputs))):
    dy = np.copy(ps[t])
    for b in range(0,B):
        dy[targets[t][b], b] -= 1 # backprop into y. see http://cs231n.github.io/neural-networks-case-study/#grad if confused here
    dWhy += np.dot(dy, hs[t].T)
    dby += np.expand_dims(np.sum(dy,axis=1), axis=1)
    dh = np.dot(Why.T, dy) + dhnext # backprop into h

    dc = dh * gs[t][N:2*N,:] + dcnext # backprop into c
    dc = dc * (1 - cs[t] * cs[t]) # backprop though tanh

    dg[N:2*N,:] = dh * cs[t] # o gates
    dg[0:N,:] = gs[t][3*N:4*N,:] * dc # i gates
    dg[2*N:3*N,:] = cs[t-1] * dc # f gates
    dg[3*N:4*N,:] = gs[t][0:N,:] * dc # c gates
    dg[0:3*N,:] = dg[0:3*N,:] * gs[t][0:3*N,:] * (1 - gs[t][0:3*N,:]) # backprop through sigmoids
    dg[3*N:4*N,:] = dg[3*N:4*N,:] * (1 - gs[t][3*N:4*N,:] * gs[t][3*N:4*N,:]) # backprop through tanh
    dbh += np.expand_dims(np.sum(dg,axis=1), axis=1)
    dWxh += np.dot(dg, xs[t].T)
    dWhh += np.dot(dg, hs[t-1].T)
    dhnext = np.dot(Whh.T, dg)
    dcnext = dc * gs[t][2*N:3*N,:]
  #  for dparam in [dWxh, dWhh, dWhy, dbh, dby]:
    #  np.clip(dparam, -5, 5, out=dparam) # clip to mitigate exploding gradients
  return loss, dWxh, dWhh, dWhy, dbh, dby, cs[len(inputs)-1], hs[len(inputs)-1]

def sample(c, h, seed_ix, n):
  """
  sample a sequence of integers from the model 
  h is memory state, seed_ix is seed letter for first time step
  """
  x = np.zeros((vocab_size, 1))
  x[seed_ix] = 1
  ixes = []

  for t in xrange(n):
    g = np.dot(Wxh, x) + np.dot(Whh,h) + bh
    g[0:3*N,:] = sigmoid(g[0:3*N,:])
    g[3*N:4*N, :] = np.tanh(g[3*N:4*N,:])
    c = g[3*N:4*N,:] * g[0:N,:] + g[2*N:3*N,:] * c
    c = np.tanh(c)
    h = g[N:2*N,:] * c
    y = np.dot(Why, h) + by
    p = np.exp(y) / np.sum(np.exp(y))
    ix = np.random.choice(range(vocab_size), p=p.ravel())
    x = np.zeros((vocab_size, 1))
    x[ix] = 1
    ixes.append(ix)
  return ixes

n = 0
p = np.random.randint(len(data)-1-S,size=(B)).tolist()
inputs = np.zeros((S,B), dtype=int)
targets = np.zeros((S,B), dtype=int)
cprev = np.zeros((hidden_size,B), dtype=np.float32)
hprev = np.zeros((hidden_size,B), dtype=np.float32)
mWxh, mWhh, mWhy = np.zeros_like(Wxh), np.zeros_like(Whh), np.zeros_like(Why)
mbh, mby = np.zeros_like(bh), np.zeros_like(by) # memory variables for Adagrad
smooth_loss = -np.log(1.0/vocab_size)*seq_length # loss at iteration 0
start = time.time()

t = time.time()-start
last=start
while t < T:
  # prepare inputs (we're sweeping from left to right in steps seq_length long)
  for b in range(0,B):
      if p[b]+seq_length+1 >= len(data) or n == 0:
        cprev[:,b] = np.zeros(hidden_size) # reset LSTM memory
        hprev[:,b] = np.zeros(hidden_size) # reset hidden memory
        p[b] = np.random.randint(len(data)-1-S)
        print p[b]

      inputs[:,b] = [char_to_ix[ch] for ch in data[p[b]:p[b]+seq_length]]
      targets[:,b] = [char_to_ix[ch] for ch in data[p[b]+1:p[b]+seq_length+1]]

  # sample from the model now and then
  if n < 0:
    sample_ix = sample(np.expand_dims(cprev[:,0], axis=1), np.expand_dims(hprev[:,0], axis=1), inputs[0], 5000)
    txt = ''.join(ix_to_char[ix] for ix in sample_ix)
    #print '----\n %s \n----' % (txt, )
    entry = '%s\n' % (txt)
    with open(samplelogname, "w") as myfile: myfile.write(entry)
    gradCheck(inputs, targets, cprev, hprev)

  # forward seq_length characters through the net and fetch gradient
  loss, dWxh, dWhh, dWhy, dbh, dby, cprev, hprev = lossFun(inputs, targets, cprev, hprev)
  smooth_loss = smooth_loss * 0.999 + np.mean(loss)/np.log(2) * 0.001
  interval = time.time() - last

  if n % 500 == 0 and n > 0:
    tdelta = time.time()-last
    last = time.time()
    t = time.time()-start
    entry = '{:5}\t\t{:3f}\t{:3f}\n'.format(n, t, smooth_loss/seq_length)
    with open(logname, "a") as myfile: myfile.write(entry)

    print '%.3f s, iter %d, %.4f BPC, %.2f char/s' % (t, n, smooth_loss / seq_length, (B*S*500)/tdelta) # print progress

  # perform parameter update with Adagrad
  for param, dparam, mem in zip([Wxh, Whh, Why, bh, by], 
                                [dWxh, dWhh, dWhy, dbh, dby], 
                                [mWxh, mWhh, mWhy, mbh, mby]):
    mem += dparam * dparam
    param += -learning_rate * dparam / np.sqrt(mem + 1e-8) # adagrad update

  for b in range(0,B): p[b] += seq_length # move data pointer
  n += 1 # iteration counter
