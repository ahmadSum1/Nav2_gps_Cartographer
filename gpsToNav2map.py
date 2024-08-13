import pandas as pd
import numpy as np
from pyproj import CRS, Transformer
from PIL import Image, ImageDraw
import math

# Load GPS data from CSV
csv_file = 'gps_data_unisee.csv'  # Replace with your actual CSV file path
data = pd.read_csv(csv_file)

# Assuming the CSV has columns 'latitude' and 'longitude'
gps_points = list(zip(data['latitude'], data['longitude']))

# Convert GPS to UTM using modern pyproj API
wgs84 = CRS.from_epsg(4326)
utm = CRS.from_epsg(32632)  # Bremen's UTM zone
transformer = Transformer.from_crs(wgs84, utm, always_xy=True)
utm_points = [transformer.transform(lon, lat) for lat, lon in gps_points]

# Calculate the bounds and resolution
min_x = min([p[0] for p in utm_points])
min_y = min([p[1] for p in utm_points])
max_x = max([p[0] for p in utm_points])
max_y = max([p[1] for p in utm_points])
resolution = 0.50  # 50 cm per pixel

# Calculate centroid
centroid_x = sum([p[0] for p in utm_points]) / len(utm_points)
centroid_y = sum([p[1] for p in utm_points]) / len(utm_points)

# Sort points based on angle with centroid
def angle_from_centroid(point):
    return math.atan2(point[1] - centroid_y, point[0] - centroid_x)

utm_points_sorted = sorted(utm_points, key=angle_from_centroid)

# Add padding to prevent out-of-bounds errors
padding = 10  # You can adjust this value
width = int((max_x - min_x) / resolution) + 2 * padding
height = int((max_y - min_y) / resolution) + 2 * padding
image = Image.new('L', (width, height), 0)  # black background (obstacle)
draw = ImageDraw.Draw(image)

# Convert UTM points to pixel coordinates for the polygon
# Note: No need to flip y-axis as the top-left is the origin (consistent with image orientation)
polygon_points = [
    (int((x - min_x) / resolution) + padding, int((y - min_y) / resolution) + padding)
    for x, y in utm_points_sorted
]

# Draw and fill the polygon as unexplored region (mid-gray)
draw.polygon(polygon_points, fill=205)  # 205 for unexplored

# Save the map
image.save('map_fixed.pgm')
image.save('map_fixed.png', 'png')

# Create the map.yaml file
with open('map.yaml', 'w') as f:
    f.write(f"image: map_fixed.pgm\n")
    f.write(f"resolution: {resolution}\n")
    f.write(f"origin: [{min_x - padding * resolution}, {min_y - padding * resolution}, 0.0]\n")
    f.write("occupied_thresh: 0.65\n")
    f.write("free_thresh: 0.196\n")
    f.write("negate: 0\n")
