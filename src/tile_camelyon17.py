"""Make a tissue mask and extract calibrated tiles from one local CAMELYON17 slide."""

import io
import json
import math
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import perf_counter
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from matplotlib.path import Path as PolygonPath
import numpy as np
import openslide
import pandas as pd
from PIL import Image, ImageDraw, ImageFilter

TARGET_MPP = 0.5
TILE_PX = 256
MASK_MPP = 8.0
MIN_TISSUE = 0.5
JPEG_QUALITY = 90


def tissue_mask(overview):
    """Detect pink and purple stain in the RGB overview. Each mask pixel is 0 or 255."""
    red, green, blue = np.asarray(overview, dtype=np.int16).transpose(2, 0, 1)
    bright = np.maximum(np.maximum(red, green), blue)
    dark = np.minimum(np.minimum(red, green), blue)
    stained = (bright >= 40) & (bright - dark >= 15) & (np.minimum(red, blue) - green >= 3)
    return Image.fromarray(stained.astype("uint8") * 255).filter(ImageFilter.MedianFilter(3))


def tile_grid(mask, dimensions, mpp_x, mpp_y):
    """Return complete, non-overlapping level-0 boxes that pass the overview mask."""
    width, height = dimensions
    field_um = TILE_PX * TARGET_MPP

    def edges(length, mpp):
        count = math.floor(length * mpp / field_um)
        return np.rint(np.arange(count + 1) * field_um / mpp).astype(int)

    xs, ys = edges(width, mpp_x), edges(height, mpp_y)
    mx = np.rint(xs * mask.width / width).astype(int)
    my = np.rint(ys * mask.height / height).astype(int)
    if np.any(np.diff(mx) <= 0) or np.any(np.diff(my) <= 0):
        raise ValueError("The overview is too coarse to measure tissue in these tiles.")

    # An integral image counts mask pixels in any rectangular window.
    pixels = np.asarray(mask) != 0
    integral = np.zeros((mask.height + 1, mask.width + 1), dtype=np.int32)
    np.cumsum(pixels, axis=0, dtype=np.int32, out=integral[1:, 1:])
    np.cumsum(integral[1:, 1:], axis=1, out=integral[1:, 1:])
    corners = integral[np.ix_(my, mx)]
    counts = np.diff(np.diff(corners, axis=0), axis=1)
    fractions = counts / (np.diff(my)[:, None] * np.diff(mx))
    rows, cols = np.nonzero(fractions >= MIN_TISSUE)
    return pd.DataFrame({
        "x0": xs[cols], "y0": ys[rows], "x1": xs[cols + 1], "y1": ys[rows + 1],
        "mask_fraction": fractions[rows, cols],
    }), fractions.size


def read_box(slide, box, level, size):
    """Read level-0 box [x0, x1) by [y0, y1) into an RGB image of the requested size."""
    x0, y0, x1, y1 = map(int, box)
    downsample = slide.level_downsamples[level]
    width, height = (x1 - x0) / downsample, (y1 - y0) / downsample
    rgba = slide.read_region((x0, y0), level, (math.ceil(width), math.ceil(height)))
    rgb = Image.new("RGB", rgba.size, "white")
    rgb.paste(rgba, mask=rgba.getchannel("A"))
    return rgb.resize(size, Image.Resampling.LANCZOS, box=(0, 0, width, height))


def read_outlines(xml_path, dimensions):
    """Read the published ASAP polygons in the same level-0 frame as the tile boxes."""
    if xml_path is None:
        return []
    root = ET.parse(xml_path).getroot()
    outlines = []
    for item in root.findall("./Annotations/Annotation"):
        group = item.get("PartOfGroup")
        if item.get("Type") != "Polygon" or group not in {"Tumor", "Exclusion"}:
            raise ValueError(f"Unrecognized annotation in {xml_path}")
        ordered = sorted(item.findall("./Coordinates/Coordinate"), key=lambda p: int(p.get("Order")))
        xy = np.array([(float(p.get("X")), float(p.get("Y"))) for p in ordered])
        if (len(xy) < 3 or not np.isfinite(xy).all() or (xy < 0).any()
                or (xy > dimensions).any()):
            raise ValueError(f"Invalid annotation coordinates in {xml_path}")
        outlines.append((group, xy))
    if root.tag != "ASAP_Annotations" or not any(group == "Tumor" for group, _ in outlines):
        raise ValueError(f"Expected at least one tumor outline in {xml_path}")
    return outlines


def centers_in_tumor(tiles, outlines):
    centers = (tiles[["x0", "y0"]].to_numpy() + tiles[["x1", "y1"]].to_numpy()) / 2
    inside = {name: np.zeros(len(tiles), dtype=bool) for name in ("Tumor", "Exclusion")}
    for group, xy in outlines:
        nearby = ((centers >= xy.min(axis=0)) & (centers <= xy.max(axis=0))).all(axis=1)
        inside[group][nearby] |= PolygonPath(xy).contains_points(centers[nearby])
    return inside["Tumor"] & ~inside["Exclusion"]


def qc_detail(slide, tiles, outlines):
    """Draw the retained grid in a local field around one of the saved tiles."""
    focus = tiles.iloc[len(tiles) // 2]
    enclosed = None if not outlines else False
    if outlines:
        inside = tiles.loc[tiles["center_in_tumor"]]
        if len(inside):
            # Prefer a fully enclosed tile close enough to a border to show both.
            border = next(xy[0] for group, xy in outlines if group == "Tumor")
            centers = (inside[["x0", "y0"]].to_numpy() + inside[["x1", "y1"]].to_numpy()) / 2
            nearest = np.argsort(((centers - border) ** 2).sum(axis=1), kind="stable")
            focus = inside.iloc[nearest[0]]
            starts = np.concatenate([xy for _, xy in outlines])
            ends = np.concatenate([np.roll(xy, -1, axis=0) for _, xy in outlines])
            low, high = np.minimum(starts, ends), np.maximum(starts, ends)
            for index in nearest:
                candidate = inside.iloc[index]
                # If even the segments' bounding boxes miss the tile, neither a
                # tumor boundary nor an exclusion boundary can enter its interior.
                touches = ((high[:, 0] >= candidate.x0) & (low[:, 0] <= candidate.x1)
                           & (high[:, 1] >= candidate.y0) & (low[:, 1] <= candidate.y1))
                if not touches.any():
                    focus, enclosed = candidate, True
                    break
    tw, th = int(focus.x1 - focus.x0), int(focus.y1 - focus.y0)
    width, height = slide.dimensions
    left, top = max(0, int(focus.x0) - 3 * tw), max(0, int(focus.y0) - 3 * th)
    right, bottom = min(width, left + 7 * tw), min(height, top + 7 * th)
    canvas = 700
    scale = canvas / max(right - left, bottom - top)
    size = (max(1, round((right - left) * scale)), max(1, round((bottom - top) * scale)))
    level = slide.get_best_level_for_downsample(1 / scale)
    detail = read_box(slide, (left, top, right, bottom), level, size)
    draw = ImageDraw.Draw(detail)
    sx, sy = size[0] / (right - left), size[1] / (bottom - top)

    def point(x, y):
        return (round((x - left) * sx), round((y - top) * sy))

    visible = tiles[(tiles.x0 < right) & (tiles.x1 > left) & (tiles.y0 < bottom) & (tiles.y1 > top)]
    for tile in visible.itertuples():
        draw.rectangle([point(tile.x0, tile.y0), point(tile.x1, tile.y1)], outline="#167A8B", width=2)
    for group, xy in outlines:
        points = [point(x, y) for x, y in xy]
        draw.line(points + [points[0]], fill="#FF552C" if group == "Tumor" else "#8C4BB8", width=4)
    draw.rectangle([point(focus.x0, focus.y0), point(focus.x1, focus.y1)], outline="#FFCC00", width=5)
    return detail, focus.filename, (left, top, right, bottom), enclosed


def extract_slide(row, raw_dir, output_dir):
    """Write one complete archive per slide. The input must already be present locally."""
    start = perf_counter()
    slide_id = row["slide_id"]
    image_path = raw_dir / "images" / slide_id
    if image_path.stat().st_size != int(row["image_bytes"]):
        raise ValueError(f"Image size differs from the selection manifest for {slide_id}")
    xml_path = raw_dir / "annotations" / Path(row["annotation_key"]).name if row["annotation_key"] else None
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / (image_path.stem + ".zip")
    with NamedTemporaryFile(dir=output_dir, suffix=".partial", delete=False) as tmp:
        temporary = Path(tmp.name)
    try:
        with openslide.OpenSlide(image_path) as slide, ZipFile(temporary, "w") as archive:
            mpp_x = float(slide.properties.get(openslide.PROPERTY_NAME_MPP_X, "nan"))
            mpp_y = float(slide.properties.get(openslide.PROPERTY_NAME_MPP_Y, "nan"))
            if not all(math.isfinite(v) and v > 0 for v in (mpp_x, mpp_y)):
                raise ValueError(f"Missing or invalid physical pixel size for {slide_id}")
            width, height = slide.dimensions
            overview = slide.get_thumbnail((round(width * mpp_x / MASK_MPP), round(height * mpp_y / MASK_MPP)))
            mask = tissue_mask(overview)
            tiles, candidates = tile_grid(mask, slide.dimensions, mpp_x, mpp_y)
            if tiles.empty:
                raise ValueError(f"No tiles passed the tissue mask on {slide_id}")
            level = slide.get_best_level_for_downsample(min(TARGET_MPP / mpp_x, TARGET_MPP / mpp_y))
            outlines = read_outlines(xml_path, slide.dimensions)
            tiles["center_in_tumor"] = centers_in_tumor(tiles, outlines) if outlines else pd.NA
            tiles["filename"] = [f"tiles/x{x}_y{y}.jpg" for x, y in zip(tiles.x0, tiles.y0)]

            jpeg_bytes = 0
            for tile in tiles.itertuples():
                rgb = read_box(slide, (tile.x0, tile.y0, tile.x1, tile.y1), level, (TILE_PX, TILE_PX))
                encoded = io.BytesIO()
                rgb.save(encoded, "JPEG", quality=JPEG_QUALITY, subsampling=0)
                jpeg_bytes += encoded.tell()
                archive.writestr(tile.filename, encoded.getvalue())

            detail, example, detail_box, enclosed = qc_detail(slide, tiles, outlines)
            with archive.open("mask.png", "w") as stream:
                mask.save(stream, "PNG")
            overview.thumbnail((1100, 1100))
            with archive.open("overview.png", "w") as stream:
                overview.save(stream, "PNG")
            with archive.open("grid_detail.png", "w") as stream:
                detail.save(stream, "PNG")
            archive.writestr("tiles.csv", tiles.to_csv(index=False))
            stats = dict(slide_id=slide_id, hospital=int(row["hospital"]), label=row["label"],
                         image_bytes=int(row["image_bytes"]), width=width, height=height,
                         mpp_x=mpp_x, mpp_y=mpp_y, target_mpp=TARGET_MPP, tile_px=TILE_PX,
                         read_level=level, level_downsample=slide.level_downsamples[level],
                         mask_width=mask.width, mask_height=mask.height, mask_target_mpp=MASK_MPP,
                         mask_min_fraction=MIN_TISSUE, mask_slide_fraction=float(np.mean(np.asarray(mask) > 0)),
                         full_grid_boxes=int(candidates), tiles=len(tiles), jpeg_bytes=jpeg_bytes,
                         jpeg_quality=JPEG_QUALITY, jpeg_subsampling="4:4:4",
                         centers_in_tumor=int(tiles["center_in_tumor"].sum()) if outlines else None,
                         example_file=example, example_enclosed=enclosed, detail_box=detail_box,
                         seconds=perf_counter() - start)
            archive.writestr("summary.json", json.dumps(stats, indent=2, allow_nan=False))
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return stats
