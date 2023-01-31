# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/01_conv.ipynb.

# %% auto 0
__all__ = ['ConvNormAct', 'ResnetStem', 'BottleneckBlock', 'ResnetStage', 'ResnetNN']

# %% ../nbs/01_conv.ipynb 1
from torch import nn

# %% ../nbs/01_conv.ipynb 4
class ConvNormAct(nn.Sequential):
    def __init__(
        self,
        in_channels,
        out_channels,
        kernel_size=3,
        bias=True,
        stride=2,
        act=True
    ):
        super().__init__(
            nn.Conv2d(in_channels, out_channels, kernel_size=kernel_size, stride=stride, padding=kernel_size//2, bias=bias),
            nn.BatchNorm2d(out_channels),
            nn.ReLU() if act else None
        )

# %% ../nbs/01_conv.ipynb 6
class ResnetStem(nn.Sequential):
    def __init__(
        self,
        stem_sizes: list # stem block channel sizes — [32, 32, 64] common
    ):
        super().__init__(
            *[
                ConvNormAct(
                    in_channels=stem_sizes[i],
                    out_channels=stem_sizes[i+1],
                    kernel_size=3,
                    stride=2 if i==0 else 1
                )
            for i in range(len(stem_sizes) - 1)
            ],
            nn.MaxPool2d(kernel_size=3, stride=2, padding=1)
        )

# %% ../nbs/01_conv.ipynb 7
class BottleneckBlock(nn.Module):
    def __init__(
        self,
        in_channels,
        out_channels,
        reduction=4,
        stride=1
    ):
        super().__init__()
        reduced_features = out_channels // reduction
        
        self.block = nn.Sequential(
            ConvNormAct(in_channels, reduced_features, kernel_size=1, stride=stride), # <----- including stride enables us to stride on this layer
            ConvNormAct(reduced_features, reduced_features, kernel_size=3),
            ConvNormAct(reduced_features, out_channels, kernel_size=1)
        )
        
        self.shortcut = (
            nn.Sequential(
                ConvNormAct(in_channels, out_channels, kernel_size=1)
            ) if in_channels != out_channels else nn.Identity()
        )
        
        self.pool = (
            nn.AvgPool2d(kernel_size=3, stride=stride, padding=1) 
            if stride != 1 else nn.Identity()
        )
        
    def forward(self, x):
        residual = x
        x = self.block(x)
        residual = self.shortcut(self.pool(residual))
        x += residual
        return x

# %% ../nbs/01_conv.ipynb 8
class ResnetStage(nn.Sequential):
    def __init__(
        self,
        in_channels,
        out_channels,
        depth,
        stride=2
    ):
        super().__init__(
            BottleneckBlock(in_channels, out_channels, stride=2),
            *[
                BottleneckBlock(out_channels, out_channels)
                for i in range(depth - 1)
            ]
        )

# %% ../nbs/01_conv.ipynb 9
class ResnetNN(nn.Module):
    def __init__(
        self,
        img_channels,
        stem_sizes,
        widths,
        depths,
        num_classes
    ):
        super().__init__()
        stem_sizes = [img_channels, *stem_sizes]
        self.stem = ResnetStem(stem_sizes)
        
        self.stages = nn.ModuleList(
            [
                ResnetStage(stem_sizes[-1], widths[0], depths[0], stride=1),
                *[
                    ResnetStage(widths[i], widths[i+1], depths[i+1])
                    for i in range(len(widths) - 1)
                ]
            ]   
        )
        
        self.avgpool = nn.AdaptiveAvgPool2d((1, 1))
        self.fc = nn.Linear(widths[-1], num_classes)
        
    def forward(self, x):
        x = self.stem(x)
        for stage in self.stages:
            x = stage(x)
        x = self.avgpool(x)
        x = torch.flatten(x, 1)
        x = self.fc(x)
        return x
