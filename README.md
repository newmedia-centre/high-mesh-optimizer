# High Mesh Optimizer & Batch Baker

This repository contains scripts to streamline the mesh preparation and baking process between Blender and Substance Painter.

## Overview

The workflow involves two main parts:

1.  **Blender Scripts (`blender-src/`):** Tools to prepare high and low poly meshes within Blender, designed to be run via the command line.
2.  **Substance Painter Plugin (`xrzone_batch_baker.py`):** A plugin for Substance Painter to automatically load mesh pairs, bake selected maps (Normal, AO, ID), and export the results.

## Blender Scripts (`blender-src/`)

These scripts are designed to be run via the Blender Command Line Interface (CLI) to prepare your models for baking. This is useful for automation and batch processing.

**Note:** These scripts require Blender version 4.4 or newer.

*   `batch_flip_merge_normal.py`:
    *   **Purpose:** Designed for high-poly meshes. It ensures normals are consistent (often recalculating outside) and merges vertices by distance to close small gaps, which helps improve baking results, especially for Normal and AO maps.
    *   **Usage (CLI):**
        1.  Open your terminal or command prompt.
        2.  Navigate to your Blender installation directory (or ensure `blender` is in your system's PATH).
        3.  Run the script using a command like:
            ```bash
            blender --background --python "path/to/blender-src/batch_flip_merge_normal.py" -- "path/to/high_poly_input_folder" "path/to/high_poly_output_folder"
            ```
            *   Replace `path/to/blender-src/...` with the actual **absolute path** to the script file.
            *   Replace `path/to/high_poly_input_folder` with the **absolute path** to the directory containing your high-poly source files.
            *   Replace `path/to/high_poly_output_folder` with the **absolute path** where the processed high-poly meshes should be saved.
            *   **Important:** Use absolute paths and enclose paths containing spaces in quotes.
            *   The `--background` flag prevents the Blender UI from opening.
            *   The `--` separates Blender's arguments from the script's arguments.

*   `batch_uv_unwrap.py`:
    *   **Purpose:** Designed for low-poly meshes. It automatically performs a Smart UV Project unwrap on each mesh. This is essential for generating UV coordinates needed for texture baking.
    *   **Usage (CLI):**
        1.  Open your terminal or command prompt.
        2.  Navigate to your Blender installation directory (or ensure `blender` is in your system's PATH).
        3.  Run the script using a command like:
            ```bash
            blender --background --python "path/to/blender-src/batch_uv_unwrap.py" -- "path/to/low_poly_input_folder" "path/to/low_poly_output_folder" [unwrap_margin] [island_margin]
            ```
            *   Replace `path/to/blender-src/...` with the actual **absolute path** to the script file.
            *   Replace `path/to/low_poly_input_folder` with the **absolute path** to the directory containing your low-poly source files.
            *   Replace `path/to/low_poly_output_folder` with the **absolute path** where the processed low-poly meshes should be saved.
            *   (Optional) Replace `[unwrap_margin]` with a float value for the unwrap margin (default: 0.001).
            *   (Optional) Replace `[island_margin]` with a float value for the island margin (default: 0.02).
            *   **Important:** Use absolute paths and enclose paths containing spaces in quotes.
            *   The `--` separates Blender's arguments from the script's arguments.

**Note:** Ensure your Blender environment has the necessary permissions if reading/writing files across different drives or protected locations, especially when running via CLI.

## Substance Painter Plugin (`xrzone_batch_baker.py`)

This script is a plugin for Adobe Substance 3D Painter.

*   **Purpose:** Automates the high-to-low poly baking process for multiple mesh pairs.
*   **Features:**
    *   Loads low-poly meshes into new Substance Painter projects sequentially.
    *   Optionally finds matching high-poly meshes based on naming conventions (e.g., `mesh_low.obj` and `mesh_high.ply`).
    *   Bakes selected maps: Normal, Ambient Occlusion (AO), and ID (from high poly vertex colors).
    *   Exports the baked maps to organized subfolders.
    *   Supports `.fbx`, `.obj`, and `.ply` mesh formats.
*   **Installation:**
    1.  Locate your Substance Painter plugins directory. This is usually in `Documents\Adobe\Adobe Substance 3D Painter\python\plugins`.
    2.  Create a new folder inside `plugins`, for example, `high-mesh-optimizer`.
    3.  Copy the `substance-src/xrzone_batch_baker.py` file from this repository into the new folder (`Documents\Adobe\Adobe Substance 3D Painter\python\plugins\high-mesh-optimizer\xrzone_batch_baker.py`).
    4.  Reload plugin via `Python` > `Reload Plugins Folder`.
    5.  Enable the plugin via `Python` > `Plugins` > `high-mesh-optimizer` (or whatever you named the folder).
*   **Usage:**
    1.  The "Batch Baker" panel will appear in Substance Painter (usually docked otherwise open it from `Window` > `Views`).
    2.  **Source Meshes:**
        *   Browse to select the folder containing your prepared **Low Poly** meshes (output from `batch_uv_unwrap.py`).
        *   Browse to select the folder containing your prepared **High Poly** meshes (output from `batch_flip_merge_normal.py`).
    3.  **Project Settings:**
        *   Choose the desired **Texture Resolution** for baking.
        *   Select the maps you want to **bake** (Normal, AO, ID).
            *   *Note:* ID map baking assumes vertex colors exist on the high poly mesh and exports the result as a file named like `..._BaseColor.png`.
    4.  **Export Settings:**
        *   Browse to select the main **Export Folder** where texture subfolders will be created.
    5.  **Additional Options:**
        *   Select the desired **Export Format** (png, tga, exr).
        *   Use **Test Mode** to process only the first found mesh pair for verification.
    6.  Click **Run Batch Process**.
    7.  The plugin will iterate through the matched low poly meshes, create projects, bake the selected maps using the corresponding high poly, and export the textures to subfolders within your chosen Export Folder.

## Workflow Summary

1.  Organize your raw high and low poly meshes into separate input folders.
2.  Prepare high poly meshes using `blender-src/batch_flip_merge_normal.py` via the command line, saving the output to a dedicated "prepared high" folder.
3.  Prepare low poly meshes using `blender-src/batch_uv_unwrap.py` and `blender-src/batch_flip_merge_normal.py` via the command line, saving the output to a dedicated "prepared low" folder.
4.  Open Substance Painter and ensure the Batch Baker plugin is enabled.
5.  Configure the plugin panel:
    *   Set Low Poly Folder to your "prepared low" folder.
    *   Set High Poly Folder to your "prepared high" folder.
    *   Choose resolution and maps to bake.
    *   Set the main Export Folder.
    *   Adjust options (format, test mode).
6.  Click "Run Batch Process" and monitor the progress bar and status label.
7.  Find your baked textures in the specified Export Folder, organized into subdirectories named after the low poly meshes.