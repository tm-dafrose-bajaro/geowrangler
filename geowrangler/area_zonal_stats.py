# AUTOGENERATED! DO NOT EDIT! File to edit: notebooks/06_area_zonal_stats.ipynb (unless otherwise specified).

__all__ = ["create_area_zonal_stats"]


# Cell
from typing import Any, Dict, List

import geopandas as gpd
import numpy as np
import geowrangler.vector_zonal_stats as vzs
from .vector_zonal_stats import GEO_INDEX_NAME

# Internal Cell
def extract_func(func):
    # extra by default is none
    extra = []
    # extra can contain either raw, data or aoi
    if func.__contains__("raw_"):
        extra += ["raw"]
        func = func.replace("raw_", "")
    elif func.__contains__("data_"):
        extra += ["data"]
        func = func.replace("data_", "")
    elif func.__contains__("aoi_"):
        extra += ["aoi"]
        func = func.replace("aoi_", "")
    # extra can have imputed
    if func.__contains__("imputed_"):
        extra += ["imputed"]
        func = func.replace("imputed_", "")

    return func, extra


# Internal Cell


def fix_area_agg(agg):
    if "func" not in agg:
        return agg  # skip fix as agg spec is invalid

    if type(agg["func"]) == str:
        agg["func"] = [agg["func"]]

    real_funcs = []
    func_extras = []
    for func in agg["func"]:
        real_func, extra = extract_func(func)
        real_funcs += [real_func]
        func_extras += [extra]
    agg["func"] = real_funcs
    agg["extras"] = func_extras

    agg = vzs._fix_agg(agg)

    return agg


# Internal Cell


def get_source_column(agg):

    if "raw" in agg["extras"]:
        return agg["column"]  # dont use intersect column

    intersect_data_column = f"intersect_data_{agg['column']}"
    intersect_aoi_column = f"intersect_aoi_{agg['column']}"

    if "data" in agg["extras"]:
        return intersect_data_column

    if "aoi" in agg["extras"]:
        return intersect_aoi_column
    # defaults if not overridden by extra modifier
    if agg["func"] == "sum":  # sum apportions data area
        return intersect_data_column
    if agg["func"] == "mean":  # mean apportions on aoi area
        return intersect_aoi_column
    return agg["column"]  # everything else based on raw column


# Internal Cell
INTERSECT_AREA_AGG = {
    "column": "intersect_area",
    "func": "sum",
    "output": "intersect_area_sum",
    "extras": "raw",
}

# Internal Cell
def build_agg_area_dicts(aggs):
    aggs = [INTERSECT_AREA_AGG, *aggs]
    agg_dicts = {agg["output"]: (get_source_column(agg), agg["func"]) for agg in aggs}
    return agg_dicts


# Internal Cell


def validate_area_aoi(aoi):
    if aoi.crs.is_geographic:
        raise ValueError(
            f"aoi has geographic crs: {aoi.crs}, areas maybe incorrectly computed"
        )


# Internal Cell


def validate_area_data(data):
    if data.crs.is_geographic:
        raise ValueError(
            f"data has geographic crs: {data.crs}, areas maybe incorrectly computed"
        )


# Internal Cell


def expand_area_aggs(aggs):
    expanded_aggs = []
    for agg in aggs:
        for i, func in enumerate(agg["func"]):
            expanded_agg = {
                "func": func,
                "column": agg["column"],
                "output": agg["output"][i],
                "fillna": agg["fillna"][i],
                "extras": agg["extras"][i],
            }
            expanded_aggs += [expanded_agg]
    return expanded_aggs


# Internal Cell
def compute_intersect_stats(intersect, expanded_aggs):
    # optimization - use df.apply to create all new columns simultaneously
    for agg in expanded_aggs:
        if "raw" in agg["extras"]:
            continue  # skip intersect stat
        intersect_data_column = f"intersect_data_{agg['column']}"
        intersect_aoi_column = f"intersect_aoi_{agg['column']}"
        if intersect_data_column not in intersect.columns.values:
            intersect[intersect_data_column] = (
                intersect["pct_data"] * intersect[agg["column"]]
            )
        if intersect_aoi_column not in intersect.columns.values:
            intersect[intersect_aoi_column] = (
                intersect["pct_aoi"] * intersect[agg["column"]]
            )
    return intersect


# Internal Cell
def compute_imputed_stats(results, expanded_aggs):
    # optimize with df.apply
    # handle when intersect_area_sum is np.nan
    for agg in expanded_aggs:
        if "imputed" in agg["extras"]:
            results[agg["output"]] = (
                results[agg["output"]] * results["aoi_area"]
            ) / results[INTERSECT_AREA_AGG["output"]]

    return results


# Cell
def create_area_zonal_stats(
    aoi: gpd.GeoDataFrame,  # Area of interest for which zonal stats are to be computed for
    data: gpd.GeoDataFrame,  # Source gdf of region/areas containing data to compute zonal stats from
    aggregations: List[  # List of agg specs, with each agg spec applied to a data column
        Dict[str, Any]
    ] = [],
    include_intersect=True,  # Add column 'intersect_area_sum' w/ch computes total area of data areas intersecting aoi
    fix_min=True,  # Set min to zero if there are areas in aoi w/ch do not containing any intersecting area from the data.
):

    validate_area_aoi(aoi)
    validate_area_data(data)

    fixed_aggs = [fix_area_agg(agg) for agg in aggregations]

    # validate_area_aggs(fixed_aggs,data)
    vzs._validate_aggs(fixed_aggs, data)

    # reindex aoi
    aoi_index_name = aoi.index.name
    aoi = vzs._prep_aoi(aoi)
    data = data.copy()

    if not data.crs.equals(aoi.crs):
        data = data.to_crs(aoi.crs)

    # compute aoi and data areas
    aoi["aoi_area"] = aoi.geometry.area
    data["data_area"] = data.geometry.area

    # add spatial indexes
    aoi.geometry.sindex
    data.geometry.sindex

    intersect = aoi.overlay(data, keep_geom_type=True)

    # compute intersect area and percentages
    intersect["intersect_area"] = intersect.geometry.area
    intersect["pct_data"] = intersect["intersect_area"] / intersect["data_area"]
    intersect["pct_aoi"] = intersect["intersect_area"] / intersect["aoi_area"]

    expanded_aggs = expand_area_aggs(fixed_aggs)
    intersect = compute_intersect_stats(intersect, expanded_aggs)

    groups = intersect.groupby(GEO_INDEX_NAME)

    agg_area_dicts = build_agg_area_dicts(expanded_aggs)

    aggregates = groups.agg(**agg_area_dicts)

    results = aoi.merge(
        aggregates, how="left", on=GEO_INDEX_NAME, suffixes=(None, "_y")
    )

    # set min to zero if intersect area is not filled.
    if fix_min:
        for col, val in agg_area_dicts.items():
            if val[1] == "min":
                results[col] = results.apply(
                    lambda x, c: x[c]
                    if np.isclose(x["aoi_area"], x["intersect_area_sum"])
                    else 0.0,
                    axis=1,
                    c=col,  # kwarg to pass to lambda
                )

    vzs._fillnas(expanded_aggs, results, aoi)

    results = compute_imputed_stats(results, expanded_aggs)
    drop_labels = ["aoi_area"]
    if not include_intersect:
        drop_labels += [INTERSECT_AREA_AGG["output"]]
    results.drop(labels=drop_labels, inplace=True, axis=1)

    results.set_index(GEO_INDEX_NAME, inplace=True)
    results.index.name = aoi_index_name
    return results