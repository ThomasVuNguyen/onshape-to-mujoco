#!/usr/bin/env python3
"""
MuJoCo Web Viewer - Optimized Multi-View Version

Features:
- Multiple camera views (main, front, top)
- Lower resolution for faster rendering
- JPEG compression for smaller payloads
- Direct joint control (no physics simulation by default)
"""
import os
os.environ['MUJOCO_GL'] = 'osmesa'

import io
import time
from pathlib import Path

import numpy as np
import mujoco
from flask import Flask, render_template_string, Response, request, jsonify

# Configuration
PORT = 1306
MODEL_PATH = Path(__file__).parent / 'robot.xml'
RENDER_WIDTH = 640  # Lower res for speed
RENDER_HEIGHT = 360
JPEG_QUALITY = 70  # Lower quality = smaller file = faster transfer

app = Flask(__name__)

# Global state
model = None
data = None
renderer = None
cameras = {}  # Multiple cameras
model_center = np.zeros(3)
model_extent = 0.1

joint_controls = {}
auto_animate = True  # Auto-oscillate for demonstration
anim_time = 0


def ensure_initialized():
    global model, data, renderer, cameras, model_center, model_extent, joint_controls
    
    if model is not None:
        return
    
    print(f"Loading model: {MODEL_PATH}")
    model = mujoco.MjModel.from_xml_path(str(MODEL_PATH))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    
    renderer = mujoco.Renderer(model, RENDER_HEIGHT, RENDER_WIDTH)
    
    # Calculate bounds
    min_pos = np.array([float('inf')] * 3)
    max_pos = np.array([float('-inf')] * 3)
    for i in range(model.nbody):
        pos = data.xpos[i]
        min_pos = np.minimum(min_pos, pos)
        max_pos = np.maximum(max_pos, pos)
    
    model_center = (min_pos + max_pos) / 2
    model_extent = max(0.1, np.linalg.norm(max_pos - min_pos))
    
    # Setup multiple cameras
    for name, (az, el) in [('main', (135, -25)), ('front', (180, 0)), ('top', (0, -90))]:
        cam = mujoco.MjvCamera()
        cam.azimuth = az
        cam.elevation = el
        cam.distance = model_extent * 0.8  # Zoom in closer
        cam.lookat[:] = model_center
        cameras[name] = cam
    
    # Joint controls
    for i in range(model.njnt):
        jname = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, i)
        if jname:
            joint_controls[jname] = 0.0
    
    print(f"Loaded: {model.nbody} bodies, {model.njnt} joints")


def render_view(cam_name='main'):
    global anim_time
    ensure_initialized()
    
    # Auto-animate joints with sine wave
    if auto_animate:
        import math
        anim_time += 0.05
        for jname in joint_controls:
            # Oscillate within joint limits
            joint_controls[jname] = math.sin(anim_time) * 1.2  # ±1.2 radians (~70°)
    
    # Apply controls directly to joint positions
    for i in range(model.njnt):
        jname = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, i)
        if jname and jname in joint_controls:
            data.qpos[i] = joint_controls[jname]
    
    mujoco.mj_forward(model, data)  # Update positions without physics
    
    cam = cameras.get(cam_name, cameras['main'])
    renderer.update_scene(data, cam)
    return renderer.render()


HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>MuJoCo Viewer</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { background: #0a0a1a; color: #fff; font-family: system-ui, sans-serif; }
        .wrap { display: flex; height: 100vh; }
        .views { flex: 1; display: grid; grid-template-columns: 2fr 1fr; grid-template-rows: 1fr 1fr; gap: 4px; padding: 4px; }
        .view { background: #111; border-radius: 4px; overflow: hidden; position: relative; }
        .view.main { grid-row: span 2; }
        .view img { width: 100%; height: 100%; object-fit: contain; }
        .view-label { position: absolute; top: 4px; left: 8px; font-size: 11px; color: #666; }
        .sidebar { width: 220px; background: #0f1525; padding: 12px; overflow-y: auto; }
        h1 { font-size: 14px; color: #0cf; margin-bottom: 12px; }
        h2 { font-size: 10px; color: #555; text-transform: uppercase; margin: 12px 0 6px; }
        .ctrl { margin-bottom: 10px; }
        .ctrl label { display: block; font-size: 11px; color: #888; margin-bottom: 2px; }
        .ctrl input { width: 100%; accent-color: #0cf; }
        .ctrl .val { font-size: 10px; color: #444; text-align: right; }
        .status { position: fixed; bottom: 8px; left: 8px; font-size: 11px; color: #4f4; background: #0008; padding: 4px 10px; border-radius: 10px; }
    </style>
</head>
<body>
    <div class="wrap">
        <div class="views">
            <div class="view main" id="v-main"><span class="view-label">Main</span><img id="img-main"></div>
            <div class="view" id="v-front"><span class="view-label">Front</span><img id="img-front"></div>
            <div class="view" id="v-top"><span class="view-label">Top</span><img id="img-top"></div>
        </div>
        <div class="sidebar">
            <h1>🤖 Robot Viewer</h1>
            <h2>Joints</h2>
            <div id="ctrls"></div>
        </div>
    </div>
    <div class="status" id="st">--</div>
    <script>
        const imgs = { main: document.getElementById('img-main'), front: document.getElementById('img-front'), top: document.getElementById('img-top') };
        const st = document.getElementById('st');
        let fc = 0, lt = Date.now();
        
        // Load joints
        fetch('/joints').then(r => r.json()).then(js => {
            const ctrls = document.getElementById('ctrls');
            for (const [n, info] of Object.entries(js)) {
                const r = info.range || [-3.14, 3.14];
                const d = document.createElement('div');
                d.className = 'ctrl';
                d.innerHTML = `<label>${n.replace(/_/g,' ')}</label><input type="range" min="${r[0]}" max="${r[1]}" step="0.02" value="0"><div class="val">0.00</div>`;
                const inp = d.querySelector('input'), val = d.querySelector('.val');
                inp.oninput = () => {
                    val.textContent = parseFloat(inp.value).toFixed(2);
                    fetch('/c', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({j:n, v:parseFloat(inp.value)})});
                };
                ctrls.appendChild(d);
            }
        });
        
        // Camera drag on main view
        const mainView = document.getElementById('v-main');
        let drag = false, lx = 0, ly = 0, cam = {az: 135, el: -25, dist: 0.3};
        mainView.onmousedown = e => { drag = true; lx = e.clientX; ly = e.clientY; e.preventDefault(); };
        document.onmouseup = () => drag = false;
        document.onmousemove = e => {
            if (!drag) return;
            cam.az += (e.clientX - lx) * 0.3;
            cam.el = Math.max(-89, Math.min(89, cam.el + (e.clientY - ly) * 0.3));
            lx = e.clientX; ly = e.clientY;
            fetch('/cam', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(cam)});
        };
        mainView.onwheel = e => {
            e.preventDefault();
            cam.dist = Math.max(0.05, Math.min(2, cam.dist + e.deltaY * 0.0005));
            fetch('/cam', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(cam)});
        };
        
        // Frame loop - load all views
        async function loop() {
            const t0 = performance.now();
            try {
                // Load all views in parallel
                const [main, front, top] = await Promise.all([
                    fetch('/f/main').then(r => r.blob()),
                    fetch('/f/front').then(r => r.blob()),
                    fetch('/f/top').then(r => r.blob())
                ]);
                imgs.main.src = URL.createObjectURL(main);
                imgs.front.src = URL.createObjectURL(front);
                imgs.top.src = URL.createObjectURL(top);
                
                fc++;
                if (Date.now() - lt > 1000) { st.textContent = fc + ' FPS'; fc = 0; lt = Date.now(); }
            } catch(e) { st.textContent = 'err'; }
            setTimeout(loop, 16);  // ~60 FPS target
        }
        loop();
    </script>
</body>
</html>
'''


@app.route('/')
def index():
    return render_template_string(HTML)


@app.route('/f/<view>')
def frame(view):
    from PIL import Image
    pixels = render_view(view)
    img = Image.fromarray(pixels)
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=JPEG_QUALITY)
    buf.seek(0)
    return Response(buf.getvalue(), mimetype='image/jpeg')


@app.route('/frame')
def frame_default():
    return frame('main')


@app.route('/joints')
def joints():
    ensure_initialized()
    info = {}
    for i in range(model.njnt):
        n = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, i)
        if n:
            lim = model.jnt_limited[i]
            rng = [float(model.jnt_range[i,0]), float(model.jnt_range[i,1])] if lim else [-3.14, 3.14]
            info[n] = {'range': rng}
    return jsonify(info)


@app.route('/c', methods=['POST'])
def ctrl():
    d = request.json
    if d.get('j') in joint_controls:
        joint_controls[d['j']] = float(d.get('v', 0))
    return jsonify({'ok': True})


@app.route('/cam', methods=['POST'])
def cam():
    ensure_initialized()
    d = request.json
    c = cameras['main']
    c.azimuth = d.get('az', c.azimuth)
    c.elevation = d.get('el', c.elevation)
    c.distance = d.get('dist', c.distance)
    return jsonify({'ok': True})


if __name__ == '__main__':
    try:
        from PIL import Image
    except ImportError:
        import subprocess
        subprocess.run(['pip', 'install', 'pillow', '-q'])
    
    print(f"\n🚀 MuJoCo Viewer: http://localhost:{PORT}\n")
    app.run(host='0.0.0.0', port=PORT, threaded=False)  # Single-threaded for OSMesa safety
