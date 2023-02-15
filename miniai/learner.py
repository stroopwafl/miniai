# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/03_learner.ipynb.

# %% auto 0
__all__ = ['CancelFitException', 'CancelBatchException', 'CancelEpochException', 'CancelFull_EpochException', 'Learner',
           'Callback', 'to_cpu', 'MetricsCB', 'ProgressCB', 'get_device', 'DeviceCB', 'BaseLearner', 'MomentumLearner',
           'LRFinderCB']

# %% ../nbs/03_learner.ipynb 3
import math, torch, matplotlib.pyplot as plt, numpy as np
from operator import itemgetter
import fastcore.all as fc

from torch import tensor, nn, optim
from torch.utils.data import DataLoader, default_collate
import torch.nn.functional as F

from datasets import load_dataset, load_dataset_builder
from tqdm import tqdm

import torchvision.transforms.functional as TF
from fastcore.test import test_close
from contextlib import contextmanager
from functools import partial

from operator import attrgetter,itemgetter
from torcheval.metrics import *

import pandas as pd
from .conv import *
from .datasets import *
from nbdev.showdoc import *

from fastprogress.fastprogress import master_bar, progress_bar

# %% ../nbs/03_learner.ipynb 11
class CancelFitException(Exception): pass
class CancelBatchException(Exception): pass
class CancelEpochException(Exception): pass
class CancelFull_EpochException(Exception): pass

# %% ../nbs/03_learner.ipynb 13
from torch.optim import lr_scheduler

# %% ../nbs/03_learner.ipynb 14
class Learner:
    """
        Main flexible learner class that enables modular functionality to be added on.
        It does so with a context manager, which wraps function calls with 'before' and 
        'after' callbacks, within which functionality can be added.
    """
    def __init__(
        self, 
        dls, # Dataloaders object, expected as a tuple of (train, valid)
        model, # Model used for training
        opt_func=optim.SGD, # Optimisation function for optimising parameters after backprop, defaults to SGD
        scheduler=None, # Scheduler for adjusting the learning rate
        loss_func=F.cross_entropy, # Loss function used, defaults to cross entropy
        cbs: list=None # Optional list of callback functions called via context manager
    ):
        fc.store_attr()
        if cbs is not None:
            for cb in cbs: cb.learn = self
        
    @contextmanager
    def callback_context(self, name):
        try:
            self.callback(f"before_{name}")
            yield
            self.callback(f"after_{name}")
        except globals()[f'Cancel{name.title()}Exception']: pass
        
    def fit(self, lr, epochs, lr_find=False):
        self.lr, self.n_epochs, self.epochs = lr, epochs, range(epochs)
        self.opt = self.opt_func(self.model.parameters(), self.lr)
        if self.scheduler is not None and not lr_find: 
            self.scheduler.learn = self
            self.cbs = self.cbs + [self.scheduler]
        with self.callback_context('fit'):
            for self.epoch in self.epochs:
                with self.callback_context('full_epoch'):
                    self._one_epoch(train=True)
                    self._one_epoch(train=False)
        
    def _one_epoch(self, train):
        self.model.training = train
        if train: self.dl = self.dls.train
        else: self.dl = self.dls.valid
        with self.callback_context('epoch'):
            for self.batch in self.dl:
                with self.callback_context('batch'):
                    self._one_batch()
        
    def _one_batch(self):
        self.xb, self.yb = self.batch
        self.predict()
        self.get_loss()
        if self.model.training:
            self.backward()
            self.step()
            self.zero_grad()
            
    def lr_find(self, lr_start=0.00001, gamma=1.3):
        lrf = LRFinderCB(gamma)
        lrf.learn = self
        self.cbs = self.cbs + [lrf]
        self.fit(lr_start, 1, lr_find=True)
        del(self.cbs[-1])
            
    def callback(self, name): 
        if self.cbs is not None:
            for cb in sorted(self.cbs, key=attrgetter('order')): 
                method = getattr(cb, name, None)
                if method is not None: method()

# %% ../nbs/03_learner.ipynb 16
class Callback(): 
    """
        Base callback class establishing that callbacks can have an order.
        Callbacks inherit from this class and optionally update the order 
        parameter, to enable sequential ordering of callback functions that 
        depend on each other.
    """
    order = 0

# %% ../nbs/03_learner.ipynb 18
def to_cpu(b):
    """
        Returns data to the CPU.
    """
    if isinstance(b, list): return [to_cpu(o) for o in b]
    if isinstance(b, tuple): return tuple(to_cpu(list(b)))
    return b.detach().cpu()

# %% ../nbs/03_learner.ipynb 19
class MetricsCB(Callback):
    """
        Establishes and calculates metrics for training, and prints them
        out at the end of each epoch. Metrics include train loss, validation
        loss and optional metrics from the `torcheval` library.
    """
    def __init__(self, *ms, **metrics):
        for o in ms: metrics[type(o).__name__] = o
        self.metrics = metrics
        self.all_metrics = metrics
        self.all_metrics['loss'] = Mean()
        
    def _log(self): 
        print(self.log)
    def before_fit(self):
        self.learn.metrics = self
    def before_full_epoch(self):
        self.log = pd.DataFrame({
            "Train loss": 0,
            "Valid loss": 0,
            "Accuracy": 0
        }, index=range(self.learn.epoch, self.learn.epoch+1))
    def before_epoch(self): [o.reset() for o in self.all_metrics.values()]
    def after_batch(self):
        x, y = to_cpu(self.learn.batch)
        self.metrics['accuracy'].update(to_cpu(self.learn.preds), y)
        self.metrics['loss'].update(to_cpu(self.learn.loss), weight=len(x))
    def after_epoch(self): 
        if self.learn.model.training: self.log['Train loss'] = round(float(self.all_metrics['loss'].compute().detach()), 4)
        if not self.learn.model.training: 
            self.log['Valid loss'] = round(float(self.all_metrics['loss'].compute().detach()), 4)
            self.log['Accuracy'] = round(float(self.all_metrics['accuracy'].compute().detach()), 4)
    def after_full_epoch(self):
        # log = {k:f"{v.compute():.3f}" for k, v in self.all_metrics.items()}
        self._log()

# %% ../nbs/03_learner.ipynb 21
class ProgressCB(Callback):
    """
        Handles progress bars during training, and an optional plot parameter 
        plots the change in loss across training steps.
    """
    order = MetricsCB.order + 1
    def __init__(
        self, 
        plot=False # If true, plots the change in loss across training steps
    ): 
        self.plot = plot
        if plot: self.losses, self.counter = [], 0
        
    def before_fit(self): self.learn.epochs = master_bar(self.learn.epochs, total=self.learn.n_epochs)
    
    def before_epoch(self):
        self.learn.dl = progress_bar(self.learn.dl, leave=False, total=len(self.learn.dl))
    def after_batch(self):
        if self.plot and self.learn.model.training:
            self.losses.append(float(self.learn.loss.detach()))
            self.counter += 1
    
    def after_fit(self):
        if self.plot:
            self._plot()
            
    def _plot(self):
        fig, ax = plt.subplots(figsize=(4, 4))
        ax.plot(range(self.counter), self.losses)
        ax.set_title('Change in loss')
        ax.set_xlabel('Steps')
        ax.set_ylabel('Loss')

# %% ../nbs/03_learner.ipynb 23
def get_device():
    """
        Returns the available device in the current environment as
        a string.
    """
    if torch.backends.mps.is_available(): device = 'mps' 
    if torch.cuda.is_available(): device = 'cuda'
    else: device = 'cpu'
    return device

# %% ../nbs/03_learner.ipynb 24
class DeviceCB(Callback):
    """
        Sends both the model and batch data to the device.
    """
    def __init__(self): self.device = get_device()
    def before_fit(self): self.learn.model.to(self.device)
    def before_batch(self): 
        xb, yb = self.learn.batch
        self.learn.batch = (xb.to(self.device), yb.to(self.device))

# %% ../nbs/03_learner.ipynb 26
class BaseLearner(Learner):
    """
        Flexible training subclass that handles key training functionality
        for each batch.
    """
    def predict(self): self.preds = self.model(self.xb)
    def get_loss(self): self.loss = self.loss_func(self.preds, self.yb)
    def backward(self): self.loss.backward()
    def step(self): self.opt.step()
    def zero_grad(self): self.opt.zero_grad()

# %% ../nbs/03_learner.ipynb 29
class MomentumLearner(BaseLearner):
    """
        Training subclass which implements momentum in a memory-efficient
        way. Gradient updates are calculated directly in the tensor gradient, 
        and thus avoids storing a history of gradient updates.
    """
    def __init__(self, dls, model, opt_func=optim.SGD, loss_func=F.cross_entropy, cbs=None, mom=0.85): 
        self.mom = mom
        super().__init__(dls, model, opt_func=opt_func, loss_func=loss_func, cbs=cbs)
    def zero_grad(self):
        with torch.no_grad():
            for p in self.model.parameters(): p.grad *= self.mom

# %% ../nbs/03_learner.ipynb 32
from torch.optim.lr_scheduler import ExponentialLR

# %% ../nbs/03_learner.ipynb 33
class LRFinderCB(Callback):
    """
        Finds a suitable learning rate for the training data, by
        implementing Leslie Smith's learning rate finder algorithm. The
        learning rate is increased exponentially by a scalar until the loss 
        skyrockets, and a graph of loss vs. learning rate is returned.
    """
    def __init__(self, gamma=1.3): self.gamma = gamma
    def before_fit(self): 
        self.lrs, self.losses = [], []
        self.min = math.inf
        self.sched = ExponentialLR(self.learn.opt, self.gamma)
        
    def after_batch(self):
        if not self.learn.model.training: raise CancelEpochException()
        self.lrs.append(self.learn.opt.param_groups[0]['lr'])
        loss = to_cpu(self.learn.loss)
        self.losses.append(loss)
        if loss < self.min: self.min = loss
        if loss > self.min*3: 
            plt.plot(self.lrs, self.losses)
            plt.xscale('log')
            plt.xlabel('Learning Rate')
            plt.ylabel('Loss')
            raise CancelFitException()
        self.sched.step()
