# gis_mcp_server.py
# GIS-focused MCP server exposing tools for DEM ingest, terrain derivation,
# hydro/lake vector ingest, buffering & clipping, and handy exports.
# Uses FastMCP from the official MCP Python SDK. [1](https://pypi.org/project/mcp/)

from __future__ import annotations
import os, io, json, tempfile, zipfile, shutil, math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Literal

import requests
import geopandas as gpd
from shapely.geometry import shape, mapping
from shapely.ops import unary_union
from pyproj import CRS

import numpy as np
import rasterio as rio
from rasterio.mask import mask

from mcp.server.fastmcp import FastMCP, Context  # FastMCP server API. [1](https://pypi.org/project/mcp/)

DATA_DIR = Path(os.environ.get("GIS_MCP_DATA_DIR", "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

mcp = FastMCP(
    name="Bengaluru GIS MCP",
    json_response=True,  # return structured JSON results to clients. [2](https://github.com/modelcontextprotocol/python-sdk)
)

# -----------------------------
# Utility helpers
# -----------------------------
def _save_bytes(content: bytes, suffix: str) -> str:
    f = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=DATA_DIR)
    f.write(content)
    f.flush(); f.close()
    return f.name

def _ensure_gdf_epsg4326(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        # Assume EPSG:4326 if no CRS; caller should provide proper CRS in production.
        gdf.set_crs(epsg=4326, inplace=True)
    else:
        gdf = gdf.to_crs(epsg=4326)
    return gdf

# -----------------------------
# Raster (DEM) tools
# -----------------------------
@mcp.tool()
def download_dem_from_url(url: str, filename_hint: str = "dem.tif") -> dict:
    """
    Download a DEM (GeoTIFF) from a public URL (e.g., OpenTopography SRTM/ALOS)
    and store it under data/. Returns path and basic metadata.
    """
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    out_path = DATA_DIR / filename_hint
    with open(out_path, "wb") as f:
        f.write(r.content)
    with rio.open(out_path) as src:
        return {
            "path": str(out_path),
            "crs": src.crs.to_string() if src.crs else None,
            "bounds": src.bounds._asdict(),
            "res": src.res,
            "width": src.width,
            "height": src.height,
        }

@mcp.tool()
def clip_dem_to_geojson(dem_path: str, aoi_geojson: str, crop: bool = True) -> dict:
    """
    Clip a DEM using an AOI polygon (GeoJSON Feature/FeatureCollection).
    """
    aoi = json.loads(aoi_geojson)
    geoms = []
    if aoi.get("type") == "FeatureCollection":
        for f in aoi["features"]:
            geoms.append(shape(f["geometry"]))
    elif aoi.get("type") == "Feature":
        geoms.append(shape(aoi["geometry"]))
    else:
        geoms.append(shape(aoi))  # raw geometry

    with rio.open(dem_path) as src:
        out_image, out_transform = mask(src, [mapping(unary_union(geoms))], crop=crop)
        out_meta = src.meta.copy()
        out_meta.update({
            "driver": "GTiff",
            "height": out_image.shape[1],
            "width": out_image.shape[2],
            "transform": out_transform
        })
    clipped_path = str(DATA_DIR / (Path(dem_path).stem + "_clipped.tif"))
    with rio.open(clipped_path, "w", **out_meta) as dest:
        dest.write(out_image)
    return {"path": clipped_path, "meta": out_meta}

@mcp.tool()
def compute_slope_aspect(dem_path: str) -> dict:
    """
    Compute slope (degrees) and aspect (degrees) from a DEM using simple
    Horn-like gradients (approx). Saves two GeoTIFFs.
    """
    with rio.open(dem_path) as src:
        dem = src.read(1, masked=True).astype("float64")
        # Pixel size in georeferenced units:
        xres, yres = src.res
        # Compute gradients:
        gy, gx = np.gradient(dem.filled(np.nan), yres, xres)
        slope_rad = np.arctan(np.hypot(gx, gy))
        slope_deg = np.degrees(slope_rad)
        aspect = (np.degrees(np.arctan2(-gx, gy)) + 360.0) % 360.0

        meta = src.meta.copy()
        meta.update(dtype="float32", count=1)

        slope_path = str(DATA_DIR / (Path(dem_path).stem + "_slope.tif"))
        with rio.open(slope_path, "w", **meta) as dst:
            dst.write(slope_deg.astype("float32"), 1)

        aspect_path = str(DATA_DIR / (Path(dem_path).stem + "_aspect.tif"))
        with rio.open(aspect_path, "w", **meta) as dst:
            dst.write(aspect.astype("float32"), 1)

    return {"slope_path": slope_path, "aspect_path": aspect_path}

# -----------------------------
# Vector tools (hydrology, lakes, admin boundaries)
# -----------------------------
@mcp.tool()
def load_vector_from_url(url: str, file_hint: str = "vector.geojson") -> dict:
    """
    Download a vector dataset (GeoJSON or zipped shapefile) and save to data/.
    Returns canonical saved GeoJSON path.
    """
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    local = DATA_DIR / file_hint
    with open(local, "wb") as f:
        f.write(r.content)

    # If it's a zip (shapefile), extract and read
    path_to_geojson = None
    if str(local).lower().endswith(".zip"):
        zdir = DATA_DIR / (Path(file_hint).stem + "_unzipped")
        zdir.mkdir(exist_ok=True)
        with zipfile.ZipFile(local, "r") as zf:
            zf.extractall(zdir)
        # find a .shp
        shp = next(zdir.rglob("*.shp"))
        gdf = gpd.read_file(shp)
        gdf = _ensure_gdf_epsg4326(gdf)
        path_to_geojson = DATA_DIR / (Path(shp).stem + ".geojson")
        gdf.to_file(path_to_geojson, driver="GeoJSON")
    else:
        # assume geojson
        gdf = gpd.read_file(local)
        gdf = _ensure_gdf_epsg4326(gdf)
        path_to_geojson = DATA_DIR / (Path(file_hint).stem + ".geojson")
        gdf.to_file(path_to_geojson, driver="GeoJSON")

    return {"path": str(path_to_geojson), "features": len(gdf)}

@mcp.tool()
def buffer_vector(
    vector_geojson_path: str,
    distance_m: float,
    dissolve: bool = True
) -> dict:
    """
    Buffer vector features by distance (meters). Assumes EPSG:4326 input;
    temporarily projects to a local metric CRS for accurate buffering.
    """
    gdf = gpd.read_file(vector_geojson_path)
    gdf = _ensure_gdf_epsg4326(gdf)

    # Use UTM zone that roughly covers Bengaluru (UTM 43N: EPSG:32643)
    metric = CRS.from_epsg(32643)
    gdf_m = gdf.to_crs(metric)
    gdf_m["geometry"] = gdf_m.buffer(distance_m)

    if dissolve:
        gdf_m = gpd.GeoDataFrame(geometry=[unary_union(gdf_m.geometry)], crs=metric)

    out = gdf_m.to_crs(epsg=4326)
    out_path = DATA_DIR / (Path(vector_geojson_path).stem + f"_buf_{int(distance_m)}m.geojson")
    out.to_file(out_path, driver="GeoJSON")
    return {"path": str(out_path), "features": len(out)}

@mcp.tool()
def clip_vector_to_aoi(vector_geojson_path: str, aoi_geojson: str) -> dict:
    """
    Clip a vector layer to the AOI polygon (GeoJSON).
    """
    gdf = gpd.read_file(vector_geojson_path)
    gdf = _ensure_gdf_epsg4326(gdf)

    aoi = json.loads(aoi_geojson)
    if aoi.get("type") == "FeatureCollection":
        aoi_geom = unary_union([shape(f["geometry"]) for f in aoi["features"]])
    elif aoi.get("type") == "Feature":
        aoi_geom = shape(aoi["geometry"])
    else:
        aoi_geom = shape(aoi)
    aoi_gdf = gpd.GeoDataFrame(geometry=[aoi_geom], crs="EPSG:4326")

    clipped = gpd.overlay(gdf, aoi_gdf, how="intersection")
    out_path = DATA_DIR / (Path(vector_geojson_path).stem + "_clipped.geojson")
    clipped.to_file(out_path, driver="GeoJSON")
    return {"path": str(out_path), "features": len(clipped)}

# -----------------------------
# Export & housekeeping
# -----------------------------
@mcp.tool()
def list_data_dir() -> dict:
    """List files created under data/"""
    files = [str(p) for p in DATA_DIR.glob("*")]
    return {"files": files}

# -----------------------------
# A reusable MCP Prompt for agents
# -----------------------------
@mcp.prompt(title="Digital Twin Flood Data Plan")
def digital_twin_flood_data_prompt() -> str:
    """
    A prompt template that instructs an AI agent how to use GIS tools (and,
    if connected, other MCP servers) to build inputs for evacuation routing.
    """
    return """You are an orchestration agent preparing data for a DIGITAL TWIN–BASED FLOOD EVACUATION system for the Bengaluru region.

YOUR OBJECTIVE
- Assemble and preprocess terrain, hydrology, and admin layers that the optimization engine (GA/ACO/PSO) consumes to generate SAFE EVACUATION CORRIDORS and CONTINGENCY REROUTES.

AVAILABLE TOOLS (on this server)
1) download_dem_from_url(url, filename_hint) → downloads DEM GeoTIFF.
2) clip_dem_to_geojson(dem_path, aoi_geojson, crop) → clips DEM to AOI.
3) compute_slope_aspect(dem_path) → saves slope/aspect rasters.
4) load_vector_from_url(url, file_hint) → downloads GeoJSON (or zipped shapefile) and converts to GeoJSON.
5) buffer_vector(vector_geojson_path, distance_m, dissolve) → buffers lake/drain polygons or lines.
6) clip_vector_to_aoi(vector_geojson_path, aoi_geojson) → clips to AOI.
7) list_data_dir() → list outputs.

OPTIONALLY AVAILABLE SERVERS (if connected by the client; call them if present)
- OSM MCP: to query hydrology/lake polygons and drains from Overpass/OpenStreetMap.
- GTFS MCP: to ingest BMTC/BMRCL routes, stops, and headways for transit-assisted evacuation.
- Fetch MCP: to fetch public GeoJSON/CSV if raw URLs are provided.

DATA SOURCES (examples; choose one set)
- DEM: OpenTopography SRTM/ALOS tiles covering Bengaluru (30m SRTM is acceptable).
- Hydrology & Lakes: Overpass/OSM exports; KLCDA/BBMP if links are provided.
- Admin AOI: Hobli boundary GeoJSON supplied by the user (or a provided URL).

REQUIRED OUTPUTS
- dem_clipped.tif, slope.tif, aspect.tif
- lakes.geojson, lakes_buffer_75m.geojson
- drains.geojson (or waterways), drains_buffer_XXm.geojson
- OPTIONAL: ward/hobli masks; shelter sites (if a resource file is provided)
- A JSON manifest summarizing paths & metadata for the digital twin.

RECIPE (typical)
1) Get AOI GeoJSON (hobli). If only a name is provided, ask the client to supply a polygon.
2) DEM:
   - download_dem_from_url(url=<DEM URL for Bengaluru>, filename_hint="bengaluru_dem.tif")
   - clip_dem_to_geojson(dem_path=..., aoi_geojson=<hobli GeoJSON>)
   - compute_slope_aspect(dem_path=<clipped path>)
3) HYDROLOGY & LAKES:
   - load_vector_from_url(url=<OSM/KLCDA lakes GeoJSON or zip>), then buffer_vector(..., 75, dissolve=True)
   - load_vector_from_url(url=<OSM drains/waterways GeoJSON or zip>), choose buffer distance appropriate to flow
   - clip_vector_to_aoi(...) for each vector layer
4) EXPORT: Call list_data_dir() and return a JSON MANIFEST with the file paths.

RETURN a JSON plan with ordered steps (each step is {tool, args}) so the client can execute it.
If some data sources are missing, produce a best-effort plan and mark items as "optional".
"""

if __name__ == "__main__":
    # For local dev:
    # - If launched as a standalone service: HTTP/SSE is handy.
    # - When spawned by an MCP client via stdio, the client controls transport. [2](https://github.com/modelcontextprotocol/python-sdk)
    import sys
    transport = "stdio" if (len(sys.argv) > 1 and sys.argv[1] == "stdio") else "streamable-http"
    mcp.run(transport=transport)
