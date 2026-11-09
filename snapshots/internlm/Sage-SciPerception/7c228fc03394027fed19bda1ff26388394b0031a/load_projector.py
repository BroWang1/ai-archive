"""Download and load released Sage Sci Perception projectors."""
import json
from pathlib import Path

from safetensors.torch import load_file

from modeling_projector import build


def download_projector(projector_id, repo_id='internlm/Sage-SciPerception',
                       revision='main', local_dir=None, cache_dir=None):
    """Resolve a projector through the repository index and download its files."""
    from huggingface_hub import hf_hub_download

    index_path = Path(hf_hub_download(repo_id, 'config.json', revision=revision,
                                    cache_dir=cache_dir))
    index = json.loads(index_path.read_text())
    component = index['projectors'][projector_id]
    # Pin component files to the same snapshot as the index.
    resolved_revision = index_path.parent.name
    if local_dir is not None:
        destination = Path(local_dir)
        destination.mkdir(parents=True, exist_ok=True)
        (destination / 'config.json').write_bytes(index_path.read_bytes())
    config_path = Path(hf_hub_download(
        repo_id, component + '/config.json', revision=resolved_revision,
        local_dir=local_dir, cache_dir=cache_dir,
    ))
    config = json.loads(config_path.read_text())
    hf_hub_download(repo_id, component + '/' + config['weights'],
                    revision=resolved_revision, local_dir=local_dir, cache_dir=cache_dir)
    return config_path.parent


def load_projector(directory, device='cpu'):
    directory = Path(directory)
    config = json.loads((directory / 'config.json').read_text())
    model = build(config['projector'], config['output_dim'])
    state = load_file(str(directory / config['weights']), device='cpu')
    model.load_state_dict(state, strict=True)
    return model.to(device).requires_grad_(False).eval(), config


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Download a projector selected from the repository index.')
    parser.add_argument('projector_id', help='backbone/modality/task, as listed in the root config.json')
    parser.add_argument('--repo-id', default='internlm/Sage-SciPerception')
    parser.add_argument('--revision', default='main')
    parser.add_argument('--local-dir', type=Path)
    args = parser.parse_args()
    print(download_projector(args.projector_id, repo_id=args.repo_id,
                             revision=args.revision, local_dir=args.local_dir))
