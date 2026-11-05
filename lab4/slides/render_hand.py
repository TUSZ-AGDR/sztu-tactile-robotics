"""Render the supplied URDF-derived PAXINI hand and embed it in the Chinese deck.

Run with the lab environment: MUJOCO_GL=egl python lab4/slides/render_hand.py
Then run build_en.py to update the English deck. PNGs are embedded for offline use.
"""
from pathlib import Path
import base64
import json
import os
import re
os.environ.setdefault('MUJOCO_GL', 'egl')
import mujoco
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ASSETS = HERE / 'assets'
model = mujoco.MjModel.from_xml_path(str(ASSETS / 'paxini_left_hand.xml'))
data = mujoco.MjData(model)
model.body_quat[model.body('left_palm_link').id] = [2**-.5, 0, -2**-.5, 0]
mujoco.mj_forward(model, data)
vertices = []
for geom in range(model.ngeom):
    mesh = model.geom_dataid[geom]
    start, count = model.mesh_vertadr[mesh], model.mesh_vertnum[mesh]
    vertices.append(model.mesh_vert[start:start+count] @ data.geom_xmat[geom].reshape(3, 3).T + data.geom_xpos[geom])
vertices = np.concatenate(vertices)
camera = mujoco.MjvCamera()
camera.lookat[:] = (vertices.min(0) + vertices.max(0)) / 2
camera.distance, camera.azimuth, camera.elevation = .42, 20, -7
renderer = mujoco.Renderer(model, height=1000, width=1000)
renderer.update_scene(data, camera=camera)
rgb = renderer.render().copy()
renderer.enable_segmentation_rendering()
renderer.update_scene(data, camera=camera)
seg = renderer.render().copy()
renderer.close()
foreground = seg[:, :, 0] >= 0
sensor = (seg[:, :, 0] == model.geom('left_index_tactile_link3_visual_0').id) & (seg[:, :, 1] == int(mujoco.mjtObj.mjOBJ_GEOM))
assert sensor.sum() > 100, 'ID3 must be visible in the selected camera view'
ys, xs = np.where(foreground)
x0, y0, x1, y1 = max(0, xs.min()-18), max(0, ys.min()-18), min(1000, xs.max()+19), min(1000, ys.max()+19)
rgba = np.dstack([rgb, foreground.astype(np.uint8)*255])[y0:y1, x0:x1]
Image.fromarray(rgba).save(ASSETS / 'paxini_hand.png')
sy, sx = np.where(sensor)
bbox = [int(sx.min()-x0), int(sy.min()-y0), int(sx.max()-x0), int(sy.max()-y0)]
metadata = dict(camera=dict(azimuth=20, elevation=-7, distance=.42, lookat=camera.lookat.tolist()), image_size=[int(x1-x0), int(y1-y0)], sensor_bbox=bbox, sensor_link='left_index_tactile_link3', pose='Zero joint positions; palm rotated upright for display. Highlight colors are editorial.')
(ASSETS / 'paxini_hand_view.json').write_text(json.dumps(metadata, indent=2)+'\n')
# Compute the annotation from the visible sensor pixels, not an estimated position.
scale = 455 / rgba.shape[0]
image_x, image_y = 130, 12
cx = image_x + (bbox[0]+bbox[2])/2*scale
cy = image_y + (bbox[1]+bbox[3])/2*scale
radius = max(bbox[2]-bbox[0], bbox[3]-bbox[1])*scale/2+11
uri = 'data:image/png;base64,' + base64.b64encode((ASSETS/'paxini_hand.png').read_bytes()).decode()
helper = '''// BEGIN PAXINI HAND ASSET
function paxiniHand(lang='zh'){
 const en=lang==='en';
 return `<image x="130" y="12" width="WIDTH" height="455" href="URI"/>`
 +circle(CX,CY,RADIUS,C.gold,'none','stroke-width="3"')
 +`<path d="M 120 119 H 218 L ENDX ENDY" stroke="${C.gold}" stroke-width="2" fill="none"/>`
 +txt(45,77,'ID3',37,C.gold)+txt(45,109,en?'Index fingertip':'食指指尖传感器',23,C.gold)
 +txt(130,508,en?'PAXINI · left-hand URDF model':'PAXINI · 左手 URDF 模型',23,C.muted);
}
// END PAXINI HAND ASSET
'''
for key, value in {'WIDTH':rgba.shape[1]*scale,'CX':cx,'CY':cy,'RADIUS':radius,'ENDX':cx-radius*.8,'ENDY':cy+radius*.6,'URI':uri}.items():
    helper = helper.replace(key, str(value))
path = HERE/'index.html'
html = path.read_text()
if '// BEGIN PAXINI HAND ASSET' in html:
    html = re.sub(r'// BEGIN PAXINI HAND ASSET.*?// END PAXINI HAND ASSET\n', lambda _: helper, html, flags=re.S)
else:
    html = html.replace("$('cover-visual')", helper+"$('cover-visual')", 1)
html = re.sub(r"let hand=.*?;hand\+='</g>';", "let hand=paxiniHand();", html)
html = html.replace('单个食指指尖模块高亮，说明固定手型和已知轨迹', 'PAXINI 左手 URDF 整手模型，圈出食指指尖 ID3 传感器')
path.write_text(html)
print(json.dumps(metadata, indent=2))
