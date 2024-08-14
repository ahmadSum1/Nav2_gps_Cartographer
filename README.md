# Nav2_gps_Cartographer
create global cost map (2d occupancy grid) for nav2 from GPS coordinates

## Usage
### Create csv 
```bash
python3 maplayer.py --lat "53.11222" --lon "8.82983" --radius 200
```
### create 2d occupancy gridmap

```bash
python3 gpsToNav2map.py --resolution=1 --map_image_name=my_map.pgm --map_yaml_name=my_map.yaml
```