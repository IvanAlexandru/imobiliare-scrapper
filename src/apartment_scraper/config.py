import yaml
from shapely.geometry import shape

def load(path="config.yaml"):
    with open(path) as f:
        c = yaml.safe_load(f)
    p = shape(c["filters"]["polygon"])
    if p.geom_type != "Polygon" or not p.is_valid or p.is_empty:
        raise ValueError("Invalid polygon")
    for key in ("timeout", "interval_seconds", "max_pages", "max_details", "retries"):
        if c["http"][key] <= 0:
            raise ValueError(f"http.{key} must be positive")
    if not any(c["websites"].values()):
        raise ValueError("Enable at least one source")
    return c
