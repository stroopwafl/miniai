# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/05_initialisation.ipynb.

# %% ../nbs/05_initialisation.ipynb 2
from __future__ import annotations
import math, random, torch, matplotlib.pyplot as plt, numpy as np
from pathlib import Path
from operator import itemgetter
from itertools import zip_longest
from functools import partial
import fastcore.all as fc

from torch import tensor, nn, optim
import torch.nn.functional as F
from datasets import load_dataset
from tqdm.auto import tqdm
import torchvision.transforms.functional as TF

from .learner import *
from .datasets import *
from .conv import *
from .activations import *
from .core import *

import re
from torcheval.metrics import MulticlassAccuracy

torch.set_printoptions(precision=2, linewidth=140, sci_mode=False)
torch.manual_seed(1)

# %% auto 0
__all__ = ['xavier_init', 'lsuv_stats', 'lsuv_init', 'LSUVInit', 'normalise_batch', 'BatchTransform', 'LayerNorm', 'BatchNorm',
           'GeneralReLU', 'kaiming_init']

# %% ../nbs/05_initialisation.ipynb 10
def xavier_init(layer):
    if isinstance(layer, (nn.Conv1d, nn.Conv2d, nn.Conv3d, nn.Linear)): nn.init.xavier_normal_(layer.weight)

# %% ../nbs/05_initialisation.ipynb 26
def lsuv_stats(hook, module, inp, out):
    if not hasattr(hook, 'mean'): hook.mean = tensor(0)
    if not hasattr(hook, 'std'): hook.std = tensor(0)
    acts = to_cpu(out)
    hook.mean = acts.mean()
    hook.std = acts.std()

# %% ../nbs/05_initialisation.ipynb 27
def lsuv_init(layer, inp, xb, model):
    h = Hook(layer, lsuv_stats)
    with torch.no_grad():
        while model(xb) is not None and (abs(h.std-1) > 1e-3 or abs(h.mean) > 1e-3):
            inp.bias -= h.mean
            inp.weight.data /= h.std
    h.remove()

# %% ../nbs/05_initialisation.ipynb 28
class LSUVInit(Callback):
    order = ProgressCB.order + 1
    def __init__(self):
        super().__init__()
    def before_fit(self):
        mods = [m for m in self.learn.model.modules() if isinstance(m, (nn.Conv1d, nn.Conv2d, nn.Conv3d, nn.Linear))]
        relus = [r for r in self.learn.model.modules() if isinstance(r, (nn.ReLU))]
        xb = next(iter(self.learn.dls.train))[0]
        for m in zip(relus, mods): lsuv_init(*m, xb, self.learn.model)
        self._del()
    def _del(self):
        cbl = [str(c) for c in self.learn.cbs]
        match = [l for l in cbl if re.search(r"LSUVInit", l) is not None]
        del(self.learn.cbs[cbl.index(match[0])])

# %% ../nbs/05_initialisation.ipynb 31
def normalise_batch(b):
    xb, yb = b[0], b[1]
    mean, std = xb.mean(), xb.std()
    return (xb-mean)/std, yb

# %% ../nbs/05_initialisation.ipynb 32
class BatchTransform(Callback):
    def __init__(self, f): self.func = f
    def before_batch(self): self.learn.batch = self.func(self.learn.batch)

# %% ../nbs/05_initialisation.ipynb 37
class LayerNorm(nn.Module):
    def __init__(self, dummy, epsilon=1e-5):
        super().__init__()
        self.epsilon = epsilon
        self.add = nn.Parameter(tensor(0.))
        self.mult = nn.Parameter(tensor(1.))
    def forward(self, x):
        mean = x.mean((1, 2, 3), keepdim=True)
        var = x.var((1, 2, 3), keepdim=True)
        norm = (x-mean)/(var+self.epsilon).sqrt()
        return norm*self.mult + self.add

# %% ../nbs/05_initialisation.ipynb 40
class BatchNorm(nn.Module):
    def __init__(self, out_channels, mom=0.9, epsilon=1e-5):
        super().__init__()
        self.epsilon, self.mom = epsilon, mom
        self.adds = nn.Parameter(torch.zeros(out_channels, 1, 1))
        self.mults = nn.Parameter(torch.ones(out_channels, 1, 1))
        self.register_buffer('means', torch.zeros(1, out_channels, 1, 1))
        self.register_buffer('vars', torch.ones(1, out_channels, 1, 1))
    
    def update(self, x):
        mean = x.mean((0, 2, 3), keepdim=True)
        var = x.var((0, 2, 3), keepdim=True)
        self.means.lerp_(mean, self.mom)
        self.vars.lerp_(var, self.mom)
        return mean, var
    
    def forward(self, x):
        if self.training:
            with torch.no_grad():
                mean, var = self.update(x)
        else: mean, var = self.means, self.vars
        norm = (x-mean)/(var-self.epsilon).sqrt()
        return norm*self.mults + self.adds

# %% ../nbs/05_initialisation.ipynb 45
class GeneralReLU(nn.Module):
    def __init__(self, subtract=None, leak=None, maxv=None):
        super().__init__()
        fc.store_attr()
    def forward(self, x):
        x = F.leaky_relu(x, self.leak) if self.leak is not None else F.relu(x)
        if self.subtract is not None: x -= self.subtract
        if self.maxv is not None: x.clamp_max_(self.maxv)
        return x

# %% ../nbs/05_initialisation.ipynb 47
def kaiming_init(layer, leak=None):
    if isinstance(layer, (nn.Conv1d, nn.Conv2d, nn.Conv3d, nn.Linear)): nn.init.kaiming_normal_(layer.weight, a=leak)
