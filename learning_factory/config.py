from pathlib import Path
import yaml

REQUIRED_KEYS = ["meta","resources","buffers","forward_flow","reverse_flow","rules"]

def load_config(path: str | Path) -> dict:
    p = Path(path)
    cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED_KEYS if k not in cfg]
    if missing:
        raise ValueError(f"Config missing keys: {missing}")
    return cfg
