import requests
import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import Polygon, LineString, Point
import re

def dms_to_dd(dms_str):
    # Convert DMS (Degrees, Minutes, Seconds) to Decimal Degrees
    dms_str = dms_str.strip()
    degrees, minutes, seconds, direction = re.split('[°\'"]+', dms_str)
    dd = float(degrees) + float(minutes)/60 + float(seconds)/3600
    if direction in ['S', 'W']:
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
    elif layer == "ground":
        overpass_query = f"""
        [out:json];
        (
          way["landuse"="grass"]({bbox});
          way["landuse"="forest"]({bbox});
          way["landuse"="meadow"]({bbox});
          way["natural"="wood"]({bbox});
        );
        out body;
        >;
        out skel qt;
        """
    
    response = requests.get(overpass_url, params={'data': overpass_query})
    data = response.json()

    # Print available elements for debugging
    print(f"Data received for {layer} layer: {data['elements']}")

    elements = data['elements']
    geometries = []
    
    for element in elements:
        if 'geometry' in element:
            points = [(point['lon'], point['lat']) for point in element['geometry']]
            if element['type'] == 'way':
                # Create a Polygon if the way forms a closed loop, otherwise a LineString
                if points[0] == points[-1]:
                    geometries.append(Polygon(points))
                else:
                    geometries.append(LineString(points))

    if not geometries:
        return gpd.GeoDataFrame()
    
    return gpd.GeoDataFrame(geometry=geometries, crs="EPSG:4326")

def create_binary_image(gdf, layer):
    # Plot the GeoDataFrame and save it as a binary image
    fig, ax = plt.subplots()
    if gdf.empty:
        print(f"No {layer} data found for the specified location.")
        ax.text(0.5, 0.5, f'No {layer} data', horizontalalignment='center', verticalalignment='center', transform=ax.transAxes)
    else:
        gdf.boundary.plot(ax=ax, color='black')
    ax.set_facecolor('white')
    ax.axis('off')
    
    # Save as black and white image
    plt.savefig(f"{layer}_binary.png", bbox_inches='tight', pad_inches=0, dpi=300)
    plt.close(fig)

def main():
    # Input latitude and longitude in DMS format
    lat_dms = "53°06'44.0\"N"
    lon_dms = "8°49'47.4\"E"
    
    # Convert DMS to Decimal Degrees
    lat = dms_to_dd(lat_dms)
    lon = dms_to_dd(lon_dms)
    
    # Fetch and save water layer
    water_gdf = fetch_osm_data(lat, lon, layer="water")
    create_binary_image(water_gdf, layer="water")
    
    # Fetch and save ground layer
    ground_gdf = fetch_osm_data(lat, lon, layer="ground")
    create_binary_image(ground_gdf, layer="ground")
    
    print("Images saved as 'water_binary.png' and 'ground_binary.png'")

if __name__ == "__main__":
    main()
