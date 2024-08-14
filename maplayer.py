import requests
import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import Polygon
import re
import pandas as pd
import os
import argparse


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


def fetch_data_from_osm_link(osm_link):
    # Extract the way ID from the OSM link
    way_id_match = re.search(r"/way/(\d+)", osm_link)
    if not way_id_match:
        raise ValueError("Invalid OSM link. Please provide a valid OpenStreetMap link.")

    way_id = way_id_match.group(1)
    osm_url = f"https://www.openstreetmap.org/api/0.6/way/{way_id}/full.json"
    response = requests.get(osm_url)
    data = response.json()

    node_dict = {
        element["id"]: (element["lon"], element["lat"])
        for element in data["elements"]
        if element["type"] == "node"
    }

    geometries = []
    tags_list = []
    for element in data["elements"]:
        if element["type"] == "way" and str(element["id"]) == way_id:
            points = [node_dict[node_id] for node_id in element["nodes"]]
            geometries.append(Polygon(points))
            tags_list.append((element["tags"], points))

    if not geometries:
        return gpd.GeoDataFrame(), []

    return gpd.GeoDataFrame(geometry=geometries, crs="EPSG:4326"), tags_list


def fetch_osm_data(lat, lon, radius=200, layer="water"):
    # Define the bounding box for the radius
    bbox = f"{lat-radius/111320},{lon-radius/111320},{lat+radius/111320},{lon+radius/111320}"

    # Overpass API query for the specified layer
    overpass_url = "http://overpass-api.de/api/interpreter"
    if layer == "water":
        overpass_query = f"""
        [out:json];
        (
          way["natural"="water"]({bbox});
        );
        out body;
        >;
        out skel qt;
        """

    response = requests.get(overpass_url, params={"data": overpass_query})
    data = response.json()

    # # Print available elements for debugging
    # print(f"Data received for {layer} layer: {data}")

    # Create a dictionary mapping node IDs to their lat/lon coordinates
    node_dict = {
        element["id"]: (element["lon"], element["lat"])
        for element in data["elements"]
        if element["type"] == "node"
    }

    geometries = []
    tags_list = []
    for element in data["elements"]:
        if element["type"] == "way":
            points = [node_dict[node_id] for node_id in element["nodes"]]
            if points[0] == points[-1]:  # Closed loop
                geometries.append(Polygon(points))
                tags_list.append((element["tags"], points))  # Include points for CSV

    if not geometries:
        return gpd.GeoDataFrame(), []

    return gpd.GeoDataFrame(geometry=geometries, crs="EPSG:4326"), tags_list


def save_lat_lon_csv(points, tags):
    # Generate a CSV file name based on the tags
    name = tags.get("name", "water_layer").replace(" ", "_")
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
        description="Fetch water layer data from OpenStreetMap and save as image and CSV."
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
        help="Radius in meters for the area to fetch (default is 100 meters)",
    )
    parser.add_argument(
        "--osm-link",
        type=str,
        help='OpenStreetMap link (e.g., "https://www.openstreetmap.org/way/330599214")',
    )

    args = parser.parse_args()
    if args.osm_link:
        water_gdf, tags_list = fetch_data_from_osm_link(args.osm_link)
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

        print(f"Got location: lat:{lat}, and lon:{lon} with radious:{radius}")

        # Fetch and save water layer
        water_gdf, tags_list = fetch_osm_data(lat, lon, radius=radius, layer="water")

    # Save lat-lon data for each way
    for tags, points in tags_list:
        file_name = save_lat_lon_csv(points, tags)

    create_colored_image(water_gdf, layer="water", color="blue", file_name=file_name)

    print("Processing completed.")


if __name__ == "__main__":
    main()
