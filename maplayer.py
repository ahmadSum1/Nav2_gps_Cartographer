import requests
import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import Polygon
import re
import pandas as pd
import os


def dms_to_dd(dms_str):
    # Convert DMS (Degrees, Minutes, Seconds) to Decimal Degrees
    dms_str = dms_str.strip()
    degrees, minutes, seconds, direction = re.split("[°'\"]+", dms_str)
    dd = float(degrees) + float(minutes) / 60 + float(seconds) / 3600
    if direction in ["S", "W"]:
        dd *= -1
    return dd


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

    # Print available elements for debugging
    print(f"Data received for {layer} layer: {data}")

    # Create a dictionary mapping node IDs to their lat/lon coordinates
    node_dict = {
        element["id"]: (element["lat"], element["lon"])
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

    # Convert points to DataFrame
    df = pd.DataFrame(points, columns=["Latitude","Longitude"])

    # Save to CSV
    df.to_csv(file_name, index=False)
    print(f"Lat-Long data saved as '{file_name}'")


def create_colored_image(gdf, layer, color="blue"):
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
    plt.savefig(f"{layer}_colored.png", bbox_inches="tight", pad_inches=0, dpi=300)
    plt.close(fig)
    print(f"Image saved as '{layer}_colored.png'")


def main():
    # Input latitude and longitude in DMS format
    lat_dms = "53°06'44.0\"N"
    lon_dms = "8°49'47.4\"E"

    # Convert DMS to Decimal Degrees
    lat = dms_to_dd(lat_dms)
    lon = dms_to_dd(lon_dms)

    # Fetch and save water layer
    water_gdf, tags_list = fetch_osm_data(lat, lon, radius=200, layer="water")

    # Save lat-lon data for each way
    for tags, points in tags_list:
        save_lat_lon_csv(points, tags)

    create_colored_image(water_gdf, layer="water", color="blue")

    print("Processing completed.")


if __name__ == "__main__":
    main()
