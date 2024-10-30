import requests
import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import Polygon, LineString, Point
import re
import pandas as pd
import os
import argparse
import math


def dms_to_dd(dms_str):
    # Convert DMS (Degrees, Minutes, Seconds) to Decimal Degrees
    dms_str = dms_str.strip()
    degrees, minutes, seconds, direction = re.split("[°'\"]+", dms_str)
    dd = float(degrees) + float(minutes) / 60 + float(seconds) / 3600
    if direction in ["S", "W"]:
        dd *= -1
    return dd


def convert_to_decimal(coord_str):
    """
    Convert a coordinate string to decimal if it's in DMS format.
    If it's already in decimal format, return it as a float.
    """
    if re.match(r'^\d{1,3}°\d{1,2}\'\d{1,2}\.\d+"[NSEW]$', coord_str.strip()):
        return dms_to_dd(coord_str)
    else:
        return float(coord_str)


def meters_to_degrees_lat(meters):
    return meters / 111320


def meters_to_degrees_lon(meters, latitude):
    return meters / (40075000 * math.cos(math.radians(latitude)) / 360)


def fetch_data_from_osm_link(osm_link):
    # Extract the type and ID from the OSM link
    id_match = re.search(r"/(node|way|relation)/(\d+)", osm_link)
    if not id_match:
        raise ValueError("Invalid OSM link. Please provide a valid OpenStreetMap link.")

    osm_type = id_match.group(1)  # 'node', 'way', or 'relation'
    osm_id = id_match.group(2)

    osm_url = f"https://www.openstreetmap.org/api/0.6/{osm_type}/{osm_id}/full.json"
    response = requests.get(osm_url)
    data = response.json()

    if "elements" not in data:
        print(f"No 'elements' in response: {data}")
        return gpd.GeoDataFrame(), []

    # Create dictionaries for nodes and ways
    node_dict = {
        element["id"]: (element["lon"], element["lat"])
        for element in data["elements"]
        if element["type"] == "node"
    }

    ways_dict = {
        element["id"]: element
        for element in data["elements"]
        if element["type"] == "way"
    }

    geometries = []
    tags_list = []

    if osm_type == "node":
        node = next(
            (
                e
                for e in data["elements"]
                if e["type"] == "node" and str(e["id"]) == osm_id
            ),
            None,
        )
        if node:
            point = Point(float(node["lon"]), float(node["lat"]))
            geometries.append(point)
            tags_list.append(
                (node.get("tags", {}), [(float(node["lon"]), float(node["lat"]))])
            )
    elif osm_type == "way":
        way = next(
            (
                e
                for e in data["elements"]
                if e["type"] == "way" and str(e["id"]) == osm_id
            ),
            None,
        )
        if way:
            points = [
                node_dict[node_id] for node_id in way["nodes"] if node_id in node_dict
            ]
            if not points:
                return gpd.GeoDataFrame(), []
            if points[0] == points[-1]:
                geometry = Polygon(points)
            else:
                geometry = LineString(points)
            geometries.append(geometry)
            tags_list.append((way.get("tags", {}), points))
    elif osm_type == "relation":
        # Handle relations (e.g., multipolygons)
        relation = next(
            (
                e
                for e in data["elements"]
                if e["type"] == "relation" and str(e["id"]) == osm_id
            ),
            None,
        )
        if relation:
            members = relation.get("members", [])
            outer_polygons = []
            inner_polygons = []
            for member in members:
                if member["type"] == "way" and member["role"] in ("outer", "inner"):
                    way_id = member["ref"]
                    way = ways_dict.get(way_id)
                    if way:
                        way_points = [
                            node_dict[node_id]
                            for node_id in way["nodes"]
                            if node_id in node_dict
                        ]
                        if not way_points:
                            continue  # Skip if no valid points
                        if way_points[0] != way_points[-1]:
                            way_points.append(way_points[0])  # Close the loop
                        poly = Polygon(way_points)
                        if member["role"] == "outer":
                            outer_polygons.append(poly)
                        else:
                            inner_polygons.append(poly)
            if outer_polygons:
                # Combine outer and inner polygons
                poly = outer_polygons[0]
                for inner_poly in inner_polygons:
                    poly = poly.difference(inner_poly)
                geometries.append(poly)
                tags_list.append((relation.get("tags", {}), list(poly.exterior.coords)))
    else:
        print(f"Unsupported OSM type: {osm_type}")
        return gpd.GeoDataFrame(), []

    if not geometries:
        return gpd.GeoDataFrame(), []

    return gpd.GeoDataFrame(geometry=geometries, crs="EPSG:4326"), tags_list


def fetch_osm_data(lat, lon, radius=200, layer="natural=water"):
    # Calculate delta degrees for latitude and longitude
    delta_lat = meters_to_degrees_lat(radius)
    delta_lon = meters_to_degrees_lon(radius, lat)

    # Define the bounding box for the radius
    bbox = f"{lat - delta_lat},{lon - delta_lon},{lat + delta_lat},{lon + delta_lon}"

    # Construct the Overpass API query dynamically
    overpass_url = "http://overpass-api.de/api/interpreter"

    # Parse the layer argument
    if "=" in layer:
        key, value = layer.split("=", 1)
        tag_filter = f'["{key}"="{value}"]'
    else:
        tag_filter = f'["{layer}"]'

    overpass_query = f"""
    [out:json];
    (
      node{tag_filter}({bbox});
      way{tag_filter}({bbox});
      relation{tag_filter}({bbox});
    );
    out body;
    >;
    out skel qt;
    """

    print(f"Overpass query:\n{overpass_query}")

    response = requests.get(overpass_url, params={"data": overpass_query})
    data = response.json()

    if "elements" not in data:
        print(f"No 'elements' in response: {data}")
        return gpd.GeoDataFrame(), []

    # Create dictionaries for nodes and ways
    node_dict = {
        element["id"]: (element["lon"], element["lat"])
        for element in data["elements"]
        if element["type"] == "node"
    }

    ways_dict = {
        element["id"]: element
        for element in data["elements"]
        if element["type"] == "way"
    }

    geometries = []
    tags_list = []

    for element in data["elements"]:
        if element["type"] == "node" and tag_filter.strip("[]") in str(
            element.get("tags", {})
        ):
            point = Point(float(element["lon"]), float(element["lat"]))
            geometries.append(point)
            tags_list.append(
                (
                    element.get("tags", {}),
                    [(float(element["lon"]), float(element["lat"]))],
                )
            )
        elif element["type"] == "way":
            points = [node_dict.get(node_id) for node_id in element["nodes"]]
            points = [pt for pt in points if pt is not None]  # Filter out None values
            if points:
                if points[0] == points[-1]:  # Closed loop
                    geometry = Polygon(points)
                else:
                    geometry = LineString(points)
                geometries.append(geometry)
                tags_list.append((element.get("tags", {}), points))
        elif element["type"] == "relation" and "members" in element:
            # Handle relations (e.g., multipolygons)
            members = element["members"]
            outer_polygons = []
            inner_polygons = []
            for member in members:
                if member["type"] == "way" and member["role"] in ("outer", "inner"):
                    way_id = member["ref"]
                    way = ways_dict.get(way_id)
                    if way:
                        way_points = [
                            node_dict.get(node_id) for node_id in way["nodes"]
                        ]
                        way_points = [pt for pt in way_points if pt is not None]
                        if not way_points:
                            continue  # Skip if no valid points
                        if way_points[0] != way_points[-1]:
                            way_points.append(way_points[0])  # Close the loop
                        poly = Polygon(way_points)
                        if member["role"] == "outer":
                            outer_polygons.append(poly)
                        else:
                            inner_polygons.append(poly)
            if outer_polygons:
                # Combine outer and inner polygons
                poly = outer_polygons[0]
                for inner_poly in inner_polygons:
                    poly = poly.difference(inner_poly)
                geometries.append(poly)
                tags_list.append((element.get("tags", {}), list(poly.exterior.coords)))

    if not geometries:
        return gpd.GeoDataFrame(), []

    return gpd.GeoDataFrame(geometry=geometries, crs="EPSG:4326"), tags_list


def save_lat_lon_csv(points, tags):
    # Generate a CSV file name based on the tags
    name = tags.get("name", "layer").replace(" ", "_")
    loc_name = tags.get("loc_name", "").replace(" ", "_")
    file_name = f"{name}_{loc_name}.csv"

    # Ensure the file name is unique
    counter = 1
    base_file_name = file_name
    while os.path.exists(file_name):
        file_name = f"{base_file_name[:-4]}_{counter}.csv"
        counter += 1

    # Convert points to DataFrame with columns ordered as 'Latitude', 'Longitude'
    df = pd.DataFrame(points, columns=["Longitude", "Latitude"])[
        ["Latitude", "Longitude"]
    ]

    # Save to CSV
    df.to_csv(file_name, index=False)
    print(f"Lat-Long data saved as '{file_name}'")
    return file_name


def create_colored_image(gdf, layer, color="blue", file_name="layer"):
    # Plot the GeoDataFrame and save it as a colored image
    fig, ax = plt.subplots()
    if gdf.empty or gdf.is_empty.all():
        print(f"No {layer} data found for the specified location.")
        ax.text(
            0.5,
            0.5,
            f"No {layer} data",
            horizontalalignment="center",
            verticalalignment="center",
            transform=ax.transAxes,
        )
    else:
        gdf.plot(ax=ax, color=color)
    ax.set_facecolor("white")
    ax.axis("off")

    # Save as colored image
    plt.savefig(f"{file_name}_colored.png", bbox_inches="tight", pad_inches=0, dpi=300)
    plt.close(fig)
    print(f"Image saved as '{file_name}_colored.png'")

    # # Input latitude and longitude in DMS format
    # lat_dms = "53°06'44.0\"N"
    # lon_dms = "8°49'47.4\"E"


def main():
    # Command-line argument parsing
    parser = argparse.ArgumentParser(
        description="Fetch OSM data and save as image and various formats."
    )
    parser.add_argument(
        "--lat",
        type=str,
        help='Latitude in DMS or decimal format (e.g., "53°06\'44.0"N" or "53.11222")',
    )
    parser.add_argument(
        "--lon",
        type=str,
        help='Longitude in DMS or decimal format (e.g., "8°49\'47.4"E" or "8.82983")',
    )
    parser.add_argument(
        "--radius",
        type=str,
        help="Radius in meters for the area to fetch (default is 200 meters)",
    )
    parser.add_argument(
        "--osm-link",
        type=str,
        help='OpenStreetMap link (e.g., "https://www.openstreetmap.org/way/330599214")',
    )
    parser.add_argument(
        "--layer",
        type=str,
        default="natural=water",
        help='Target layer to fetch (default is "natural=water"). Specify as "key=value" or just "key".',
    )
    parser.add_argument(
        "--output-formats",
        nargs="+",
        default=["csv", "png"],
        help="List of output formats to export (e.g., 'csv gpx shp kml')",
    )

    args = parser.parse_args()
    if args.osm_link:
        gdf, tags_list = fetch_data_from_osm_link(args.osm_link)
        if gdf.empty:
            print(f"No data found for the provided OSM link '{args.osm_link}'.")
            return
        file_name = args.osm_link.strip("/").split("/")[-1].replace("=", "_")
    else:
        # Prompt for input if not provided
        lat_str = (
            args.lat
            or input(
                "Enter latitude in DMS or decimal format (default is 53°06'44.0\"N): "
            )
            or "53°06'44.0\"N"
        )
        lon_str = (
            args.lon
            or input(
                "Enter longitude in DMS or decimal format (default is 8°49'47.4\"E): "
            )
            or "8°49'47.4\"E"
        )
        radius = (
            args.radius
            or input("Enter radius in meters (default is 200 meters): ")
            or "200"
        )

        # Convert to decimal degrees if necessary
        lat = convert_to_decimal(lat_str)
        lon = convert_to_decimal(lon_str)
        radius = int(float(radius))

        print(f"Got location: lat:{lat}, and lon:{lon} with radius:{radius}")

        # Fetch data
        gdf, tags_list = fetch_osm_data(lat, lon, radius=radius, layer=args.layer)
        if gdf.empty:
            print(f"No data found for the specified location and layer '{args.layer}'.")
            return
        file_name = args.layer.replace("=", "_")

    # Save data in specified formats
    for fmt in args.output_formats:
        fmt = fmt.lower()
        if fmt == "csv":
            # Save lat-lon data for each geometry
            for tags, points in tags_list:
                save_lat_lon_csv(points, tags)
        elif fmt == "gpx":
            output_file = f"{file_name}.gpx"
            try:
                # GPX supports LineString and Point geometries
                gdf_gpx = gdf[gdf.geometry.type.isin(["LineString", "Point"])]
                if not gdf_gpx.empty:
                    gdf_gpx.to_file(output_file, driver="GPX")
                    print(f"Data saved as '{output_file}'")
                else:
                    print("No LineString or Point geometries to save as GPX.")
            except Exception as e:
                print(f"Error saving to GPX: {e}")
        elif fmt == "kml":
            output_file = f"{file_name}.kml"
            try:
                gdf.to_file(output_file, driver="KML")
                print(f"Data saved as '{output_file}'")
            except Exception as e:
                print(f"Error saving to KML: {e}")
        elif fmt == "shp":
            output_file = f"{file_name}.shp"
            try:
                gdf.to_file(output_file, driver="ESRI Shapefile")
                print(f"Data saved as '{output_file}'")
            except Exception as e:
                print(f"Error saving to Shapefile: {e}")
        elif fmt == "png":
            create_colored_image(
                gdf, layer=args.layer, color="blue", file_name=file_name
            )
        else:
            print(f"Unsupported format: {fmt}")

    print("Processing completed.")


if __name__ == "__main__":
    main()
