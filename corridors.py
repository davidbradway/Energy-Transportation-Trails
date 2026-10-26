"""Split Duke Energy easement parcels into trail-sized corridor segments and score each one's
feasibility as a bike/hike trail.

All inputs are GeoDataFrames in NC State Plane feet (see build.py).
"""

import geopandas as gpd
import numpy as np
import pandas as pd

SEGMENT_FT = 2640  # target segment length: half a mile
MIN_SEGMENT_FT = 660  # shorter leftovers are merged into a neighboring segment
TOUCH_FT = 5  # parcels this close together count as one continuous corridor
REACH_FT = 500  # a segment within this distance of a facility "connects" to it
NETWORK_SNAP_FT = 50  # existing facilities this close together form one network
PARALLEL_FT = 300  # planned facilities this close "run alongside" a segment
MIN_WIDTH_FT, FULL_WIDTH_FT = 20, 50  # 12 ft trail (Duke's max) plus clearance -> room to spare
FEW_DEEDS, MANY_DEEDS = 2, 12  # easement deeds per mile: each is a separate negotiation

WEIGHTS = {"connectivity": 35, "landowners": 20, "planned": 15, "width": 15, "length": 15}
SERVICE_FACTOR = {"Electric": 1.0, "Gas": 0.5}  # paving over gas lines may be restricted
TIERS = [(60, "High"), (40, "Medium"), (0, "Low")]


def corridor_length(geoms):
    """Length of the rectangle with the same area and perimeter as each shape."""
    half_perimeter = geoms.length / 2
    return (half_perimeter + np.sqrt(np.maximum(half_perimeter**2 - 4 * geoms.area, 0))) / 2


def neighbors(parcels):
    """Map each parcel index to the set of parcels it touches."""
    buffered = gpd.GeoDataFrame(geometry=parcels.buffer(TOUCH_FT), crs=parcels.crs)
    pairs = gpd.sjoin(buffered, parcels[["geometry"]], predicate="intersects")
    pairs = pairs[pairs.index != pairs["index_right"]]
    found = pairs.groupby(level=0)["index_right"].apply(set)
    return {i: found.get(i, set()) for i in parcels.index}


def segment(parcels):
    """Group touching parcels into contiguous runs of about SEGMENT_FT.

    Returns (segment id, corridor id) Series indexed like parcels. A corridor is a connected
    set of parcels; segments are pieces of one corridor.
    """
    nbrs = neighbors(parcels)
    length = parcels["length_ft"]
    seg, corridor, seg_len = {}, {}, {}
    n = c = 0
    # Walk each corridor depth-first from an end parcel, starting a new segment when the
    # current one is long enough or the walk jumps back to a branch.
    for start in sorted(parcels.index, key=lambda i: len(nbrs[i])):
        if start in seg:
            continue
        c += 1
        stack, prev = [start], None
        while stack:
            i = stack.pop()
            if i in seg:
                continue
            if prev is None or i not in nbrs[prev] or seg_len[n] >= SEGMENT_FT:
                n += 1
                seg_len[n] = 0
            seg[i], corridor[i], prev = n, c, i
            seg_len[n] += length[i]
            stack.extend(j for j in nbrs[i] if j not in seg)

    # Fold short leftovers (branch stubs, corridor ends) into their shortest neighbor.
    for s in sorted(seg_len, key=seg_len.get):
        if seg_len[s] >= MIN_SEGMENT_FT:
            continue
        members = [i for i in seg if seg[i] == s]
        options = {seg[j] for i in members for j in nbrs[i]} - {s}
        if options:
            target = min(options, key=seg_len.get)
            for i in members:
                seg[i] = target
            seg_len[target] += seg_len.pop(s)

    return pd.Series(seg), pd.Series(corridor)


def names_near(segs, lines, distance):
    """'; '-joined names of the lines within distance of each segment."""
    reach = gpd.GeoDataFrame(geometry=segs.buffer(distance), crs=segs.crs)
    hits = gpd.sjoin(reach, lines[lines["name"].notna()][["name", "geometry"]], predicate="intersects")
    names = hits.groupby(level=0)["name"].apply(lambda s: "; ".join(sorted(set(s))[:4]))
    return names.reindex(segs.index)


def build_segments(parcels, county, existing, planned):
    """Return scored corridor segments.

    parcels: easement polygons with OBJECTID and Service columns
    county: Durham County polygon
    existing, planned: line layers with a name column
    """
    # Short segments are discounted by the length factor, so a short link only scores
    # well if it closes a gap between networks.
    parcels = parcels.reset_index(drop=True)
    parcels["length_ft"] = corridor_length(parcels.geometry)
    parcels["segment"], parcels["corridor"] = segment(parcels)

    # Keep only corridors that reach into the county.
    inside = parcels.intersects(county.union_all())
    parcels = parcels[parcels["corridor"].isin(parcels.loc[inside, "corridor"])]

    # Measure the merged shape, so overlapping parcels aren't counted twice.
    segs = parcels.dissolve(
        by="segment", aggfunc={"OBJECTID": "count", "Service": lambda s: s.mode()[0]},
    ).rename(columns={"OBJECTID": "deeds", "Service": "service"})
    segs["length_ft"] = corridor_length(segs.geometry)
    segs["width_ft"] = segs.area / segs["length_ft"]
    segs["deeds_per_mile"] = segs["deeds"] / (segs["length_ft"] / 5280)

    # Connectivity: how many separate trail/bike networks the segment reaches. Planned
    # facilities count too, since linking two planned projects closes a future gap.
    network = pd.concat([existing, planned])
    blobs = gpd.GeoDataFrame(
        geometry=[network.buffer(NETWORK_SNAP_FT).union_all()], crs=network.crs
    ).explode(index_parts=False).reset_index(drop=True)
    reach = gpd.GeoDataFrame(geometry=segs.buffer(REACH_FT), crs=segs.crs)
    hits = gpd.sjoin(reach, blobs, predicate="intersects")
    segs["networks"] = hits.groupby(level=0)["index_right"].nunique().reindex(segs.index, fill_value=0)

    # Planned facilities: share of the segment they run alongside, or at least touch.
    alongside = segs.intersection(planned.buffer(PARALLEL_FT).union_all()).area / segs.area
    touches = segs.buffer(REACH_FT).intersects(planned.union_all())

    points = pd.DataFrame({
        "connectivity": segs["networks"].map(lambda k: 0 if k == 0 else 0.6 if k == 1 else 1.0),
        "landowners": (MANY_DEEDS - segs["deeds_per_mile"]) / (MANY_DEEDS - FEW_DEEDS),
        "planned": np.maximum(alongside / 0.5, np.where(touches, 0.5, 0)),
        "width": (segs["width_ft"] - MIN_WIDTH_FT) / (FULL_WIDTH_FT - MIN_WIDTH_FT),
        "length": segs["length_ft"] / SEGMENT_FT,
    }).clip(0, 1)
    for factor, weight in WEIGHTS.items():
        segs[f"pts_{factor}"] = (points[factor] * weight).round().astype(int)
    pts = segs[[f"pts_{f}" for f in WEIGHTS]].sum(axis=1)
    segs["score"] = (pts * segs["service"].map(SERVICE_FACTOR).fillna(1)).round().astype(int)
    segs["tier"] = segs["score"].map(lambda s: next(t for cut, t in TIERS if s >= cut))

    segs["connects"] = names_near(segs, existing, REACH_FT)
    segs["planned"] = names_near(segs, planned, REACH_FT)
    segs["trail_inside_ft"] = segs.intersection(existing.union_all()).length.round()
    segs["in_county"] = segs.intersects(county.union_all())
    segs["miles"] = (segs["length_ft"] / 5280).round(2)
    segs["width_ft"] = segs["width_ft"].round()
    segs["deeds_per_mile"] = segs["deeds_per_mile"].round(1)

    segs = segs.sort_values("score", ascending=False).reset_index(drop=True)
    segs.insert(0, "id", segs.index + 1)
    return segs.drop(columns="length_ft")
