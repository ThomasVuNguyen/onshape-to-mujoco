#!/usr/bin/env python3
"""
Pre-process STL files to set correct rotation origin for MuJoCo
"""
import struct
import numpy as np
import os

def read_stl_binary(filepath):
    """Read binary STL file and return vertices and faces."""
    with open(filepath, 'rb') as f:
        header = f.read(80)
        num_triangles = struct.unpack('<I', f.read(4))[0]
        
        vertices = []
        faces = []
        
        for i in range(num_triangles):
            # Normal (3 floats)
            normal = struct.unpack('<3f', f.read(12))
            
            # 3 vertices (3 floats each)
            v1 = struct.unpack('<3f', f.read(12))
            v2 = struct.unpack('<3f', f.read(12))
            v3 = struct.unpack('<3f', f.read(12))
            
            # Attribute byte count
            attr = struct.unpack('<H', f.read(2))[0]
            
            base = len(vertices)
            vertices.extend([v1, v2, v3])
            faces.append((base, base+1, base+2, normal))
        
        return np.array(vertices), faces

def write_stl_binary(filepath, vertices, faces, header=None):
    """Write binary STL file."""
    if header is None:
        header = b'Binary STL processed for MuJoCo' + b' ' * 48
    header = header[:80].ljust(80, b'\x00')
    
    with open(filepath, 'wb') as f:
        f.write(header)
        f.write(struct.pack('<I', len(faces)))
        
        for face_idx, (v1_idx, v2_idx, v3_idx, normal) in enumerate(faces):
            # Recalculate normal from new vertices
            v1 = vertices[v1_idx]
            v2 = vertices[v2_idx]
            v3 = vertices[v3_idx]
            
            edge1 = v2 - v1
            edge2 = v3 - v1
            new_normal = np.cross(edge1, edge2)
            norm = np.linalg.norm(new_normal)
            if norm > 0:
                new_normal = new_normal / norm
            
            f.write(struct.pack('<3f', *new_normal))
            f.write(struct.pack('<3f', *v1))
            f.write(struct.pack('<3f', *v2))
            f.write(struct.pack('<3f', *v3))
            f.write(struct.pack('<H', 0))

def shift_stl_origin(input_path, output_path, offset):
    """Shift all vertices in STL by given offset."""
    vertices, faces = read_stl_binary(input_path)
    
    print(f"  Original bounds: ({vertices.min(axis=0)}) to ({vertices.max(axis=0)})")
    print(f"  Applying offset: {offset}")
    
    # Shift vertices
    shifted_vertices = vertices - np.array(offset)
    
    print(f"  New bounds: ({shifted_vertices.min(axis=0)}) to ({shifted_vertices.max(axis=0)})")
    
    write_stl_binary(output_path, shifted_vertices, faces)
    print(f"  Saved: {output_path}")

def main():
    # Motor shaft world position (calculated from cylindrical mate)
    # Motor world: (0.2317, -0.0042, 0.0341)
    # Motor local mate: (-0.01025, 0.0325, 0)
    # Motor shaft world: (0.2317 - 0.01025, -0.0042 + 0.0325, 0.0341) = (0.2215, 0.0283, 0.0341)
    
    motor_shaft = np.array([0.2215, 0.0283, 0.0341])
    
    mesh_dir = 'output/meshes'
    processed_dir = 'output/meshes_processed'
    os.makedirs(processed_dir, exist_ok=True)
    
    # Parts that rotate around motor shaft need origin at motor shaft
    rotating_parts = ['Horn__2__JFD.stl', 'Joint__1__2__JoD.stl']
    
    # Static parts keep their original coordinates (or use motor center as reference)
    # For consistency, let's shift all parts so motor shaft is at origin
    all_parts = ['Horn__2__JFD.stl', 'Joint__1__2__JoD.stl', 
                 'mg996r_motor__2__JFD.stl', 'Joint__2__2__JID.stl']
    
    print("Processing STL files to set origin at motor shaft...")
    print(f"Motor shaft world position: {motor_shaft}")
    print()
    
    for part_file in all_parts:
        input_path = os.path.join(mesh_dir, part_file)
        output_path = os.path.join(processed_dir, part_file)
        
        if os.path.exists(input_path):
            print(f"Processing: {part_file}")
            shift_stl_origin(input_path, output_path, motor_shaft)
            print()
        else:
            print(f"WARNING: Not found: {input_path}")

if __name__ == '__main__':
    main()
