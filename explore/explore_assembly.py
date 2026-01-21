#!/usr/bin/env python3
"""
Comprehensive Onshape Assembly Explorer

This script extracts ALL available data from an Onshape assembly:
- Assembly structure (parts, sub-assemblies, occurrences)
- Mate features (joints/constraints with parameters)
- Mass properties (mass, inertia, center of mass)
- Part geometry (exported as STL)
- Transform matrices for each instance

All data is saved to the output/ directory for analysis.
"""
import os
import json
from pathlib import Path
from dotenv import load_dotenv
from onshape_client import OnshapeClient

load_dotenv()

# Configuration from environment
DOCUMENT_ID = os.getenv('DOCUMENT_ID')
WORKSPACE_ID = os.getenv('WORKSPACE_ID')
ELEMENT_ID = os.getenv('ELEMENT_ID')

OUTPUT_DIR = Path(__file__).parent / 'output'
MESH_DIR = OUTPUT_DIR / 'meshes'


def save_json(data: dict, filename: str):
    """Save data as formatted JSON."""
    filepath = OUTPUT_DIR / filename
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"  Saved: {filepath}")


def explore_document(client: OnshapeClient):
    """Get document-level information."""
    print("\n" + "="*60)
    print("1. DOCUMENT INFORMATION")
    print("="*60)
    
    doc = client.get_document(DOCUMENT_ID)
    save_json(doc, '01_document.json')
    
    print(f"  Name: {doc.get('name', 'Unknown')}")
    print(f"  Owner: {doc.get('owner', {}).get('name', 'Unknown')}")
    print(f"  Created: {doc.get('createdAt', 'Unknown')}")
    
    # Get all elements in the document
    elements = client.get_document_elements(DOCUMENT_ID, WORKSPACE_ID)
    save_json(elements, '02_document_elements.json')
    
    print(f"\n  Elements in document:")
    for elem in elements:
        print(f"    - {elem.get('name')} ({elem.get('elementType')}): {elem.get('id')}")
    
    return doc, elements


def explore_assembly_definition(client: OnshapeClient):
    """Get the complete assembly definition."""
    print("\n" + "="*60)
    print("2. ASSEMBLY DEFINITION")
    print("="*60)
    
    assembly = client.get_assembly_definition(
        DOCUMENT_ID, WORKSPACE_ID, ELEMENT_ID,
        include_mate_features=True,
        include_mate_connectors=True
    )
    save_json(assembly, '03_assembly_definition.json')
    
    # Parse root assembly info
    root = assembly.get('rootAssembly', {})
    instances = root.get('instances', [])
    occurrences = root.get('occurrences', [])
    
    print(f"\n  Root Assembly:")
    print(f"    Instances: {len(instances)}")
    print(f"    Occurrences: {len(occurrences)}")
    
    # List all instances
    print(f"\n  Instances:")
    for inst in instances:
        inst_type = inst.get('type', 'Unknown')
        name = inst.get('name', 'Unnamed')
        inst_id = inst.get('id', '')
        print(f"    - [{inst_type}] {name} (id: {inst_id[:20]}...)")
    
    # Check for sub-assemblies
    sub_assemblies = assembly.get('subAssemblies', [])
    if sub_assemblies:
        print(f"\n  Sub-Assemblies: {len(sub_assemblies)}")
        for sub in sub_assemblies:
            print(f"    - {sub.get('documentId', '')[:12]}...")
    
    # Parts information
    parts = assembly.get('parts', [])
    print(f"\n  Parts: {len(parts)}")
    for part in parts[:10]:  # First 10
        part_name = part.get('name', 'Unnamed')
        part_id = part.get('partId', '')[:20]
        print(f"    - {part_name} (partId: {part_id}...)")
    if len(parts) > 10:
        print(f"    ... and {len(parts) - 10} more")
    
    return assembly


def explore_assembly_features(client: OnshapeClient):
    """Get all features including mates."""
    print("\n" + "="*60)
    print("3. ASSEMBLY FEATURES (MATES)")
    print("="*60)
    
    features = client.get_assembly_features(DOCUMENT_ID, WORKSPACE_ID, ELEMENT_ID)
    save_json(features, '04_assembly_features.json')
    
    feature_list = features.get('features', [])
    print(f"\n  Total Features: {len(feature_list)}")
    
    # Categorize features
    mate_types = {}
    for feat in feature_list:
        feat_type = feat.get('featureType', 'unknown')
        if feat_type not in mate_types:
            mate_types[feat_type] = []
        mate_types[feat_type].append(feat)
    
    print(f"\n  Feature Types:")
    for ftype, flist in mate_types.items():
        print(f"    {ftype}: {len(flist)}")
    
    # Detailed mate info
    print(f"\n  Mate Details:")
    for feat in feature_list:
        if feat.get('featureType') in ['mate', 'mateConnector']:
            name = feat.get('name', 'Unnamed')
            ftype = feat.get('featureType')
            suppressed = feat.get('suppressed', False)
            
            # Get mate type from parameters
            mate_type = 'unknown'
            params = feat.get('parameters', [])
            for param in params:
                if param.get('parameterId') == 'mateType':
                    mate_type = param.get('value', 'unknown')
                    break
            
            status = " [SUPPRESSED]" if suppressed else ""
            print(f"    - {name} ({ftype}/{mate_type}){status}")
            
            # Print key parameters
            for param in params:
                param_id = param.get('parameterId', '')
                if param_id in ['limitAxialZMin', 'limitAxialZMax', 'limitZMin', 'limitZMax',
                               'limitsEnabled', 'offset', 'rotationType']:
                    value = param.get('value', param.get('expression', ''))
                    print(f"        {param_id}: {value}")
    
    return features


def explore_bill_of_materials(client: OnshapeClient):
    """Get the Bill of Materials."""
    print("\n" + "="*60)
    print("4. BILL OF MATERIALS")
    print("="*60)
    
    try:
        bom = client.get_assembly_bom(DOCUMENT_ID, WORKSPACE_ID, ELEMENT_ID)
        save_json(bom, '05_bill_of_materials.json')
        
        items = bom.get('bomTable', {}).get('items', [])
        print(f"\n  BOM Items: {len(items)}")
        for item in items[:10]:
            name = item.get('name', 'Unnamed')
            qty = item.get('quantity', 1)
            print(f"    - {name} x{qty}")
    except Exception as e:
        print(f"  Warning: Could not fetch BOM: {e}")


def explore_mass_properties(client: OnshapeClient, assembly: dict):
    """Get mass properties for all parts."""
    print("\n" + "="*60)
    print("5. MASS PROPERTIES")
    print("="*60)
    
    parts = assembly.get('parts', [])
    mass_data = {}
    
    print(f"\n  Fetching mass properties for {len(parts)} parts...")
    
    for i, part in enumerate(parts):
        part_id = part.get('partId')
        doc_id = part.get('documentId')
        elem_id = part.get('elementId')
        part_name = part.get('name', 'Unnamed')
        
        if not all([part_id, doc_id, elem_id]):
            continue
            
        try:
            # Use workspace ID from our assembly for linked docs
            props = client.get_part_mass_properties(
                doc_id, WORKSPACE_ID, elem_id, part_id
            )
            mass_data[part_id] = {
                'name': part_name,
                'properties': props
            }
            
            # Print summary
            bodies = props.get('bodies', {})
            for body_id, body in bodies.items():
                mass = body.get('mass', [0])[0] if isinstance(body.get('mass'), list) else body.get('mass', 0)
                print(f"    [{i+1}/{len(parts)}] {part_name}: {mass:.6f} kg")
                break
                
        except Exception as e:
            print(f"    [{i+1}/{len(parts)}] {part_name}: Error - {str(e)[:50]}")
    
    save_json(mass_data, '06_mass_properties.json')
    return mass_data


def explore_transforms(assembly: dict):
    """Extract and analyze transform matrices."""
    print("\n" + "="*60)
    print("6. TRANSFORM MATRICES")
    print("="*60)
    
    root = assembly.get('rootAssembly', {})
    occurrences = root.get('occurrences', [])
    
    transforms = {}
    print(f"\n  Occurrences with transforms: {len(occurrences)}")
    
    for occ in occurrences:
        path = occ.get('path', [])
        transform = occ.get('transform', [])
        hidden = occ.get('hidden', False)
        
        # Path is a list of instance IDs
        path_str = '/'.join(path)
        
        transforms[path_str] = {
            'path': path,
            'transform': transform,  # 16-element list (4x4 matrix, column-major)
            'hidden': hidden
        }
        
        if len(path) == 1:  # Top-level instances
            status = " [HIDDEN]" if hidden else ""
            print(f"    - {path[0][:20]}...{status}")
            if transform:
                # Extract position from transform matrix (last column)
                x, y, z = transform[12], transform[13], transform[14]
                print(f"        Position: ({x:.4f}, {y:.4f}, {z:.4f})")
    
    save_json(transforms, '07_transforms.json')
    return transforms


def export_meshes(client: OnshapeClient, assembly: dict):
    """Export STL meshes for all parts."""
    print("\n" + "="*60)
    print("7. EXPORTING MESHES (STL)")
    print("="*60)
    
    MESH_DIR.mkdir(parents=True, exist_ok=True)
    
    # Get unique parts from instances (they have the real part info)
    root = assembly.get('rootAssembly', {})
    instances = root.get('instances', [])
    
    exported = []
    seen_parts = set()
    
    print(f"\n  Exporting parts as STL...")
    
    for i, inst in enumerate(instances):
        if inst.get('type') != 'Part':
            continue
            
        part_id = inst.get('partId')
        doc_id = inst.get('documentId')
        elem_id = inst.get('elementId')
        part_name = inst.get('name', 'Unnamed')
        
        # Skip duplicates
        key = (doc_id, elem_id, part_id)
        if key in seen_parts:
            continue
        seen_parts.add(key)
        
        if not all([part_id, doc_id, elem_id]):
            continue
        
        # Create safe filename
        safe_name = "".join(c if c.isalnum() or c in '-_' else '_' for c in part_name)
        filename = f"{safe_name}_{part_id}.stl"
        filepath = MESH_DIR / filename
        
        try:
            # Export using the part's own document/element context
            stl_data = client.export_stl(doc_id, WORKSPACE_ID, elem_id, part_id)
            with open(filepath, 'wb') as f:
                f.write(stl_data)
            
            size_kb = len(stl_data) / 1024
            print(f"    [{len(exported)+1}] {part_name}: {size_kb:.1f} KB")
            
            exported.append({
                'partId': part_id,
                'name': part_name,
                'filename': filename,
                'size_bytes': len(stl_data),
                'instanceId': inst.get('id')
            })
        except Exception as e:
            print(f"    [!] {part_name}: Error - {str(e)[:60]}")
    
    save_json(exported, '08_exported_meshes.json')
    return exported


def analyze_for_mujoco(assembly: dict, features: dict, mass_data: dict):
    """Analyze the data and create a summary for MuJoCo mapping."""
    print("\n" + "="*60)
    print("8. MUJOCO MAPPING ANALYSIS")
    print("="*60)
    
    analysis = {
        'summary': {},
        'bodies': [],
        'joints': [],
        'potential_issues': []
    }
    
    # Analyze parts → bodies
    parts = assembly.get('parts', [])
    analysis['summary']['total_parts'] = len(parts)
    
    for part in parts:
        part_id = part.get('partId', '')
        name = part.get('name', 'Unnamed')
        
        body_info = {
            'name': name,
            'part_id': part_id,
            'has_mass': part_id in mass_data,
            'mujoco_element': '<body>'
        }
        
        if part_id in mass_data:
            props = mass_data[part_id].get('properties', {})
            bodies = props.get('bodies', {})
            for body in bodies.values():
                body_info['mass'] = body.get('mass', [0])[0] if isinstance(body.get('mass'), list) else body.get('mass', 0)
                body_info['centroid'] = body.get('centroid', [])
                body_info['inertia'] = body.get('inertia', [])
                break
        
        analysis['bodies'].append(body_info)
    
    # Analyze mates → joints
    feature_list = features.get('features', [])
    mate_mapping = {
        'FASTENED': {'mujoco': None, 'description': 'Welded (no joint needed)'},
        'REVOLUTE': {'mujoco': 'hinge', 'description': 'Single rotation axis'},
        'SLIDER': {'mujoco': 'slide', 'description': 'Single translation axis'},
        'CYLINDRICAL': {'mujoco': 'hinge+slide', 'description': 'Rotation + translation on same axis'},
        'BALL': {'mujoco': 'ball', 'description': '3-DOF spherical joint'},
        'PLANAR': {'mujoco': 'free (constrained)', 'description': 'Complex - may need multiple joints'},
        'PARALLEL': {'mujoco': None, 'description': 'Orientation constraint only'},
    }
    
    for feat in feature_list:
        if feat.get('featureType') != 'mate':
            continue
            
        name = feat.get('name', 'Unnamed')
        suppressed = feat.get('suppressed', False)
        
        if suppressed:
            continue
        
        # Extract mate type and limits
        mate_type = 'UNKNOWN'
        limits = {}
        for param in feat.get('parameters', []):
            pid = param.get('parameterId', '')
            if pid == 'mateType':
                mate_type = param.get('value', 'UNKNOWN')
            elif 'limit' in pid.lower():
                limits[pid] = param.get('value', param.get('expression', ''))
        
        mapping = mate_mapping.get(mate_type, {'mujoco': 'unknown', 'description': 'Unknown mate type'})
        
        joint_info = {
            'name': name,
            'onshape_type': mate_type,
            'mujoco_type': mapping['mujoco'],
            'description': mapping['description'],
            'limits': limits,
            'has_limits': bool(limits)
        }
        analysis['joints'].append(joint_info)
        
        if mapping['mujoco'] == 'unknown':
            analysis['potential_issues'].append(f"Unknown mate type: {mate_type} in {name}")
    
    # Summary
    analysis['summary']['total_joints'] = len(analysis['joints'])
    analysis['summary']['mate_types'] = {}
    for j in analysis['joints']:
        mt = j['onshape_type']
        analysis['summary']['mate_types'][mt] = analysis['summary']['mate_types'].get(mt, 0) + 1
    
    save_json(analysis, '09_mujoco_analysis.json')
    
    # Print summary
    print(f"\n  Bodies (parts): {analysis['summary']['total_parts']}")
    print(f"  Joints (mates): {analysis['summary']['total_joints']}")
    
    print(f"\n  Mate Type Distribution:")
    for mt, count in analysis['summary']['mate_types'].items():
        mapping = mate_mapping.get(mt, {})
        mj = mapping.get('mujoco', '?')
        print(f"    {mt}: {count} → MuJoCo: {mj}")
    
    if analysis['potential_issues']:
        print(f"\n  Potential Issues:")
        for issue in analysis['potential_issues']:
            print(f"    ⚠ {issue}")
    
    return analysis


def main():
    """Main exploration routine."""
    print("="*60)
    print("ONSHAPE ASSEMBLY EXPLORER")
    print("="*60)
    print(f"\nDocument: {DOCUMENT_ID}")
    print(f"Workspace: {WORKSPACE_ID}")
    print(f"Element: {ELEMENT_ID}")
    
    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Initialize client
    client = OnshapeClient()
    print("\n✓ API client initialized")
    
    # Run all explorations (skip document info - not essential)
    # doc, elements = explore_document(client)  # Skip - can 404 on some docs
    assembly = explore_assembly_definition(client)
    features = explore_assembly_features(client)
    explore_bill_of_materials(client)
    mass_data = explore_mass_properties(client, assembly)
    explore_transforms(assembly)
    export_meshes(client, assembly)
    analysis = analyze_for_mujoco(assembly, features, mass_data)
    
    print("\n" + "="*60)
    print("EXPLORATION COMPLETE")
    print("="*60)
    print(f"\nAll data saved to: {OUTPUT_DIR}")
    print("\nKey files for MuJoCo conversion:")
    print("  - 03_assembly_definition.json  (structure)")
    print("  - 04_assembly_features.json    (mates/joints)")
    print("  - 06_mass_properties.json      (physics)")
    print("  - 07_transforms.json           (positions)")
    print("  - 09_mujoco_analysis.json      (mapping summary)")
    print("  - meshes/                      (STL geometry)")


if __name__ == '__main__':
    main()
