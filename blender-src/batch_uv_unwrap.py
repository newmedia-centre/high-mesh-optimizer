import bpy
import os
import sys
import re

# Get command line arguments after --
argv = sys.argv
argv = argv[argv.index("--") + 1:] if "--" in argv else []

if len(argv) < 1:
    print("Usage: blender --background --python batch_uv_unwrap.py -- input_directory [output_directory] [margin] [island_margin]")
    print("  margin: Unwrap margin (default: 0.001)")
    print("  island_margin: Island margin (default: 0.02)")
    sys.exit(1)

# Get input and output directories and parameters
input_dir = argv[0].strip('"\'')  # Remove any quotes
output_dir = argv[1].strip('"\'') if len(argv) > 1 else input_dir
unwrap_margin = float(argv[2]) if len(argv) > 2 else 0.001
island_margin = float(argv[3]) if len(argv) > 3 else 0.02

# Fix any square brackets in paths which can cause issues on Windows
input_dir = input_dir.replace('[', '_').replace(']', '_')
output_dir = output_dir.replace('[', '_').replace(']', '_')

print(f"Sanitized Input directory: {input_dir}")
print(f"Sanitized Output directory: {output_dir}")
print(f"Unwrap margin: {unwrap_margin}")
print(f"Island margin: {island_margin}")

# Ensure paths are absolute and normalized
input_dir = os.path.abspath(os.path.normpath(input_dir))
output_dir = os.path.abspath(os.path.normpath(output_dir))

# Create output directory if it doesn't exist
if not os.path.exists(output_dir):
    try:
        os.makedirs(output_dir, exist_ok=True)
        print(f"Created output directory: {output_dir}")
    except Exception as e:
        print(f"Error creating output directory: {str(e)}")
        sys.exit(1)

# Set to object mode and deselect all
def set_mode_object():
    if bpy.context.active_object and bpy.context.active_object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')

# Clear all objects in the scene
def clear_scene():
    set_mode_object()
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()

# Process each model file in the input directory
def process_models(input_directory, output_directory, margin, island_margin):
    # Supported file extensions
    model_extensions = ['.obj', '.fbx', '.3ds', '.dae', '.ply', '.stl', '.glb', '.gltf']
    
    # Check if input directory exists
    if not os.path.exists(input_directory):
        print(f"Input directory not found: {input_directory}")
        return
    
    # List files in the directory
    try:
        files = os.listdir(input_directory)
        print(f"Found {len(files)} files in input directory")
    except Exception as e:
        print(f"Error listing files in input directory: {str(e)}")
        return
    
    for filename in files:
        file_path = os.path.join(input_directory, filename)
        file_extension = os.path.splitext(filename)[1].lower()
        
        # Skip if it's not a model file
        if file_extension not in model_extensions:
            continue
        
        print(f"Processing: {filename}")
        
        # Clear the scene before importing new model
        clear_scene()
        
        # Import the model based on file extension
        try:
            if file_extension == '.obj':
                # For Blender 4.4
                bpy.ops.wm.obj_import(filepath=file_path)
            elif file_extension == '.fbx':
                bpy.ops.wm.fbx_import(filepath=file_path)
            elif file_extension == '.3ds':
                bpy.ops.wm.autodesk_3ds_import(filepath=file_path)
            elif file_extension == '.dae':
                bpy.ops.wm.collada_import(filepath=file_path)
            elif file_extension == '.ply':
                bpy.ops.wm.ply_import(filepath=file_path)
            elif file_extension == '.stl':
                bpy.ops.wm.stl_import(filepath=file_path)
            elif file_extension in ['.glb', '.gltf']:
                bpy.ops.wm.gltf_import(filepath=file_path)
        except Exception as e:
            print(f"Error importing {filename}: {str(e)}")
            continue
        
        # Select all objects and join them if multiple objects were imported
        objects = bpy.context.scene.objects
        mesh_objects = [obj for obj in objects if obj.type == 'MESH']
        
        if not mesh_objects:
            print(f"No mesh objects found in {filename}, skipping...")
            continue
            
        # Select all mesh objects
        for obj in mesh_objects:
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
        
        # Join objects if there are multiple
        if len(mesh_objects) > 1:
            bpy.ops.object.join()
        
        # Get the active object
        obj = bpy.context.active_object
          
        # Perform UV unwrapping
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        
        # First create a new UV map if none exists
        if not obj.data.uv_layers:
            bpy.ops.mesh.uv_texture_add()
        
        # Perform Smart UV Project (automatic unwrapping)
        bpy.ops.uv.smart_project(
            angle_limit=66.0,
            island_margin=island_margin,
            area_weight=0.0,
            correct_aspect=True,
            scale_to_bounds=True,
            margin_method='FRACTION'  # Use FRACTION method to have more control
        )
        
        # Return to object mode
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # Create output filename with _unwrapped suffix
        base_name = os.path.splitext(filename)[0]
        output_path = os.path.join(output_directory, f"{base_name}.obj")
        
        # Export as OBJ
        try:
            # For Blender 4.4
            bpy.ops.wm.obj_export(
                filepath=output_path,
                export_selected_objects=True,
                export_materials=False,
                export_uv=True,
                export_triangulated_mesh=True,
                path_mode='RELATIVE'
            )
            print(f"Processed {filename} -> {os.path.basename(output_path)}")
        except Exception as e:
            print(f"Error exporting {filename}: {str(e)}")

# Main execution
print(f"Input directory: {input_dir}")
print(f"Output directory: {output_dir}")

try:
    process_models(input_dir, output_dir, unwrap_margin, island_margin)
    print("Batch UV unwrapping completed successfully!")
except Exception as e:
    print(f"Error during processing: {str(e)}") 