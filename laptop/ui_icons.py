"""Small, consistent line icons; no emoji, glyph fallback or network assets."""
from PIL import Image, ImageDraw, ImageTk

from .ui_theme import FG


def icon_image(widget, name, color=FG, size=16):
    root = widget.winfo_toplevel()
    cache = getattr(root, '_icon_images', None)
    if cache is None:
        cache = root._icon_images = {}
    key = (name,color,size)
    if key in cache:
        return cache[key]
    scale = 4
    image = Image.new('RGBA',(size*scale,size*scale))
    draw = ImageDraw.Draw(image)
    def xy(points):
        return [(x/24*size*scale,y/24*size*scale) for x,y in points]
    def line(points, width=1.6):
        draw.line(xy(points),fill=color,width=max(1,round(width/24*size*scale)),joint='curve')
    def rect(bounds, fill=None):
        draw.rectangle(xy([(bounds[0],bounds[1]),(bounds[2],bounds[3])]),
                       outline=color,width=max(1,round(1.5/24*size*scale)),fill=fill)
    def circle(bounds, fill=None):
        draw.ellipse(xy([(bounds[0],bounds[1]),(bounds[2],bounds[3])]),
                     outline=color,width=max(1,round(1.5/24*size*scale)),fill=fill)
    def polygon(points, fill=None):
        draw.polygon(xy(points),fill=fill or color)
    if name == 'play': polygon([(7,4),(20,12),(7,20)])
    elif name == 'pause': rect((6,4,9,20),color); rect((15,4,18,20),color)
    elif name == 'step': polygon([(4,5),(15,12),(4,19)]); line([(19,4),(19,20)],2)
    elif name == 'fast':
        polygon([(3,5),(12,12),(3,19)]);polygon([(13,5),(22,12),(13,19)])
    elif name in ('plus','minus'):
        line([(4,12),(20,12)])
        if name == 'plus': line([(12,4),(12,20)])
    elif name == 'close': line([(6,6),(18,18)]);line([(18,6),(6,18)])
    elif name == 'check': line([(4,12),(9,17),(20,6)],2)
    elif name == 'restart':
        draw.arc(xy([(4,4),(20,20)]),start=200,end=510,fill=color,width=max(1,round(size*scale/14)))
        line([(3,3),(3,10),(10,10)])
    elif name == 'settings':
        import math
        points=[]
        for i in range(32):
            r=10 if i%4 in (1,2) else 7.5
            points.append((12+r*math.cos(i*math.pi/16),12+r*math.sin(i*math.pi/16)))
        line(points+[points[0]],1.4);circle((8,8,16,16))
    elif name == 'focus':
        circle((5,5,19,19));circle((10,10,14,14))
        for points in [[(12,1),(12,7)],[(12,17),(12,23)],[(1,12),(7,12)],[(17,12),(23,12)]]:line(points)
    elif name == 'map':
        line([(2,5),(8,3),(16,6),(22,3),(22,19),(16,22),(8,19),(2,21),(2,5)])
        line([(8,3),(8,19)]);line([(16,6),(16,22)])
    elif name == 'folder': line([(2,6),(9,6),(11,9),(22,9),(20,20),(3,20),(2,6)]);line([(4,6),(4,3),(10,3),(12,6),(20,6),(20,9)])
    elif name == 'save':
        rect((4,3,20,21));rect((8,3,16,9));rect((8,14,16,21))
    elif name == 'new':
        line([(14,3),(5,3),(5,21),(19,21),(19,8),(14,3),(14,8),(19,8)])
        line([(8,14),(16,14)]);line([(12,10),(12,18)])
    elif name == 'example':
        rect((3,4,21,20));line([(3,9),(21,9)]);polygon([(10,11),(17,15),(10,19)])
    elif name == 'pin':
        circle((5,2,19,16));circle((10,7,14,11));line([(6,13),(12,22),(18,13)])
    elif name == 'send': line([(2,3),(22,12),(2,21),(6,12),(2,3)]);line([(6,12),(22,12)])
    elif name == 'clear': circle((3,3,21,21));line([(6,18),(18,6)])
    elif name == 'circle': circle((3,3,21,21))
    elif name == 'rectangle': rect((3,5,21,19))
    elif name == 'polygon': line([(4,7),(15,3),(21,12),(15,21),(3,17),(4,7)])
    elif name == 'trash':
        line([(3,6),(21,6)]);line([(8,6),(8,3),(16,3),(16,6)])
        line([(6,6),(7,21),(17,21),(18,6)]);line([(10,9),(10,18)]);line([(14,9),(14,18)])
    elif name == 'car':
        line([(3,19),(3,11),(6,5),(18,5),(21,11),(21,19)])
        rect((3,11,21,18));line([(5,18),(5,21)]);line([(19,18),(19,21)])
        line([(6,14),(9,14)]);line([(15,14),(18,14)])
    elif name in ('chevron_down','chevron_right'):
        line([(5,9),(12,16),(19,9)] if name=='chevron_down' else [(9,5),(16,12),(9,19)])
    elif name == 'search':circle((3,3,16,16));line([(14,14),(22,22)])
    else: raise ValueError('Unknown UI icon: '+name)
    result=ImageTk.PhotoImage(image.resize((size,size),Image.Resampling.LANCZOS),master=root)
    cache[key]=result
    return result


def set_icon(button, name, color=FG):
    image = icon_image(button,name,color)
    button.configure(image=image, text='')
    button._icon_ref=image
