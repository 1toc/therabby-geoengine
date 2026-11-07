"""Conservative texture enhancement inside surveyed GLB UV surface polygons.

The polygons come from the existing mesh UV vertices, not inferred wall shapes.
No geometric features are added. Pillow is a development-only dependency.
"""
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter


def enhance_surface(source, polygon):
    source = source.convert('RGB')
    mask = Image.new('L', source.size, 0)
    ImageDraw.Draw(mask).polygon(polygon, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(1.3))
    # Modest contrast and local edge enhancement retain original windows/signs.
    detail = ImageEnhance.Contrast(source).enhance(1.04)
    detail = detail.filter(ImageFilter.UnsharpMask(radius=1.5, percent=110, threshold=5))
    return Image.composite(detail, source, mask)
