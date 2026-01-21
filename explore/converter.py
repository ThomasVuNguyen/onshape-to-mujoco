#!/usr/bin/env python3
"""
Convert Onshape assembly to MuJoCo MJCF with proper transforms.
"""
import json
import math
import numpy as np
from pathlib import Path
from scipy.spatial.transform import Rotation

OUTPUT_DIR = Path(__file__).parent / 'output'
MJCF_PATH = Path(__file__).parent / 'robot.xml'


def load_json(name):
    with open(OUTPUT_DIR / name) as f:
        return json.load(f)


def transform_to_pos_quat(t):
    """Convert Onshape 4x4 transform to pos and quat.
    
    Onshape uses column-major layout:
    [r00, r10, r20, tx, r01, r11, r21, ty, r02, r12, r22, tz, 0, 0, 0, 1]
    """
    # Position is at indices 3, 7, 11
    pos = np.array([t[3], t[7], t[11]])
    
    # Rotation matrix columns
    rot = np.array([
        [t[0], t[4], t[8]],
        [t[1], t[5], t[9]], 
        [t[2], t[6], t[10]]
    ])
    
    r = Rotation.from_matrix(rot)
    quat = r.as_quat()  # [x, y, z, w] scipy format
    # MuJoCo uses [w, x, y, z]
    quat_mujoco = [quat[3], quat[0], quat[1], quat[2]]
    return pos, quat_mujoco


def main():
    assembly = load_json('03_assembly_definition.json')
    meshes = load_json('08_exported_meshes.json')
    
    root = assembly['rootAssembly']
    instances = {inst['id']: inst for inst in root['instances']}
    occurrences = {occ['path'][0]: occ for occ in root['occurrences']}
    mesh_map = {m['instanceId']: m['filename'] for m in meshes}
    
    # Find the fixed part (base)
    fixed_id = None
    for occ in root['occurrences']:
        if occ.get('fixed'):
            fixed_id = occ['path'][0]
            break
    
    if not fixed_id:
        # Default to motor
        for id, inst in instances.items():
            if 'motor' in inst['name'].lower():
                fixed_id = id
                break
    
    print(f"Base (fixed): {instances[fixed_id]['name']}")
    
    # Get base transform (to use as reference)
    base_occ = occurrences[fixed_id]
    base_pos, base_quat = transform_to_pos_quat(base_occ['transform'])
    
    print("\nPart positions (world frame):")
    for id, occ in occurrences.items():
        name = instances[id]['name']
        pos, quat = transform_to_pos_quat(occ['transform'])
        print(f"  {name}: pos=({pos[0]:.4f}, {pos[1]:.4f}, {pos[2]:.4f})")
    
    # Find cylindrical mate (servo rotation)
    for feat in root['features']:
        fd = feat['featureData']
        if fd['mateType'] == 'CYLINDRICAL':
            ents = fd['matedEntities']
            horn_id = ents[0]['matedOccurrence'][0]
            motor_id = ents[1]['matedOccurrence'][0]
            horn_name = instances[horn_id]['name']
            motor_name = instances[motor_id]['name']
            print(f"\nCylindrical mate: {horn_name} rotates on {motor_name}")
            
            # Get joint axis from mate connector
            cs = ents[0]['matedCS']
            axis = cs['zAxis']  # Rotation axis
            origin = cs['origin']  # Joint origin
            print(f"  Axis: {axis}")
            print(f"  Origin: {origin}")
    
    # Generate MJCF
    # For simplicity: motor as base, horn rotates on motor
    motor_id = None
    horn_id = None
    joint1_id = None
    joint2_id = None
    
    for id, inst in instances.items():
        name = inst['name'].lower()
        if 'motor' in name:
            motor_id = id
        elif 'horn' in name:
            horn_id = id
        elif 'joint #1' in name or 'joint_1' in name:
            joint1_id = id
        elif 'joint #2' in name or 'joint_2' in name:
            joint2_id = id
    
    # Get transforms
    motor_pos, motor_quat = transform_to_pos_quat(occurrences[motor_id]['transform'])
    horn_pos, horn_quat = transform_to_pos_quat(occurrences[horn_id]['transform'])
    j1_pos, j1_quat = transform_to_pos_quat(occurrences[joint1_id]['transform'])
    j2_pos, j2_quat = transform_to_pos_quat(occurrences[joint2_id]['transform'])
    
    def fmt_pos(p):
        return f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f}"
    
    def fmt_quat(q):
        return f"{q[0]:.6f} {q[1]:.6f} {q[2]:.6f} {q[3]:.6f}"
    
    # Compute relative transforms
    # Horn relative to motor
    horn_rel = horn_pos - motor_pos
    j2_rel = j2_pos - motor_pos
    j1_rel = j1_pos - horn_pos  # J1 attached to horn
    
    print(f"\nRelative positions:")
    print(f"  Horn from Motor: {horn_rel}")
    print(f"  J2 from Motor: {j2_rel}")
    print(f"  J1 from Horn: {j1_rel}")
    
    mjcf = f'''<mujoco model="onshape_robot">
  <compiler angle="radian" meshdir="output/meshes" autolimits="true"/>
  <option gravity="0 0 -9.81" timestep="0.002"/>
  
  <visual>
    <global offwidth="1280" offheight="720"/>
  </visual>
  
  <asset>
    <texture name="grid" type="2d" builtin="checker" rgb1="0.1 0.2 0.3" rgb2="0.2 0.3 0.4" width="512" height="512"/>
    <material name="grid_mat" texture="grid" texrepeat="5 5" reflectance="0.2"/>
    <material name="pla_orange" rgba="1.0 0.6 0.1 1"/>
    <material name="pla_gray" rgba="0.3 0.3 0.3 1"/>
    <material name="pla_blue" rgba="0.2 0.4 0.8 1"/>
    <mesh name="Motor" file="{mesh_map[motor_id]}"/>
    <mesh name="Horn" file="{mesh_map[horn_id]}"/>
    <mesh name="Joint_1" file="{mesh_map[joint1_id]}"/>
    <mesh name="Joint_2" file="{mesh_map[joint2_id]}"/>
  </asset>
  
  <worldbody>
    <geom name="ground" type="plane" size="1 1 0.1" pos="0 0 0" material="grid_mat"/>
    <light name="light" pos="0.3 0.3 0.5" dir="-0.3 -0.3 -0.5"/>
    
    <!-- Motor (base) -->
    <body name="motor" pos="{fmt_pos(motor_pos)}" quat="{fmt_quat(motor_quat)}">
      <inertial pos="0 0 0" mass="0.055" diaginertia="0.00001 0.00001 0.00001"/>
      <geom type="mesh" mesh="Motor" material="pla_gray"/>
      
      <!-- Joint #2 (fixed to motor) -->
      <body name="joint_2" pos="{fmt_pos(j2_rel)}">
        <inertial pos="0 0 0" mass="0.01" diaginertia="0.000001 0.000001 0.000001"/>
        <geom type="mesh" mesh="Joint_2" material="pla_orange" 
              quat="{fmt_quat(j2_quat)}"/>
      </body>
      
      <!-- Horn (rotates on motor via servo) -->
      <body name="horn" pos="{fmt_pos(horn_rel)}">
        <inertial pos="0 0 0" mass="0.003" diaginertia="0.000001 0.000001 0.000001"/>
        <joint name="servo_rotation" type="hinge" axis="0 -1 0" range="-1.5708 1.5708" damping="0.01"/>
        <geom type="mesh" mesh="Horn" material="pla_blue"
              quat="{fmt_quat(horn_quat)}"/>
        
        <!-- Joint #1 (attached to horn) -->
        <body name="joint_1" pos="{fmt_pos(j1_rel)}">
          <inertial pos="0 0 0" mass="0.01" diaginertia="0.000001 0.000001 0.000001"/>
          <geom type="mesh" mesh="Joint_1" material="pla_orange"
                quat="{fmt_quat(j1_quat)}"/>
        </body>
      </body>
    </body>
  </worldbody>
  
  <actuator>
    <motor name="servo" joint="servo_rotation" gear="100" ctrllimited="true" ctrlrange="-1 1"/>
  </actuator>
</mujoco>
'''
    
    with open(MJCF_PATH, 'w') as f:
        f.write(mjcf)
    
    print(f"\n✓ Generated: {MJCF_PATH}")


if __name__ == '__main__':
    main()
