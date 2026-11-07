"""Register an AI wall repaint to its rectified polygon reference without UV changes."""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def align(reference, repaint, output):
    with Image.open(reference) as image:
        original = np.asarray(image.convert('RGB'))
    with Image.open(repaint) as image:
        resized = image.convert('RGB').resize((original.shape[1], original.shape[0]), Image.Resampling.LANCZOS)
        generated = np.asarray(resized).copy()
    inside = original.max(axis=2) > 8
    gap = inside & (generated.max(axis=2) < 8)
    generated[gap] = original[gap]
    generated[~inside] = 0
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(generated).save(output)
    return {"source_size": [original.shape[1], original.shape[0]],
            "valid_pixels": int(inside.sum()), "fallback_pixels": int(gap.sum()),
            "fallback_fraction": round(float(gap.sum()/max(inside.sum(),1)), 5)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--reference', required=True)
    parser.add_argument('--repaint', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(align(args.reference, args.repaint, args.output), indent=2))
