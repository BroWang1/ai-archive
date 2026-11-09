"""Shared MLP with learned slot identities; state keys match the exported weights."""
import math

import torch
from torch import nn


class OutputNorm(nn.Module):
    """Parameter-free RMSNorm then one learned scale, kept in log space so decay pulls toward 1."""
    def __init__(self, scale, eps=1e-12):
        super().__init__()
        self.eps = eps
        self.log_scale = nn.Parameter(torch.tensor(math.log(scale)))

    def forward(self, values):
        # Initial outputs have RMS ~1e-2 (last-layer std 0.001), so a usual 1e-6 eps would shrink them.
        values = values * torch.rsqrt(values.pow(2).mean(-1, keepdim=True) + self.eps)
        # RMS norm of a d-dim vector is sqrt(d), so divide to make `scale` the target L2 norm.
        return values * (self.log_scale.exp() / math.sqrt(values.shape[-1]))


class ResidualBlock(nn.Module):
    """Pre-LN MLP block; the zero-initialized exit makes extra depth start as the identity."""
    def __init__(self, hidden_dim, mult):
        super().__init__()
        self.norm = nn.LayerNorm(hidden_dim)
        self.up = nn.Linear(hidden_dim, hidden_dim * mult)
        self.down = nn.Linear(hidden_dim * mult, hidden_dim)
        nn.init.zeros_(self.down.weight)
        nn.init.zeros_(self.down.bias)

    def forward(self, values):
        return values + self.down(nn.functional.gelu(self.up(self.norm(values))))


class ContextResidual(nn.Module):
    """A zero-exit global readout within each scientific object, before translation to GLM."""
    def __init__(self, hidden_dim, model_dim, layers, heads):
        super().__init__()
        self.input = nn.Sequential(nn.LayerNorm(hidden_dim), nn.Linear(hidden_dim, model_dim))
        layer = nn.TransformerEncoderLayer(model_dim, heads, model_dim * 2, dropout=0.0,
                                           activation='gelu', batch_first=True, norm_first=True)
        self.encoder = nn.TransformerEncoder(layer, layers, norm=nn.LayerNorm(model_dim),
                                             enable_nested_tensor=False)
        self.output = nn.Linear(model_dim, hidden_dim)
        nn.init.zeros_(self.output.weight)
        nn.init.zeros_(self.output.bias)

    def forward(self, hidden, counts):
        if not len(hidden):
            return hidden + sum(parameter.sum() * 0 for parameter in self.parameters())
        values = self.input(hidden)
        chunks = values.split(counts.tolist())
        padded = nn.utils.rnn.pad_sequence(chunks, batch_first=True)
        valid = torch.arange(padded.shape[1], device=hidden.device)[None, :] < counts[:, None]
        encoded = self.encoder(padded, src_key_padding_mask=~valid)
        return hidden + self.output(encoded[valid])


class ClassificationReadout(nn.Module):
    """A pretrained scientific classifier followed by a trainable translation to GLM space."""
    def __init__(self, feature_dim, output_dim, classes, side_dim=0):
        super().__init__()
        self.per_atom = classes == 1  # A single output is the per-residue binary task.
        self.side_dim = side_dim
        width = (feature_dim + side_dim) * (1 if self.per_atom else 5) + (0 if self.per_atom else 1)
        self.register_buffer('feature_mean', torch.zeros(width))
        self.register_buffer('feature_std', torch.ones(width))
        self.classifier = (nn.Sequential(nn.LayerNorm(width),nn.Linear(width,256),nn.GELU(),nn.Linear(256,1))
                           if self.per_atom else nn.Sequential(nn.Linear(width,256),nn.GELU(),nn.Dropout(0.),nn.Linear(256,classes)))
        self.bridge = nn.Sequential(nn.Linear(classes,128),nn.GELU(),nn.Linear(128,output_dim))
        nn.init.zeros_(self.bridge[-1].weight)
        nn.init.zeros_(self.bridge[-1].bias)
        self.classes = classes

    def probabilities(self, values, counts, side=None):
        if not len(values):
            return values.new_empty((0,self.classes))
        if self.side_dim:
            values = torch.cat([values,side.float()],dim=-1)
        if self.per_atom:
            normalized = (values-self.feature_mean)/self.feature_std
            return self.classifier(normalized).sigmoid()
        pooled = []
        for item in values.split(counts.tolist()):
            if self.side_dim:
                # The lightcurve teacher pools joint states and measurements at floor-spaced edges.
                edges = [i*len(item)//4 for i in range(5)]
                regions = [item[left:right].mean(0) if right>left else item[min(left,len(item)-1)]
                           for left,right in zip(edges[:-1],edges[1:])]
            else:
                regions = [chunk.mean(0) if len(chunk) else item[-1] for chunk in item.tensor_split(4)]
            pooled.append(torch.cat([item.mean(0),*regions,item.new_tensor([math.log1p(len(item))])]))
        normalized = (torch.stack(pooled)-self.feature_mean)/self.feature_std
        return self.classifier(normalized).softmax(-1)

    def forward(self, values, counts, side=None):
        translated = self.bridge(self.probabilities(values,counts,side))
        return translated if self.per_atom else translated.repeat_interleave(counts,dim=0)


class BondResidualBlock(nn.Module):
    """Mean bond messages; a zero exit initially preserves the frozen node states."""
    def __init__(self, feature_dim, hidden_dim):
        super().__init__()
        self.norm = nn.LayerNorm(feature_dim)
        self.up = nn.Linear(feature_dim, hidden_dim)
        self.bond = nn.Embedding(4, hidden_dim)
        self.down = nn.Linear(hidden_dim, feature_dim)
        nn.init.normal_(self.bond.weight, std=0.02)
        nn.init.zeros_(self.down.weight)
        nn.init.zeros_(self.down.bias)

    def forward(self, values, edge_index, bond_types):
        source, target = edge_index
        messages = nn.functional.gelu(self.up(self.norm(values)[source]) + self.bond(bond_types))
        aggregate = values.new_zeros((len(values), messages.shape[-1])).index_add_(0, target, messages)
        degree = values.new_zeros(len(values)).index_add_(0, target, values.new_ones(len(target)))
        return values + self.down(aggregate / degree.clamp_min(1)[:, None])


class LeadProjector(nn.Module):
    def __init__(self, feature_dim, tokens, hidden_dim, output_dim, output_scale=None):
        super().__init__()
        self.payload_tokens = tokens
        self.feature_dim = feature_dim
        self.output_dim = output_dim
        self.identity = nn.Parameter(torch.empty(tokens, feature_dim))
        nn.init.normal_(self.identity, std=0.02)
        self.layers = nn.Sequential(nn.LayerNorm(feature_dim), nn.Linear(feature_dim, hidden_dim),
                                    nn.GELU(), nn.Linear(hidden_dim, output_dim))
        nn.init.normal_(self.layers[-1].weight, std=0.001)
        nn.init.zeros_(self.layers[-1].bias)
        self.output_norm = OutputNorm(output_scale) if output_scale else nn.Identity()

    def forward(self, values):
        return self.output_norm(self.layers(values.float() + self.identity))


class AtomProjector(nn.Module):
    def __init__(self, feature_dim, index_dim, max_atoms, hidden_dim, output_dim, output_scale=None,
                 discrete_sizes=(), discrete_dim=0, depth=0, block_mult=2, block_exit_norm=False,
                 graph_layers=0, graph_hidden_dim=128, side_dim=0, side_hidden_dim=128,
                 context_layers=0, context_dim=256, context_heads=8, readout_classes=0,
                 readout_uses_side=True):
        super().__init__()
        self.graph = nn.ModuleList(BondResidualBlock(feature_dim, graph_hidden_dim) for _ in range(graph_layers))
        self.needs_graph = bool(graph_layers)
        self.atom_index = nn.Embedding(max_atoms, index_dim)
        # The frozen GIN mixes its neighbourhood into every state; these embeddings give the
        # projector each atom's own discrete properties unmixed, in the exported column order.
        self.discrete = nn.ModuleList([nn.Embedding(size, discrete_dim) for size in discrete_sizes])
        width = feature_dim + index_dim + discrete_dim * len(self.discrete)
        # depth 0 keeps the original four-element Sequential, so earlier state keys still load.
        blocks = [ResidualBlock(hidden_dim, block_mult) for _ in range(depth)]
        # A pre-LN residual stack normalizes each block's input but never its own output, so the
        # stream reaches the exit projection unbounded: e1-stm-num-deep (depth 2, no exit norm)
        # trained to payload norms 250,000x the vocabulary rows and scored near zero. Keep the
        # flag so that run stays reproducible from its manifest; set it on every new deep arm.
        exit_norm = [nn.LayerNorm(hidden_dim)] if depth and block_exit_norm else []
        self.layers = nn.Sequential(nn.LayerNorm(width), nn.Linear(width, hidden_dim), nn.GELU(),
                                    *blocks, *exit_norm, nn.Linear(hidden_dim, output_dim))
        for embedding in (self.atom_index, *self.discrete):
            nn.init.normal_(embedding.weight, std=0.02)
        nn.init.normal_(self.layers[-1].weight, std=0.001)
        nn.init.zeros_(self.layers[-1].bias)
        self.needs_context = bool(context_layers)
        self.needs_counts = bool(context_layers or readout_classes > 1)
        if context_layers:
            self.context = ContextResidual(hidden_dim, context_dim, context_layers, context_heads)
        self.output_norm = OutputNorm(output_scale) if output_scale else nn.Identity()
        self.needs_side = bool(side_dim)
        if side_dim:
            self.side = nn.Sequential(nn.Linear(side_dim, side_hidden_dim, bias=False), nn.GELU(),
                                      nn.Linear(side_hidden_dim, output_dim, bias=False))
            nn.init.zeros_(self.side[-1].weight)
        if readout_classes:
            self.readout = ClassificationReadout(feature_dim,output_dim,readout_classes,
                                                  side_dim if readout_uses_side else 0)

    def forward(self, values, atom_indices, discrete=None, *, edge_index=None, bond_types=None, side=None, counts=None):
        values = values.float()
        if self.needs_graph:
            if edge_index is None or bond_types is None:
                raise ValueError('bond residual projector requires original graph edges and bond types')
            for block in self.graph:
                values = block(values, edge_index, bond_types)
        parts = [values, self.atom_index(atom_indices)]
        if len(self.discrete) != (0 if discrete is None else discrete.shape[-1]):
            raise ValueError('discrete atom feature columns and embeddings disagree')
        parts += [embedding(discrete[:, column]) for column, embedding in enumerate(self.discrete)]
        hidden = self.layers[:-1](torch.cat(parts, dim=-1))
        if self.needs_context:
            hidden = self.context(hidden, counts)
        output = self.layers[-1](hidden)
        if self.needs_side:
            output = output + self.side(side.float())
        if hasattr(self,'readout'):
            output = output + self.readout(values,counts,side)
        return self.output_norm(output)


class AtomSetProjector(nn.Module):
    """Atoms of one molecule attend to each other; no graph structure, no cross-molecule leak.

    The flat per-atom batch is regrouped into `[molecules, longest, model_dim]` with a key
    padding mask, so a molecule's output cannot depend on what else shares the batch.
    """
    needs_counts = True

    def __init__(self, feature_dim, index_dim, max_atoms, model_dim, layers, heads, ffn_dim,
                 output_dim, output_scale=None):
        super().__init__()
        self.atom_index = nn.Embedding(max_atoms, index_dim)
        nn.init.normal_(self.atom_index.weight, std=0.02)
        width = feature_dim + index_dim
        self.input = nn.Sequential(nn.LayerNorm(width), nn.Linear(width, model_dim))
        layer = nn.TransformerEncoderLayer(model_dim, heads, ffn_dim, dropout=0.0,
                                           activation='gelu', batch_first=True, norm_first=True)
        self.encoder = nn.TransformerEncoder(layer, layers, norm=nn.LayerNorm(model_dim),
                                             enable_nested_tensor=False)
        self.output = nn.Linear(model_dim, output_dim)
        nn.init.normal_(self.output.weight, std=0.001)
        nn.init.zeros_(self.output.bias)
        self.output_norm = OutputNorm(output_scale) if output_scale else nn.Identity()

    def forward(self, values, atom_indices, counts):
        hidden = self.input(torch.cat([values.float(), self.atom_index(atom_indices)], dim=-1))
        if hidden.shape[0] == 0:
            return self.output_norm(self.output(hidden))
        # Wrong boundaries would mix molecules without ever failing, so check them here.
        if int(counts.sum()) != hidden.shape[0] or int(counts.min()) < 1:
            raise ValueError('molecule atom counts do not partition the payload rows')
        longest = int(counts.max())
        valid = torch.arange(longest, device=hidden.device)[None, :] < counts.to(hidden.device)[:, None]
        padded = hidden.new_zeros((len(counts), longest, hidden.shape[-1]))
        padded[valid] = hidden
        encoded = self.encoder(padded, src_key_padding_mask=~valid)
        return self.output_norm(self.output(encoded[valid]))


def build(spec, output_dim, *, train_core=False, train_side_only=False):
    # output_scale is the initial L2 norm of each payload vector; absent keeps the old unnormalized output.
    scale = spec.get("output_scale")
    if spec.get('graph_layers') and spec.get('kind') != 'atom':
        raise ValueError('bond residual layers require the atom projector')
    if spec.get('side_dim') and spec.get('kind') != 'atom':
        raise ValueError('side measurements require the atom projector')
    if spec.get('context_layers') and spec.get('kind') != 'atom':
        raise ValueError('context residual requires the atom projector')
    if spec.get('readout_classes') and spec.get('kind') != 'atom':
        raise ValueError('classification readout requires the atom projector')
    if spec.get("kind") == "atom-set":
        model = AtomSetProjector(spec["feature_dim"], spec["index_dim"], spec["max_atoms"],
                                spec["model_dim"], spec["layers"], spec["heads"],
                                spec["ffn_dim"], output_dim, scale)
    elif spec.get("kind") == "atom":
        model = AtomProjector(spec["feature_dim"], spec["index_dim"], spec["max_atoms"],
                             spec["hidden_dim"], output_dim, scale,
                             spec.get("discrete_sizes") or (), spec.get("discrete_dim", 0),
                             spec.get("depth", 0), spec.get("block_mult", 2),
                             spec.get("block_exit_norm", False),
                             spec.get("graph_layers", 0), spec.get("graph_hidden_dim", 128),
                             spec.get('side_dim', 0), spec.get('side_hidden_dim', 128),
                             spec.get('context_layers', 0), spec.get('context_dim', 256),
                             spec.get('context_heads', 8), spec.get('readout_classes', 0),
                             spec.get('readout_uses_side', True))
    else:
        model = LeadProjector(spec["feature_dim"], spec["tokens"], spec["hidden_dim"], output_dim, scale)
    if spec.get('task_head_outputs'):
        model.task_head = nn.Sequential(nn.LayerNorm(output_dim), nn.Linear(output_dim, spec['task_head_outputs']))
    if spec.get('readout_classes'):
        model.requires_grad_(train_core)
        model.readout.requires_grad_(False)
        model.readout.bridge.requires_grad_(True)
        if hasattr(model,'task_head'):
            model.task_head.requires_grad_(False)
    if train_side_only:
        if not spec.get('side_dim'):
            raise ValueError('side-only training requires a scientific readout side channel')
        model.requires_grad_(False)
        model.side.requires_grad_(True)
    return model


def load_initial(model, state):
    """An original atom checkpoint may initialize only the complete non-graph core."""
    loaded = model.load_state_dict(state, strict=False)
    missing = set(loaded.missing_keys)
    for prefix in ('graph.', 'task_head.', 'side.', 'context.', 'readout.'):
        keys = {key for key in model.state_dict() if key.startswith(prefix)}
        if missing & keys and not keys <= missing:
            raise ValueError(f'incomplete projector initialization: {loaded}')
        missing -= keys
    if loaded.unexpected_keys or missing:
        raise ValueError(f'incomplete projector initialization: {loaded}')
