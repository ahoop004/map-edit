"""Offline export with active-edge rasterization and reuse of validated pixels.

Legacy exporters remain unchanged. Cell centers, even-odd fill, boundary stroke,
CSV encoders and ROS annotations retain the existing conventions.
"""
from dataclasses import asdict
import math
from pathlib import Path
import numpy as np
import yaml
from PySide6.QtGui import QImage,QPainter,QPen,QColor
from map_editor.exporters.centerline import export_centerline_csv
from map_editor.models.annotations import MapAnnotations
from .wall_extraction import export_walls_csv
from .track_profile import export_track_profile
from .geometry_metadata import write_geometry_metadata
from .yaml_serializer import MapYamlDocument,dump_map_yaml
from .procedural_track import (_compute_raster_bounds,_world_to_cell,_draw_line,_write_png,_write_pgm,
    _draw_polyline,build_finish_line,_build_metadata,TrackSpecError)


def rasterize_corridor(walls,*,resolution,padding):
    width,height,ox,oy=_compute_raster_bounds(walls,resolution=resolution,padding=max(padding,resolution))
    if width*height>64_000_000:raise TrackSpecError('Offline raster exceeds the explicit 64-million-cell budget')
    edge=[(a,b) for wall in walls for a,b in zip(wall,[*wall[1:],wall[0]]) if a.y!=b.y]
    coordinates=np.array([[(a.x,a.y),(b.x,b.y)] for a,b in edge]);starts={};stops={}
    for j,(a,b) in enumerate(edge):
        start=max(0,math.floor((min(a.y,b.y)-oy)/resolution-.5))
        stop=min(height,math.ceil((max(a.y,b.y)-oy)/resolution-.5)+1)
        starts.setdefault(start,[]).append(j);stops.setdefault(stop,[]).append(j)
    active=set();pixels=bytearray(width*height)
    for bottom_row in range(height):
        active.difference_update(stops.get(bottom_row,()));active.update(starts.get(bottom_row,()))
        if not active:continue
        row=height-1-bottom_row;y=oy+(height-row-.5)*resolution
        e=coordinates[sorted(active)];a=e[:,0];b=e[:,1]
        valid=(a[:,1]>y)!=(b[:,1]>y);a=a[valid];b=b[valid]
        crossings=np.sort(a[:,0]+(y-a[:,1])*(b[:,0]-a[:,0])/(b[:,1]-a[:,1]))
        if len(crossings)%2:raise TrackSpecError('Invalid odd crossing count in corridor scanline')
        for left,right in zip(crossings[::2],crossings[1::2]):
            first=max(0,math.ceil((float(left)-ox)/resolution-.5));stop=min(width,math.ceil((float(right)-ox)/resolution-.5))
            if stop>first:pixels[row*width+first:row*width+stop]=bytes([255])*(stop-first)
    for wall in walls:
        for a,b in zip(wall,[*wall[1:],wall[0]]):
            x0,y0=_world_to_cell(a,ox,oy,resolution,height);x1,y1=_world_to_cell(b,ox,oy,resolution,height)
            _draw_line(pixels,width,height,x0,y0,x1,y1,1)
    return bytes(pixels),width,height,ox,oy


def export_offline(spec,geometry,metadata,recipe,raster,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    pixels,width,height,ox,oy=raster;stem=spec.stem
    _write_png(pixels,width,height,directory/(stem+'.png'));_write_pgm(pixels,width,height,directory/(stem+'.pgm'))
    export_centerline_csv(geometry.samples,directory/(stem+'_centerline.csv'))
    export_walls_csv(geometry.walls,directory/(stem+'_walls.csv'))
    export_track_profile(geometry.profile,directory/(stem+'_track_profile.csv'))
    image=QImage(pixels,width,height,width,QImage.Format_Grayscale8).convertToFormat(QImage.Format_RGB888)
    painter=QPainter(image)
    try:
        painter.setPen(QPen(QColor(0,200,200),1))
        _draw_polyline(painter,geometry.centerline,ox,oy,spec.resolution,height,close=True,cell_coordinates=True)
    finally:painter.end()
    if not image.save(str(directory/(stem+'_preview.png')),'PNG'):raise TrackSpecError('Failed to save offline preview')
    path=directory/(stem+'.yaml')
    document=MapYamlDocument(yaml_path=path,image=stem+'.png',metadata=_build_metadata(spec,ox,oy),
        annotations=MapAnnotations(centerline=geometry.centerline,start_finish_line=build_finish_line(geometry)),
        negate=0,extra_fields=dict(track_metadata=stem+'_metadata.json',occupancy=dict(mode='corridor',outside_track='occupied',marl_race_track_inverted=False)))
    dump_map_yaml(document,path)
    recipe=dict(recipe,achieved=geometry.metrics,files={k:v for k,v in metadata['artifacts'].items() if k in ('map','image','pgm','centerline','walls','track_profile','metadata')})
    (directory/(stem+'_generation.yaml')).write_text(yaml.safe_dump(recipe,sort_keys=False))
    write_geometry_metadata(metadata,directory/(stem+'_metadata.json'))
    return path
