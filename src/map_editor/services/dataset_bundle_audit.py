"""Inspect serialized research artifacts without any simulator dependency."""
import csv
import json
import math
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from PySide6.QtGui import QImage
from map_editor.geometry import GeometryError
from map_editor.geometry.curves import State
from map_editor.geometry.validation import validate_raster_footprint
from .research_spec import load_research_spec
from .yaml_serializer import load_map_yaml


def audit_bundle(root,entry):
    root=Path(root);folder=(root/entry['map']).parent
    metadata=json.loads((root/entry['metadata']).read_text());artifacts=metadata['artifacts'];spec=load_research_spec(root/entry['recipe'])
    with (folder/artifacts['centerline']).open() as handle:
        reader=csv.DictReader(handle)
        if reader.fieldnames!=['x','y','theta','velocity']:raise GeometryError('Invalid ordinary centerline CSV schema')
        rows=list(reader)
    xy=np.array([(float(r['x']),float(r['y'])) for r in rows]);headings=np.array([float(r['theta']) for r in rows])
    if len(xy)!=metadata['measured']['sample_count'] or not np.isfinite(xy).all() or not np.isfinite(headings).all():raise GeometryError('Invalid serialized centerline geometry')
    edges=np.roll(xy,-1,axis=0)-xy
    if min(np.linalg.norm(edges,axis=1))<=1e-10:raise GeometryError('Degenerate serialized centerline edge')
    previous=np.roll(edges,1,axis=0)
    winding=float(np.arctan2(previous[:,0]*edges[:,1]-previous[:,1]*edges[:,0],(previous*edges).sum(axis=1)).sum())
    if abs(winding-math.tau)>1e-6:raise GeometryError('Serialized winding differs from +2 pi')
    profile=np.genfromtxt(folder/artifacts['track_profile'],delimiter=',',names=True)
    if len(profile)!=len(xy) or any(not np.isfinite(profile[n]).all() for n in profile.dtype.names):raise GeometryError('Invalid serialized track profile')
    if max(abs(profile['width_m']-profile['left_width_m']-profile['right_width_m']))>3e-9:raise GeometryError('Serialized side widths disagree')
    if not np.allclose(np.c_[profile['x_m'],profile['y_m']],xy,atol=1e-9,rtol=0):raise GeometryError('Profile and centerline positions disagree')
    walls={};sentinels={}
    with (folder/artifacts['walls']).open() as handle:
        reader=csv.DictReader(handle)
        if reader.fieldnames!=['wall_id','vertex_id','x','y']:raise GeometryError('Invalid wall CSV schema')
        for row in reader:
            key=row['wall_id'];x,y=float(row['x']),float(row['y'])
            if row['vertex_id'] in ('BEGIN','END'):
                if not math.isnan(x) or not math.isnan(y):raise GeometryError('Wall delimiter must contain NaN coordinates')
                sentinels.setdefault(key,[]).append(row['vertex_id'])
            else:
                if not math.isfinite(x) or not math.isfinite(y):raise GeometryError('Invalid wall vertex')
                walls.setdefault(key,[]).append((x,y))
    if set(walls)!={'0','1'} or any(sentinels[k]!=['BEGIN','END'] for k in walls):raise GeometryError('Expected two delimited wall polylines')
    if any(len(p)!=len(xy)+1 or p[0]!=p[-1] for p in walls.values()):raise GeometryError('Wall CSV must close both retained boundary polygons')
    document=load_map_yaml(root/entry['map']);finish=document.annotations.start_finish_line
    if finish is None or finish.direction is None:raise GeometryError('Directional finish annotation missing')
    start=np.array([finish.segment.start.x,finish.segment.start.y]);end=np.array([finish.segment.end.x,finish.segment.end.y])
    direction=np.array([finish.direction.x,finish.direction.y]);tangent=np.array([math.cos(headings[0]),math.sin(headings[0])])
    segment=end-start;t=float((xy[0]-start)@segment/(segment@segment))
    if not 0<t<1 or np.linalg.norm(xy[0]-start-t*segment)>1e-6 or direction@tangent<.999999:
        raise GeometryError('Serialized finish does not span centerline in its travel direction')
    spawn=next((s for s in document.annotations.spawn_points if s.name=='grid_1'),None)
    if spawn is None:raise GeometryError('Named grid spawn missing')
    pose=spawn.pose;nearest=int(np.argmin(np.linalg.norm(xy-[pose.x,pose.y],axis=1)))
    if np.linalg.norm(xy[nearest]-[pose.x,pose.y])>1e-6 or abs(math.atan2(math.sin(headings[nearest]-pose.theta),math.cos(headings[nearest]-pose.theta)))>1e-5:
        raise GeometryError('Named spawn does not match a retained centerline pose')
    header=(folder/artifacts['pgm']).read_bytes().split(b'\n',3)
    if len(header)!=4 or header[0]!=b'P5' or header[2]!=b'255':raise GeometryError('Unsupported PGM occupancy encoding')
    width,height=map(int,header[1].split());pixels=header[3]
    if len(pixels)!=width*height:raise GeometryError('PGM payload dimensions mismatch')
    image=QImage(str(folder/artifacts['image'])).convertToFormat(QImage.Format_Grayscale8)
    if image.isNull() or image.width()!=width or image.height()!=height:raise GeometryError('PNG occupancy dimensions mismatch')
    png=np.frombuffer(image.constBits(),dtype=np.uint8).reshape(height,image.bytesPerLine())[:,:width]
    if not np.array_equal(png,np.frombuffer(pixels,dtype=np.uint8).reshape(height,width)):raise GeometryError('PNG and PGM occupancy disagree')
    state=State(0.,pose.x,pose.y,pose.theta,0.,0.)
    sampled=SimpleNamespace(states=(state,state),closed=True)
    spawn_check=validate_raster_footprint(sampled,(pixels,width,height,document.metadata.origin_x,document.metadata.origin_y,document.metadata.resolution),spec.vehicle,spec.limits.footprint_margin_m)
    return dict(centerline_csv='passed',walls_csv='passed',profile_csv='passed',winding_rad=winding,
        directional_finish='passed_geometrically',named_spawn='passed_geometrically',spawn_raster_footprint=spawn_check,
        png_pgm_agreement='byte_identical_pixels',simulator_integration='not_run')
