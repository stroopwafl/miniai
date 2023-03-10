# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/01_datasets.ipynb.

# %% auto 0
__all__ = ['inplace', 'collate_dict', 'DataLoaders']

# %% ../nbs/01_datasets.ipynb 2
from torch.utils.data import DataLoader, default_collate
from operator import itemgetter
from fastcore import docments

# %% ../nbs/01_datasets.ipynb 5
def inplace(f):
    """
        Performs dataset operations in place. To be used as a
        decorator
    """
    def _f(b):
        f(b)
        return b
    return _f

# %% ../nbs/01_datasets.ipynb 8
def collate_dict(ds):
    """
        Takes a dataset dictionary and returns datasets as a tuple. Usually
        used when calling the Pytorch DataLoader object.
    """
    get = itemgetter(*ds.features)
    def _f(b): return get(default_collate(b))
    return _f

# %% ../nbs/01_datasets.ipynb 10
class DataLoaders:
    """
        Establishes DataLoader objects for training and validation sets,
        and optionally returns them as a tuple.
    """
    def __init__(
        self, 
        *dsd # 
    ): 
        self.train, self.valid = dsd[:2]
    
    @classmethod
    def from_dd(
        cls, 
        dd, # Dataset dict object (works with hugging face datasets) 
        batch_size: int, # Batch size for the dataloader
        as_tuple: bool=True, # If true, returns a tuple of dataloaders like (train, valid)
        num_workers: int=4 # Number of CPUs used in parallel
    ):
        return cls(*[DataLoader(ds, batch_size, num_workers=num_workers, collate_fn=collate_dict(ds) if as_tuple else default_collate) for ds in dd.values()])
