"""Small raster tiles of the actual SUMO/OSM graph, built off the UI thread."""
from PIL import Image, ImageDraw
from shapely.geometry import box


def road_tile(provider, zoom, tx, ty):
    from .map_canvas import world_pixel, pixel_lonlat
    # A gutter includes roads crossing tile borders without seams.
    west,north=pixel_lonlat(tx*256-8,ty*256-8,zoom)
    east,south=pixel_lonlat((tx+1)*256+8,(ty+1)*256+8,zoom)
    a,b=provider.lonlat_to_xy(west,south),provider.lonlat_to_xy(east,north)
    image=Image.new('RGB',(256,256),'#e8edf1')
    draw=ImageDraw.Draw(image)
    positions=provider.tree.query(box(min(a[0],b[0]),min(a[1],b[1]),max(a[0],b[0]),max(a[1],b[1])))
    for position in positions:
        edge=provider.edges[provider.edge_ids[int(position)]]
        if 'passenger' not in edge['allowed']:continue
        points=[(x-tx*256,y-ty*256) for x,y in (world_pixel(*ll,zoom) for ll in edge['shape_wgs84'])]
        if len(points)>1:draw.line(points,fill='#75879a',width=2)
    return image


def grid_tile(zoom,tx,ty):
    """Transparent display grid; authoritative MEC incident cells stay separate."""
    import h3
    import math
    from .map_canvas import pixel_lonlat,world_pixel
    res=10 if zoom>=15 else 8
    _,latitude=pixel_lonlat(tx*256+128,ty*256+128,zoom)
    metres_per_pixel=156543.033928*math.cos(math.radians(latitude))/2**zoom
    padding=max(256,math.ceil(2*h3.average_hexagon_edge_length(res,unit='m')/metres_per_pixel))
    west,north=pixel_lonlat(tx*256-padding,ty*256-padding,zoom)
    east,south=pixel_lonlat((tx+1)*256+padding,(ty+1)*256+padding,zoom)
    cover={'type':'Polygon','coordinates':[[[west,south],[east,south],[east,north],[west,north],[west,south]]]}
    # At broad views a display cover would become needlessly large.
    area=abs((east-west)*(north-south))*111.32**2
    image=Image.new('RGBA',(256,256))
    if zoom<11 or area/h3.average_hexagon_area(res,unit='km^2')>2200:return image
    draw=ImageDraw.Draw(image)
    for cell in h3.geo_to_cells(cover,res):
        points=[(x-tx*256,y-ty*256) for x,y in (world_pixel(lon,lat,zoom) for lat,lon in h3.cell_to_boundary(cell))]
        draw.line([*points,points[0]],fill='#94a3b8',width=1)
    return image
