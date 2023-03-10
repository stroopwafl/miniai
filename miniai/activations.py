# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/04_activations.ipynb.

# %% auto 0
__all__ = ['append_stats', 'Hook', 'Hooks', 'get_hist', 'get_min', 'ActivationStats']

# %% ../nbs/04_activations.ipynb 2
import math, random, torch, matplotlib.pyplot as plt, numpy as np
from operator import itemgetter
from functools import partial
import fastcore.all as fc
from fastcore import docments

from torch import tensor, nn, optim
import torch.nn.functional as F
from datasets import load_dataset
import torchvision.transforms.functional as TF

from .learner import *
from .datasets import *
from .conv import *

# %% ../nbs/04_activations.ipynb 7
def append_stats(hook, module, inp, out):
    """
        Creates lists to store the mean, standard deviation and histogram
        information of layer activations.
    """
    if not hasattr(hook, "stats"): hook.stats = ([], [], [])
    acts = to_cpu(out)
    hook.stats[0].append(acts.mean())
    hook.stats[1].append(acts.std())
    hook.stats[2].append(acts.histc(40, 0, 10))

# %% ../nbs/04_activations.ipynb 8
class Hook():
    """
        Base hook class that initialises a Pytorch hook using the function
        passed as an argument.
    """
    def __init__(self, model, func): self.hook = model.register_forward_hook(partial(func, self))
    def remove(self): self.hook.remove()
    def __del__(self): self.remove()

# %% ../nbs/04_activations.ipynb 13
class Hooks(list):
    def __init__(self, model, func): super().__init__([Hook(layer, func) for layer in model])
    def __enter__(self, *args): return self
    def __exit__(self, *args): self.remove()
    def __del__(self): self.remove()
    def __delitem__(self, i):
        self[i].remove()
        super().__delitem__(i)
    def remove(self): 
        for hook in self: hook.remove()

# %% ../nbs/04_activations.ipynb 15
def get_hist(h): 
    """
        Takes the list of histogram information stored inside a hook,
        and produces a stacked tensor of log values for layer activations 
        suitable for the colourful dimension chart.
    """
    return torch.stack(h.stats[2]).float().log1p().t().flip(0)

# %% ../nbs/04_activations.ipynb 18
def get_min(h):
    h1 = torch.stack(h.stats[2]).t().float()
    return h1[0]/h1.sum(0)

# %% ../nbs/04_activations.ipynb 21
class ActivationStats(Callback):
    """
        Base callback for activation stats which collects and stores statistics,
        including mean, standard deviation and histogram tensor for layer 
        activations. Not used itself ??? inherited by child classes.
    """
    order = ProgressCB.order + 1
    def __init__(
        self, 
        func, # Function that will be applied to a layer each time forward method is called.
        layer_filter=fc.noop, # Optional function to filter layers to which hooks are applied.
        on_train=True # If true, hooks are applied to training set
    ): 
        fc.store_attr()
        super().__init__()
    def before_fit(self):
        mods = fc.filter_ex(self.learn.model.modules(), self.layer_filter)
        self.hooks = [Hook(l, self.func) for l in mods]
        self.learn.hooks = self
        
    def color_dim(self):
        fig, axes = plt.subplots(1,len(self.hooks),figsize=(16,10))
        for i, (ax, h) in enumerate(zip(axes.flatten(), self.hooks)):
            ax.imshow(get_hist(h))
            ax.set_title(f"Layer {i + 1}")
            ax.axis('off')
    
    def mean_std(self):
        fig, ax = plt.subplots(1,2,figsize=(9,5))
        for i, h in enumerate(self.hooks):
            for j in 0,1:
                ax[j].plot(h.stats[j])
                ax[j].set_title("Means" if j == 0 else "Std")
                ax[j].legend(range(len(self.hooks)))
                
    def dead_chart(self):
        fig, axes = plt.subplots(1,len(self.hooks),figsize=(16,2))
        for i, (ax, h) in enumerate(zip(axes.flatten(), self.hooks)):
            ax.plot(get_min(h))
            ax.set_title(f"Layer {i}")
        
    def __iter__(): return iter(self.hooks)
    def __len__(): return len(self.hooks)
