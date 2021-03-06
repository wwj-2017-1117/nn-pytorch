# -*- coding: utf-8 -*-
# author: kmrocki

import numpy as np
import argparse, sys
import datetime, time
import random
from random import uniform

def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))

### parse args
parser = argparse.ArgumentParser(description='')
parser.add_argument('--fname', type=str, default = './logs/' + sys.argv[0] + '.dat', help='log filename')
parser.add_argument('--batchsize', type=int, default = 16, help='batch size')
parser.add_argument('--hidden', type=int, default = 64, help='hiddens')
parser.add_argument('--seqlength', type=int, default = 25, help='seqlength')
parser.add_argument('--timelimit', type=int, default = 1000, help='time limit (s)')
parser.add_argument('--gradcheck', action='store_const', const=True, default=True, help='run gradcheck?')
parser.add_argument('--fp64', action='store_const', const=True, default=True, help='double precision?')
parser.add_argument('--sample_length', type=int, default=1000, help='sample length')
parser.add_argument('--check_interval', type=int, default=1000, help='check interval (sample, grads)')

opt = parser.parse_args()
print(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sys.argv[0], opt)
logname = opt.fname
B = opt.batchsize
S = opt.seqlength
T = opt.timelimit
GC = opt.gradcheck
datatype = np.float32
if opt.fp64: datatype = np.float64

gradchecklogname = 'gradcheck.log'
samplelogname = 'sample.log'

# gradient checking
def gradCheck(inputs, target, cprev, hprev, mprev, rprev):
  global Wxh, Whh, Why, Whr, Whv, Whw, Whe, Wrh, bh, by
  num_checks, delta = 10, 1e-5
  _, dWxh, dWhh, dWhy, dWhr, dWhv, dWhw, dWhe, dWrh, dWry, dbh, dby, _, _ = lossFun(inputs, targets, cprev, hprev, mprev, rprev)
  print 'GRAD CHECK\n'
  with open(gradchecklogname, "w") as myfile: myfile.write("-----\n")

  for param,dparam,name in zip([Wxh, Whh, Why, Whr, Whv, Whw, Whe, Wrh, Wry, bh, by], [dWxh, dWhh, dWhy, dWhr, dWhv, dWhw, dWhe, dWrh, dWry, dbh, dby], ['Wxh', 'Whh', 'Why', 'Whr', 'Whv', 'Whw', 'Whe', 'Wrh', 'Wry', 'bh', 'by']):
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
      cg0, _, _, _, _, _, _ ,_, _, _, _ , _ , _ , _ = lossFun(inputs, targets, cprev, hprev, mprev, rprev)
      param.flat[ri] = old_val - delta
      cg1, _, _, _, _, _, _ ,_, _, _, _ , _ , _ , _ = lossFun(inputs, targets, cprev, hprev, mprev, rprev)
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
    print '%s:\t\tn = [%e, %e]\tmin %e, max %e\t\n\t\ta = [%e, %e]\tmean %e # %d/%d' % (name, min_numerical, max_numerical, min_error, max_error, min_analytic, max_analytic, mean_error, num_checks, valid_checks)
      # rel_error should be on order of 1e-7 or less
    entry = '%s:\t\tn = [%e, %e]\tmin %e, max %e\t\n\t\ta = [%e, %e]\tmean %e # %d/%d\n' % (name, min_numerical, max_numerical, min_error, max_error, min_analytic, max_analytic, mean_error, num_checks, valid_checks)
    with open(gradchecklogname, "a") as myfile: myfile.write(entry)


start = time.time()
with open(logname, "a") as myfile:
    entry = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sys.argv[0], opt
    myfile.write("# " + str(entry))
    myfile.write("\n#  ITER\t\tTIME\t\tTRAIN LOSS\n")

# data I/O
data = open('./ptb/ptb.train.txt', 'r').read() # should be simple plain text file
#data = open('./enwik8', 'r').read()
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
Wxh = np.random.randn(4*hidden_size, vocab_size).astype(datatype)*0.01 # input to hidden
Whh = np.random.randn(4*hidden_size, hidden_size).astype(datatype)*0.01 # hidden to hidden
Why = np.random.randn(vocab_size, hidden_size).astype(datatype)*0.01 # hidden to output
bh = np.zeros((4*hidden_size, 1), dtype = datatype) # hidden bias
by = np.zeros((vocab_size, 1), dtype = datatype) # output bias

# external memory
read_heads = 1
mem_width = vocab_size

Wrh = np.random.randn(4*hidden_size, vocab_size).astype(datatype)*0.01 # read vector to hidden
Whv = np.random.randn(vocab_size, hidden_size).astype(datatype)*0.01 # write content
Whr = np.random.randn(vocab_size, hidden_size).astype(datatype)*0.01 # read strength
Whw = np.random.randn(vocab_size, hidden_size).astype(datatype)*0.01 # write strength
Whe = np.random.randn(vocab_size, hidden_size).astype(datatype)*0.01 # erase strength
Wry = np.random.randn(vocab_size, read_heads * mem_width).astype(datatype)*0.01 # erase strength

N = hidden_size
M = vocab_size

# i o f c
# init f gates biases higher
bh[2*N:3*N,:] = 1

def lossFun(inputs, targets, cprev, hprev, mprev, rprev):
  """
  inputs,targets are both list of integers.
  cprev is Hx1 array of initial memory cell state
  hprev is Hx1 array of initial hidden state
  returns the loss, gradients on model parameters, and last hidden state
  """
  xs, hs, ys, ps, gs, cs = {}, {}, {}, {}, {}, {}

  # external mem
  mem_new_content, mem_read_gate, mem_write_gate, mem_erase_gate, memory, rs = {}, {}, {}, {}, {}, {}
  #

  hs[-1] = np.copy(hprev)
  cs[-1] = np.copy(cprev)
  rs[-1] = np.copy(rprev)
  memory[-1] = np.copy(mprev)

  loss = 0
  # forward pass
  for t in xrange(len(inputs)):
    xs[t] = np.zeros((vocab_size, B), dtype=datatype) # encode in 1-of-k representation
    for b in range(0,B):
        xs[t][:,b][inputs[t][b]] = 1

    # gates linear part
    gs[t] = np.dot(Wxh, xs[t]) + np.dot(Whh, hs[t-1]) + bh

    ############ external memory input ##########

    gs[t] += np.dot(Wrh, rs[t-1]) # add previous read vector

    ###############

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

    ##### external mem ########

    mem_new_content[t] = np.dot(Whv, hs[t])
    mem_write_gate[t] = sigmoid(np.dot(Whw, hs[t]))
    mem_read_gate[t] = sigmoid(np.dot(Whr, hs[t]))
    mem_erase_gate[t] = sigmoid(np.dot(Whe, hs[t]))

    memory[t] = memory[t-1] * (1 - mem_erase_gate[t] * mem_write_gate[t]) # 1
    #memory[t] = memory[t-1] * (1 - mem_erase_gate[t]) # 2
    memory[t] += mem_new_content[t] * mem_write_gate[t]

    rs[t] = memory[t] * mem_read_gate[t]

    # rs[t].shape = 50,20
    ys[t] += np.dot(Wry, rs[t]) # add read vector to output
    #ys[t] += rs[t] # add read vector to output

    ###########################
    ps[t] = np.exp(ys[t]) / np.sum(np.exp(ys[t]), axis=0) # probabilities for next chars

    for b in range(0,B):
        loss += -np.log(ps[t][targets[t,b],b]) # softmax (cross-entropy loss)
  # backward pass: compute gradients going backwards
  dWxh, dWhh, dWhy = np.zeros_like(Wxh), np.zeros_like(Whh), np.zeros_like(Why )

  ### ext
  dWhr, dWhv, dWhw, dWhe, dWrh, dWry = np.zeros_like(Whr), np.zeros_like(Whv), np.zeros_like(Whw), np.zeros_like(Whe), np.zeros_like(Wrh), np.zeros_like(Wry)
  ###

  dbh, dby = np.zeros_like(bh), np.zeros_like(by)
  dcnext = np.zeros_like(cs[0])
  dhnext = np.zeros_like(hs[0])
  dmemory = np.zeros_like(memory[0])
  dmem_next = np.zeros_like(memory[0])
  drs_next = np.zeros_like(rs[0])
  dg = np.zeros_like(gs[0])

  for t in reversed(xrange(len(inputs))):
    dy = np.copy(ps[t])
    for b in range(0,B):
        dy[targets[t][b], b] -= 1 # backprop into y. see http://cs231n.github.io/neural-networks-case-study/#grad if confused here
    dWhy += np.dot(dy, hs[t].T)
    ########
    dWry += np.dot(dy, rs[t].T)

    drs = np.dot(Wry.T, dy) + drs_next

    dmemory = drs * mem_read_gate[t] + dmem_next

    #iface gates
    dmem_write_gate = dmemory * (mem_new_content[t] - mem_erase_gate[t] * memory[t-1]) # 1
    # dmem_write_gate = dmemory * mem_new_content[t] # 2
    dmem_read_gate = drs * memory[t]
    dmem_new_content = dmemory * mem_write_gate[t]

    dmem_erase_gate = -dmemory * memory[t-1] * mem_write_gate[t]
    dmem_next = dmemory * (1 - mem_erase_gate[t] * mem_write_gate[t])

    #  dmem_erase_gate = -dmemory * memory[t-1] # 2
    #  dmem_next = dmemory * (1 - mem_erase_gate[t]) # 2

    # sigmoids
    dmem_read_gate = dmem_read_gate * mem_read_gate[t] * (1-mem_read_gate[t])
    dmem_write_gate = dmem_write_gate * mem_write_gate[t] * (1-mem_write_gate[t])
    dmem_erase_gate = dmem_erase_gate * mem_erase_gate[t] * (1-mem_erase_gate[t])

    # linearities
    dWhw += np.dot(dmem_write_gate, hs[t].T)
    dWhr += np.dot(dmem_read_gate, hs[t].T)
    dWhe += np.dot(dmem_erase_gate, hs[t].T)
    dWhv += np.dot(dmem_new_content, hs[t].T)
    ########

    dby += np.expand_dims(np.sum(dy,axis=1), axis=1)
    dh = np.dot(Why.T, dy) + dhnext # backprop into h

    dh += np.dot(Whw.T, dmem_write_gate)
    dh += np.dot(Whr.T, dmem_read_gate)
    dh += np.dot(Whe.T, dmem_erase_gate)
    dh += np.dot(Whv.T, dmem_new_content)
    ####

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
    dWrh += np.dot(dg, rs[t-1].T)
    dhnext = np.dot(Whh.T, dg)
    drs_next = np.dot(Wrh.T, dg)
    dcnext = dc * gs[t][2*N:3*N,:]
  #  for dparam in [dWxh, dWhh, dWhy, dbh, dby]:
    #  np.clip(dparam, -5, 5, out=dparam) # clip to mitigate exploding gradients
  return loss, dWxh, dWhh, dWhy, dWhr, dWhv, dWhw, dWhe, dWrh, dWry, dbh, dby, cs[len(inputs)-1], hs[len(inputs)-1]

def sample(c, h, m, r, seed_ix, n):
  """
  sample a sequence of integers from the model 
  h is memory state, seed_ix is seed letter for first time step
  """
  x = np.zeros((vocab_size, 1), dtype=datatype)
  x[seed_ix] = 1
  ixes = []

  for t in xrange(n):
    g = np.dot(Wxh, x) + np.dot(Whh,h) + np.dot(Wrh, r) + bh
    g[0:3*N,:] = sigmoid(g[0:3*N,:])
    g[3*N:4*N, :] = np.tanh(g[3*N:4*N,:])
    c = g[3*N:4*N,:] * g[0:N,:] + g[2*N:3*N,:] * c
    c = np.tanh(c)
    h = g[N:2*N,:] * c
    y = np.dot(Why, h) + by
    mem_new_content = np.dot(Whv, h)
    mem_write_gate = sigmoid(np.dot(Whw, h))
    mem_read_gate = sigmoid(np.dot(Whr, h))
    mem_erase_gate = sigmoid(np.dot(Whe, h))
    m = m * (1-mem_erase_gate * mem_write_gate) # 1
    #  m = m * (1-mem_erase_gate) # 2
    m += mem_new_content * mem_write_gate
    r = m * mem_read_gate
    y += np.dot(Wry, r)
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
cprev = np.zeros((hidden_size,B), dtype=datatype)
hprev = np.zeros((hidden_size,B), dtype=datatype)
mprev = np.zeros((vocab_size,B), dtype=datatype)
rprev = np.zeros((vocab_size,B), dtype=datatype)
mWxh, mWhh, mWhy  = np.zeros_like(Wxh), np.zeros_like(Whh), np.zeros_like(Why)
mWhr, mWhv, mWhw, mWhe, mWrh, mWry = np.zeros_like(Whr), np.zeros_like(Whv), np.zeros_like(Whw), np.zeros_like(Whe), np.zeros_like(Wrh), np.zeros_like(Wry)
mbh, mby = np.zeros_like(bh), np.zeros_like(by) # memory variables for Adagrad
smooth_loss = -np.log(1.0/vocab_size)*seq_length # loss at iteration 0
start = time.time()

t = time.time()-start
last=start
while t < T:
  # prepare inputs (we're sweeping from left to right in steps seq_length long)
  for b in range(0,B):
      if p[b]+seq_length+1 >= len(data) or n == 0:
        cprev[:,b] = np.zeros(hidden_size, dtype=datatype) # reset LSTM memory
        hprev[:,b] = np.zeros(hidden_size, dtype=datatype) # reset hidden memory
        mprev[:,b] = np.zeros(vocab_size, dtype=datatype) # reset ext memory
        rprev[:,b] = np.zeros(vocab_size, dtype=datatype) # reset read vec memory
        p[b] = np.random.randint(len(data)-1-S)

      inputs[:,b] = [char_to_ix[ch] for ch in data[p[b]:p[b]+seq_length]]
      targets[:,b] = [char_to_ix[ch] for ch in data[p[b]+1:p[b]+seq_length+1]]

  # sample from the model now and then
  if n % opt.check_interval == 200 and n > 0:
    sample_ix = sample(np.expand_dims(cprev[:,0], axis=1), np.expand_dims(hprev[:,0], axis=1), np.expand_dims(mprev[:,0], axis=1), np.expand_dims(rprev[:,0], axis=1), inputs[0], opt.sample_length)
    txt = ''.join(ix_to_char[ix] for ix in sample_ix)
    print '----\n %s \n----' % (txt, )
    entry = '%s\n' % (txt)
    with open(samplelogname, "w") as myfile: myfile.write(entry)
    gradCheck(inputs, targets, cprev, hprev, mprev, rprev)

  # forward seq_length characters through the net and fetch gradient
  loss, dWxh, dWhh, dWhy, dWhr, dWhv, dWhw, dWhe, dWrh, dWry, dbh, dby, cprev, hprev = lossFun(inputs, targets, cprev, hprev, mprev, rprev)
  smooth_loss = smooth_loss * 0.999 + np.mean(loss)/(np.log(2)*B) * 0.001
  interval = time.time() - last

  if n % 100 == 0 and n > 0:
    tdelta = time.time()-last
    last = time.time()
    t = time.time()-start
    entry = '{:5}\t\t{:3f}\t{:3f}\n'.format(n, t, smooth_loss/seq_length)
    with open(logname, "a") as myfile: myfile.write(entry)

    print '%.3f s, iter %d, %.4f BPC, %.2f char/s' % (t, n, smooth_loss / seq_length, (B*S*100)/tdelta) # print progress

  # perform parameter update with Adagrad
  for param, dparam, mem in zip([Wxh, Whh, Why, Whr, Whv, Whw, Whe, Wrh, Wry, bh, by],
                                [dWxh, dWhh, dWhy, dWhr, dWhv, dWhw, dWhe, dWrh, dWry, dbh, dby], 
                                [mWxh, mWhh, mWhy, mWhr, mWhv, mWhw, mWhe, mWrh, mWry, mbh, mby]):
    mem += dparam * dparam
    param += -learning_rate * dparam / np.sqrt(mem + 1e-8) # adagrad update

  for b in range(0,B): p[b] += seq_length # move data pointer
  n += 1 # iteration counter
