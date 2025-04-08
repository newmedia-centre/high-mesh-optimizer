"""
Batch Baker Plugin for Substance Painter

A plugin that automates the process of:
1. Importing high and low poly meshes
2. Baking normal maps and other texture maps
3. Exporting the baked textures

Compatible with Substance Painter's Python API 0.3.4+
"""

import os
import re
import logging
from typing import Dict, List, Tuple

import substance_painter as sp
from PySide6 import QtWidgets, QtCore
import substance_painter.export as export
from substance_painter.export import ExportStatus
import substance_painter.baking as baking
import substance_painter.project as project
import substance_painter.textureset as textureset

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BatchBaker")

# Global paths
PLUGIN_PATH = os.path.dirname(os.path.realpath(__file__))
RESOURCES_PATH = os.path.join(PLUGIN_PATH, "resources")

# Global instance of the widget
batch_baker_widget = None

#--------------------------------------------------------
# UI CLASS
#--------------------------------------------------------

class BatchBakerWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Add state variables to store current mesh info
        self.current_low_poly = None
        self.current_high_poly = None
        
        # Create the main layout
        main_layout = QtWidgets.QVBoxLayout(self)
        self.setLayout(main_layout)
        
        # Default paths
        self.default_low_poly = "E:\\VRock2B\\ForSharif_03April2025\\GraphiteExports\\Low\\BlenderExport"
        self.default_high_poly = "E:\\VRock2B\\ForSharif_03April2025\\GraphiteExports\\High\\BlenderExport"
        self.default_template = "C:\\Users\\sbayo\\Documents\\Adobe\\Adobe Substance 3D Painter\\python\\plugins\\AutoUnwrapDisabled.spp"
        
        # Add title and description
        title_label = QtWidgets.QLabel("Mesh Loader & Baker")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        description_label = QtWidgets.QLabel(
            "Load low poly meshes and bake normal maps from high poly meshes"
        )
        
        # Source mesh selection
        source_group = QtWidgets.QGroupBox("Source Meshes")
        source_layout = QtWidgets.QVBoxLayout()
        source_group.setLayout(source_layout)
        
        # Low poly mesh folder
        low_poly_layout = QtWidgets.QHBoxLayout()
        self.low_poly_folder = QtWidgets.QLineEdit()
        self.low_poly_folder.setText(self.default_low_poly)
        low_poly_button = QtWidgets.QPushButton("Browse...")
        low_poly_button.clicked.connect(lambda: self._browse_folder(self.low_poly_folder))
        low_poly_layout.addWidget(QtWidgets.QLabel("Low Poly Folder:"))
        low_poly_layout.addWidget(self.low_poly_folder)
        low_poly_layout.addWidget(low_poly_button)
        
        # High poly mesh folder
        high_poly_layout = QtWidgets.QHBoxLayout()
        self.high_poly_folder = QtWidgets.QLineEdit()
        self.high_poly_folder.setText(self.default_high_poly)
        high_poly_button = QtWidgets.QPushButton("Browse...")
        high_poly_button.clicked.connect(lambda: self._browse_folder(self.high_poly_folder))
        high_poly_layout.addWidget(QtWidgets.QLabel("High Poly Folder:"))
        high_poly_layout.addWidget(self.high_poly_folder)
        high_poly_layout.addWidget(high_poly_button)
        
        # Template project path
        template_layout = QtWidgets.QHBoxLayout()
        self.template_path = QtWidgets.QLineEdit()
        self.template_path.setText(self.default_template)
        template_button = QtWidgets.QPushButton("Browse...")
        template_button.clicked.connect(lambda: self._browse_file(self.template_path, "Select Template Project", "Substance Painter Project (*.spp)"))
        template_layout.addWidget(QtWidgets.QLabel("Template Project:"))
        template_layout.addWidget(self.template_path)
        template_layout.addWidget(template_button)
        
        # Add to source layout
        source_layout.addLayout(low_poly_layout)
        source_layout.addLayout(high_poly_layout)
        source_layout.addLayout(template_layout)
        
        # Project settings
        settings_group = QtWidgets.QGroupBox("Project Settings")
        settings_layout = QtWidgets.QVBoxLayout()
        settings_group.setLayout(settings_layout)
        
        # Texture resolution
        resolution_layout = QtWidgets.QHBoxLayout()
        resolution_layout.addWidget(QtWidgets.QLabel("Texture Resolution:"))
        self.resolution_combo = QtWidgets.QComboBox()
        for res in ["256x256", "512x512", "1024x1024", "2048x2048", "4096x4096"]:
            self.resolution_combo.addItem(res)
        self.resolution_combo.setCurrentText("2048x2048")
        resolution_layout.addWidget(self.resolution_combo)
        
        # Baking options
        baking_layout = QtWidgets.QVBoxLayout()
        self.bake_normal_checkbox = QtWidgets.QCheckBox("Bake Normal Map")
        self.bake_normal_checkbox.setChecked(True)
        self.bake_ao_checkbox = QtWidgets.QCheckBox("Bake Ambient Occlusion")
        self.bake_ao_checkbox.setChecked(True) # Default to checked
        self.bake_id_checkbox = QtWidgets.QCheckBox("Bake ID Map (from Vertex Color)")
        self.bake_id_checkbox.setChecked(True) # Default to checked
        baking_layout.addWidget(self.bake_normal_checkbox)
        baking_layout.addWidget(self.bake_ao_checkbox)
        baking_layout.addWidget(self.bake_id_checkbox)
        
        # Add to settings layout
        settings_layout.addLayout(resolution_layout)
        settings_layout.addLayout(baking_layout)
        
        # Additional options
        options_layout = QtWidgets.QVBoxLayout()
        self.match_naming_checkbox = QtWidgets.QCheckBox("Match high/low poly meshes by name (e.g. 123_high.obj and 123_low.obj)")
        self.match_naming_checkbox.setChecked(True)
        self.test_mode_checkbox = QtWidgets.QCheckBox("Test Mode (process only the first mesh)")
        self.test_mode_checkbox.setChecked(True)
        options_layout.addWidget(self.match_naming_checkbox)
        options_layout.addWidget(self.test_mode_checkbox)
        
        # For compatibility, keep format combo but hide it
        self.format_combo = QtWidgets.QComboBox()
        for format in ["png", "tga", "exr"]:
            self.format_combo.addItem(format)
        self.format_combo.setVisible(False)
        
        # --- Action Buttons --- 
        buttons_layout = QtWidgets.QHBoxLayout()
        
        # Load Mesh button
        self.load_button = QtWidgets.QPushButton("Load First Mesh")
        self.load_button.setMinimumHeight(40)
        self.load_button.clicked.connect(self._handle_load_mesh) # Connect to new handler
        buttons_layout.addWidget(self.load_button)
        
        # Bake Normals button
        self.bake_button = QtWidgets.QPushButton("Bake Selected Maps")
        self.bake_button.setMinimumHeight(40)
        self.bake_button.clicked.connect(self._handle_bake_normals) # Connect to new handler
        self.bake_button.setEnabled(False) # Initially disabled
        buttons_layout.addWidget(self.bake_button)
        
        # Status display
        self.status_label = QtWidgets.QLabel("Ready")
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setVisible(False)
        
        # Add all components to main layout
        main_layout.addWidget(title_label)
        main_layout.addWidget(description_label)
        main_layout.addWidget(source_group)
        main_layout.addWidget(settings_group)
        main_layout.addLayout(options_layout)
        main_layout.addLayout(buttons_layout) # Add new buttons layout
        main_layout.addWidget(self.status_label)
        main_layout.addWidget(self.progress_bar)
        
    def _browse_folder(self, line_edit):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Directory")
        if folder:
            line_edit.setText(folder)
    
    def _browse_file(self, line_edit, dialog_title, filter):
        file_path = QtWidgets.QFileDialog.getOpenFileName(self, dialog_title, "", filter)[0]
        if file_path:
            line_edit.setText(file_path)

    def _handle_load_mesh(self):
        """Handles the 'Load First Mesh' button click."""
        # Reset state
        self.current_low_poly = None
        self.current_high_poly = None
        self.bake_button.setEnabled(False)
        self._update_progress(0, 1, "Validating inputs...")

        # Validate inputs
        if not self._validate_inputs():
            self.status_label.setText("Input validation failed.")
            return

        # Get settings
        settings = self._get_settings()
        low_poly_folder = settings.get('low_poly_folder')
        high_poly_folder = settings.get('high_poly_folder')
        resolution = settings.get('resolution', '2048x2048')
        match_naming = settings.get('match_naming', True)
        bake_normal_enabled_in_ui = settings.get('maps', {}).get('normal', False)
        resolution_int = int(resolution.split('x')[0]) # Convert resolution

        # Find mesh files
        self._update_progress(0, 1, "Finding mesh files...")
        try:
            low_poly_meshes = _find_mesh_files(low_poly_folder)
            if not low_poly_meshes:
                raise ValueError("No mesh files found in the low poly folder")

            high_poly_meshes = []
            if bake_normal_enabled_in_ui:
                high_poly_meshes = _find_mesh_files(high_poly_folder)
                if not high_poly_meshes:
                    # Warn but proceed without high poly, bake button will be disabled
                    logger.warning("No mesh files found in the high poly folder, normal baking will be disabled.")
                    bake_normal_enabled_in_ui = False # Disable baking for this run
            
            # Match meshes
            mesh_pairs = _match_meshes(high_poly_meshes, low_poly_meshes, match_naming)
            if not mesh_pairs:
                raise ValueError("Could not match any high poly to low poly meshes (or no low-poly meshes found)")
            
            # Select the first pair
            first_low_poly, first_high_poly = mesh_pairs[0]
            self.current_low_poly = first_low_poly
            self.current_high_poly = first_high_poly if bake_normal_enabled_in_ui else None
            
            logger.info(f"Selected mesh pair: Low='{os.path.basename(self.current_low_poly)}', High='{os.path.basename(self.current_high_poly) if self.current_high_poly else 'None'}'")
            self._update_progress(0, 1, f"Loading: {os.path.basename(self.current_low_poly)}")

            # Load the mesh (create project)
            # This now uses a simplified version of the old _process_mesh_pair
            _load_mesh_into_new_project(self.current_low_poly, resolution_int)
            
            # If successful, update UI
            self.status_label.setText(f"Loaded: {os.path.basename(self.current_low_poly)}")
            
            # Enable Bake button if *any* bake map is checked 
            # (We handle missing high poly later if needed by specific bakers)
            any_bake_selected = (self.bake_normal_checkbox.isChecked() or 
                                 self.bake_ao_checkbox.isChecked() or 
                                 self.bake_id_checkbox.isChecked())
            
            if any_bake_selected:
                 self.bake_button.setEnabled(True)
            else:
                 self.bake_button.setEnabled(False)

        except Exception as e:
            error_msg = f"Error loading mesh: {str(e)}"
            logger.error(error_msg)
            self.status_label.setText(error_msg)
            QtWidgets.QMessageBox.critical(self, "Error", error_msg)
            self.bake_button.setEnabled(False)
        finally:
            self._update_progress(0, 0, self.status_label.text()) # Clear progress bar


    def _handle_bake_normals(self):
        """Handles the 'Bake Selected Maps' button click (now asynchronous)."""
        # Get current settings to see which maps are checked
        settings = self._get_settings()
        enabled_maps = settings.get('maps', {})
        bake_normal = enabled_maps.get('normal', False)
        bake_ao = enabled_maps.get('ambient_occlusion', False)
        bake_id = enabled_maps.get('id', False)
        
        # Check if any map requires high poly but it's missing
        needs_high_poly = bake_normal or bake_ao
        if needs_high_poly and not self.current_high_poly:
            logger.warning("Bake button clicked, but Normal or AO map requested and no high poly mesh is loaded.")
            QtWidgets.QMessageBox.warning(self, "Baking Error", "Normal and/or AO map baking requires a high poly mesh, but none is loaded.")
            self.bake_button.setEnabled(False) # Disable button again
            return
        
        if not project.is_open():
             logger.error("Bake button clicked, but no project is open.")
             QtWidgets.QMessageBox.critical(self, "Baking Error", "No project is currently open. Please load a mesh first.")
             self.bake_button.setEnabled(False)
             return

        # Disable button immediately
        self.bake_button.setEnabled(False)
        self._update_progress(0, 1, f"Starting bake from {os.path.basename(self.current_high_poly) if self.current_high_poly else 'None'}...")
        
        try:
            texture_sets = textureset.all_texture_sets()
            if not texture_sets:
                raise RuntimeError("Cannot bake: No texture sets found.")
            
            material_name = texture_sets[0].name()
            logger.info(f"Baking selected maps async for texture set: {material_name}")

            # Call the updated baking function with enabled maps
            _bake_selected_maps(self.current_high_poly, material_name, enabled_maps)
            
            # Status label updated here to show baking started
            self.status_label.setText("Normal map baking in progress...")
            # Button remains disabled until callback runs

        except Exception as e:
            error_msg = f"Error initiating bake: {str(e)}"
            logger.error(error_msg)
            self.status_label.setText(error_msg)
            QtWidgets.QMessageBox.critical(self, "Baking Error", error_msg)
            # Re-enable button on immediate error
            self.bake_button.setEnabled(True)
            self._update_progress(0, 0, self.status_label.text()) # Clear progress
             
    def _update_progress(self, value, max_value, message=None):
        self.progress_bar.setMaximum(max_value)
        self.progress_bar.setValue(value)
        self.progress_bar.setVisible(value < max_value and value > 0) # Show progress only when active
        if message:
            self.status_label.setText(message)
    
    def _validate_inputs(self):
        # Check if folders exist
        if not os.path.isdir(self.low_poly_folder.text()):
            QtWidgets.QMessageBox.warning(self, "Warning", "Low poly folder does not exist")
            return False
            
        # Make sure there are mesh files in the folder
        low_poly_meshes = _find_mesh_files(self.low_poly_folder.text())
        if not low_poly_meshes:
            QtWidgets.QMessageBox.warning(self, "Warning", "No mesh files found in low poly folder")
            return False
        
        # Check high poly folder if normal baking is enabled
        if self.bake_normal_checkbox.isChecked():
            if not os.path.isdir(self.high_poly_folder.text()):
                QtWidgets.QMessageBox.warning(self, "Warning", "High poly folder does not exist")
                return False
                
            # Make sure there are mesh files in the folder
            high_poly_meshes = _find_mesh_files(self.high_poly_folder.text())
            if not high_poly_meshes:
                QtWidgets.QMessageBox.warning(self, "Warning", "No mesh files found in high poly folder")
                return False
        
        # Check template path
        if self.template_path.text() and not os.path.isfile(self.template_path.text()):
            QtWidgets.QMessageBox.warning(self, "Warning", "Template project file does not exist")
            return False
        
        # If template path is provided, verify it has .spp extension
        if self.template_path.text() and not self.template_path.text().lower().endswith('.spp'):
            QtWidgets.QMessageBox.warning(self, "Warning", "Template project must be a .spp file")
            return False
            
        return True

    def _get_settings(self):
        # Collect settings from the UI
        settings = {
            'low_poly_folder': self.low_poly_folder.text(),
            'high_poly_folder': self.high_poly_folder.text(),
            'export_folder': '',  # Not used but kept for compatibility
            'resolution': self.resolution_combo.currentText(),
            'format': self.format_combo.currentText(),  # Kept for compatibility
            'maps': {
                'normal': self.bake_normal_checkbox.isChecked(),
                'ambient_occlusion': self.bake_ao_checkbox.isChecked(),
                'id': self.bake_id_checkbox.isChecked()
            },
            'match_naming': self.match_naming_checkbox.isChecked(),
            'test_mode': self.test_mode_checkbox.isChecked(),

        }
        return settings

#--------------------------------------------------------
# BAKER FUNCTIONALITY (Modified)
#--------------------------------------------------------

def _load_mesh_into_new_project(low_poly: str, resolution: int):
    """Creates a new project with the given low poly mesh.
    
    Args:
        low_poly: Path to low poly mesh
        resolution: Texture resolution for the project
    """
    logger.info(f"Attempting to load mesh: {os.path.basename(low_poly)}")
    
    # Close any previously open project
    if project.is_open():
        logger.info("Closing existing project...")
        project.close()

    # --- Create a new project --- 
    logger.info(f"Creating new project with mesh: {low_poly}")
    try:
        project_settings = project.Settings(
            normal_map_format = project.NormalMapFormat.DirectX,
            default_texture_resolution = resolution
        )
        
        # Create the project
        project.create(mesh_file_path=low_poly, settings=project_settings)
        logger.info(f"Project creation command sent for: {os.path.basename(low_poly)}")

    except Exception as e:
        # Error message now relates only to creation itself
        logger.error(f"Error during project creation: {str(e)}")
        # Attempt to close project if open before re-raising
        if project.is_open():
            project.close()
        # Re-raise to be caught by the button handler
        raise RuntimeError(f"Failed to create project with mesh {low_poly}: {str(e)}")

def _bake_selected_maps(high_poly: str | None, material_name: str, enabled_maps: Dict[str, bool]):
    """Initiates asynchronous baking of the selected maps for a specific material.

    Args:
        high_poly: Path to the high poly mesh file (can be None if only ID map is baked).
        material_name: Name of the texture set/material to bake for.
        enabled_maps: Dict indicating which maps to bake (e.g., {'normal': True, 'ambient_occlusion': False, 'id': True})
    """
    bake_normal = enabled_maps.get('normal', False)
    bake_ao = enabled_maps.get('ambient_occlusion', False)
    bake_id = enabled_maps.get('id', False)
    
    log_high_poly = os.path.basename(high_poly) if high_poly else "None"
    enabled_map_names = [k for k, v in enabled_maps.items() if v]
    logger.info(f"Configuring bake for material '{material_name}' with high poly '{log_high_poly}'. Enabled maps: {enabled_map_names}")

    try:
        # Get BakingParameters instance using the texture set name
        baking_params = baking.BakingParameters.from_texture_set_name(material_name)
        if not baking_params:
            raise ValueError(f"Could not get BakingParameters for TextureSet '{material_name}'.")

        # Get the common parameters dictionary
        common_params = baking_params.common()
        if not common_params:
             raise RuntimeError("Could not retrieve common baking parameters.")

        # --- Prepare parameters dictionary for setting ---
        # Try getting resolution from TextureSet, fallback to project setting, then default
        bake_resolution = None
        resolution_source = "Unknown"
        try:
            ts_res_obj = baking_params.texture_set().get_resolution()
            # Check if it's the expected Resolution object or similar with attributes
            if hasattr(ts_res_obj, 'width') and hasattr(ts_res_obj, 'height'):
                 bake_resolution = (ts_res_obj.width, ts_res_obj.height)
                 resolution_source = "TextureSet"
            # Check if it's already a tuple (less likely based on error)
            elif isinstance(ts_res_obj, tuple) and len(ts_res_obj) == 2 and all(isinstance(x, int) for x in ts_res_obj):
                 bake_resolution = ts_res_obj
                 resolution_source = "TextureSet (tuple)"
            else:
                 logger.warning(f"TextureSet resolution format not recognized: {ts_res_obj}. Trying project default.")
        except Exception as e:
            logger.warning(f"Could not get TextureSet resolution: {e}. Trying project default.")

        if not bake_resolution:
             try:
                 # Assuming project settings also returns Resolution object or tuple
                 proj_res_obj = project.Settings().default_texture_resolution
                 if hasattr(proj_res_obj, 'width') and hasattr(proj_res_obj, 'height'):
                     bake_resolution = (proj_res_obj.width, proj_res_obj.height)
                     resolution_source = "ProjectDefault"
                 elif isinstance(proj_res_obj, tuple) and len(proj_res_obj) == 2 and all(isinstance(x, int) for x in proj_res_obj):
                     bake_resolution = proj_res_obj
                     resolution_source = "ProjectDefault (tuple)"
                 else:
                      logger.warning(f"Project default resolution format not recognized: {proj_res_obj}. Falling back to default.")
             except Exception as e:
                  logger.warning(f"Could not get project default resolution: {e}. Falling back to default.")

        if not bake_resolution:
            default_res = 2048
            bake_resolution = (default_res, default_res)
            logger.warning(f"Falling back to default resolution: {default_res}x{default_res}")
            resolution_source = "FallbackDefault"

        # Final check if bake_resolution is now a valid tuple of integers
        if not (isinstance(bake_resolution, tuple) and len(bake_resolution) == 2 and all(isinstance(x, int) for x in bake_resolution)):
             raise TypeError(f"Could not obtain a valid (int, int) bake_resolution. Last attempt (source: {resolution_source}): {bake_resolution}")

        logger.info(f"Final bake resolution to use: {bake_resolution[0]}x{bake_resolution[1]}")

        # --- Set TextureSet Resolution Directly ---
        try:
            ts = baking_params.texture_set()
            if ts:
                resolution_obj = textureset.Resolution(bake_resolution[0], bake_resolution[1])
                ts.set_resolution(resolution_obj)
            else:
                logger.warning("Could not get TextureSet object from BakingParameters to set resolution directly.")
        except Exception as e:
            logger.error(f"Error setting TextureSet resolution directly: {e}")
            # Decide if this is critical - maybe proceed anyway?
            # raise # Or just log and continue

        # Format high poly path using QUrl as per example
        highpoly_mesh_path_url = QtCore.QUrl.fromLocalFile(high_poly).toString() if high_poly else "None"
        logger.info(f"Formatted high poly path: {highpoly_mesh_path_url}")
        
        # --- Unlink common parameters before setting ---
        try:
            baking.unlink_all_common_parameters()
        except Exception as e:
            logger.warning(f"Failed to call unlink_all_common_parameters: {e}")

        # Define the dictionary for BakingParameters.set()
        # Use keys *found* in common_params, referencing the logged output
        parameters_to_set = {}
        
        # Parameter mapping: Desired Setting -> Actual Key in common_params (UPDATED BASED ON LOG OUTPUT)
        param_key_map = {
            'output_size': 'OutputSize', 
            'hipoly_mesh': 'HipolyMesh', 
            'use_low_poly': 'LowAsHigh', 
            'avg_normals': 'SmoothNormals', 
            'ignore_backface': 'IgnoreBackface', 
            'match_option': 'FilterMethod', 
            'cage_mode': 'CageMode'
        }

        # High Poly Mesh - Only set if needed
        key = param_key_map.get('hipoly_mesh')
        if (bake_normal or bake_ao) and high_poly:
             if key and key in common_params:
                 parameters_to_set[common_params[key]] = highpoly_mesh_path_url
             elif key:
                  logger.error(f"Could not find key '{key}' for High Poly Mesh in common_params. Cannot set mesh.")
                  raise KeyError(f"Missing required parameter key: {key}")
             else:
                  logger.error("Internal error: 'hipoly_mesh' not found in param_key_map.")
                  raise KeyError("Missing required internal parameter mapping for 'hipoly_mesh'")
        elif bake_normal or bake_ao:
             # This case should ideally be caught by _handle_bake_normals, but log just in case
             logger.error("Normal or AO bake requested, but high_poly path is missing in _bake_selected_maps.")
             raise ValueError("High poly mesh required for Normal/AO bake but not provided.")
        else:
            logger.info("HipolyMesh parameter not set as Normal and AO are disabled.")
             
        # Use Low Poly as High Poly - Keep setting this, might be relevant for some bakers?
        key = param_key_map.get('use_low_poly')
        if key and key in common_params:
            parameters_to_set[common_params[key]] = False
        elif key:
            logger.warning(f"Could not find key '{key}' for Use Low Poly in common_params.")

        # Average Normals - Only relevant for Normal map?
        key = param_key_map.get('avg_normals')
        if bake_normal:
             if key and key in common_params:
                 parameters_to_set[common_params[key]] = True
             elif key: 
                 logger.warning(f"Could not find key '{key}' for Average Normals in common_params.")
        else:
            logger.info("SmoothNormals parameter not set as Normal bake is disabled.")

        # Ignore Backface - Only relevant for Normal/AO?
        key = param_key_map.get('ignore_backface')
        if bake_normal or bake_ao:
             if key and key in common_params:
                  parameters_to_set[common_params[key]] = True
             elif key:
                  logger.warning(f"Could not find key '{key}' for Ignore Backface in common_params.")
        else:
            logger.info("IgnoreBackface parameter not set as Normal/AO bake is disabled.")

        # Match Option - Only relevant for Normal/AO?
        key = param_key_map.get('match_option')
        if bake_normal or bake_ao:
             if key and key in common_params:
                 match_prop = common_params[key]
                 try:
                      parameters_to_set[match_prop] = match_prop.enum_value('Always') 
                 except AttributeError:
                     logger.warning(f"Could not call enum_value on match property {match_prop}. Trying string 'Always'.")
                     parameters_to_set[match_prop] = 'Always'
                 except Exception as e:
                      logger.warning(f"Error setting match option using key '{key}': {e}")
             elif key:
                 logger.warning(f"Could not find key '{key}' for Match Option in common_params.")
        else:
            logger.info("Match Option parameter not set as Normal/AO bake is disabled.")

        # Cage Mode (Set to Automatic) - Only relevant for Normal/AO?
        key = param_key_map.get('cage_mode')
        if bake_normal or bake_ao:
            if key and key in common_params:
                 cage_prop = common_params[key]
                 try:
                      parameters_to_set[cage_prop] = cage_prop.enum_value('Automatic (experimental)') 
                 except AttributeError:
                     logger.warning(f"Could not call enum_value on cage property {cage_prop}. Trying string 'Automatic (experimental)'.")
                     parameters_to_set[cage_prop] = 'Automatic (experimental)'
                 except Exception as e:
                      logger.warning(f"Error setting Cage Mode using key '{key}': {e}")
            elif key:
                 logger.warning(f"Could not find key '{key}' for Cage Mode in common_params.")
        else:
            logger.info("Cage Mode parameter not set as Normal/AO bake is disabled.")

        # --- Configure AO Specific Parameters ---
        if bake_ao:
            # Use the baker() method with the correct MeshMapUsage enum
            ao_baker = baking_params.baker(baking.MeshMapUsage.AO) 
            if ao_baker:
                ao_params = ao_baker # Access parameters directly from the baker object
                ao_param_key_map = {} # Store mapping 
                # Iterate through the keys provided by the baker object
                ao_param_keys = ao_params.keys()
                for key in ao_param_keys:
                    # Using the actual key string now
                    if 'ray' in key.lower() or 'sample' in key.lower():
                        ao_param_key_map.setdefault('secondary_rays', key)
                    if 'occluder' in key.lower() and 'max' in key.lower():
                        ao_param_key_map.setdefault('max_occluder_distance', key)
                    if 'occluder' in key.lower() and 'min' in key.lower():
                         ao_param_key_map.setdefault('min_occluder_distance', key)
                    if 'spread' in key.lower():
                        ao_param_key_map.setdefault('spread_angle', key)
                    if 'distribution' in key.lower():
                        ao_param_key_map.setdefault('distribution', key)

            else:
                logger.warning("Could not retrieve AO-specific baker parameters using baker(MeshMapUsage.AO).")
        else:
             logger.info("AO baking is disabled, skipping AO-specific parameters.")

        # --- Configure ID Specific Parameters ---
        if bake_id:
            # Use the baker() method with the correct MeshMapUsage enum
            id_baker = baking_params.baker(baking.MeshMapUsage.ID) 
            if id_baker:
                id_params = id_baker
                id_param_keys = id_params.keys()
                
                color_source_key = None # Variable to store the found key
                for key in id_param_keys:
                    # Find the key for color source (likely contains 'color' and 'source')
                    if 'color' in key.lower() and 'source' in key.lower():
                        color_source_key = key
                        break # Assume the first match is the correct one

                if color_source_key:
                    color_source_prop = id_params[color_source_key]
                    try:
                        # --- Set the value using the integer representation ---
                        vertex_color_int_value = 0 # Assuming 1 represents Vertex Color
                        parameters_to_set[color_source_prop] = vertex_color_int_value
                        logger.info(f"  Set ID Param '{color_source_key}' to {vertex_color_int_value} (assumed value for Vertex Color).")

                    except Exception as e:
                         logger.error(f"  Failed to set ID Param '{color_source_key}' using integer value {vertex_color_int_value}: {e}")
                else:
                     logger.warning("  Could not find the 'Color Source' parameter key for the ID baker.")

            else:
                logger.warning("Could not retrieve ID-specific baker parameters using baker(MeshMapUsage.ID).")

        # --- Get Available MeshMapUsage Enums ---
        available_enums = {}
        if hasattr(baking, 'MeshMapUsage'):
            for name in dir(baking.MeshMapUsage):
                if not name.startswith('_'): # Skip private/dunder attributes
                    try:
                        enum_member = getattr(baking.MeshMapUsage, name)
                        # Basic check if it's likely an enum value (might need refinement)
                        if isinstance(enum_member, baking.MeshMapUsage):
                             available_enums[name] = enum_member
                    except AttributeError:
                        continue # Skip if getattr fails

        requested_to_enum_name = {}
        if bake_normal:
            requested_to_enum_name['normal'] = 'Normal'
        if bake_ao:
            requested_to_enum_name['ambient_occlusion'] = 'AO'
        if bake_id:
            requested_to_enum_name['id'] = 'ID'
        
        # --- Build the list of actual enums to enable --- 
        bakers_to_enable_enums = []
        enabled_baker_names_log = []
        missing_baker_names_log = []

        for map_key, enum_name in requested_to_enum_name.items():
            if enum_name in available_enums:
                bakers_to_enable_enums.append(available_enums[enum_name])
                enabled_baker_names_log.append(enum_name)
            else:
                 logger.warning(f"Cannot enable baker for '{map_key}': Enum 'baking.MeshMapUsage.{enum_name}' not found in available enums {list(available_enums.keys())}.")
                 missing_baker_names_log.append(enum_name)

        if not bakers_to_enable_enums:
             logger.error("No requested bakers could be enabled because required MeshMapUsage enums were not found.")
             raise RuntimeError("Failed to find any valid bakers to enable.")
        
        # --- Set Enabled Bakers using the Enum List --- 
        try:
            logger.info(f"Attempting to enable bakers using enums: {enabled_baker_names_log}")
            if missing_baker_names_log:
                logger.warning(f"Skipped unavailable bakers: {missing_baker_names_log}")
            baking_params.set_enabled_bakers(bakers_to_enable_enums)
            logger.info(f"Successfully enabled bakers: {enabled_baker_names_log}")
        except Exception as e:
             # Catch any error during setting bakers with the enum list
             logger.error(f"Failed to enable selected bakers using enums {enabled_baker_names_log}: {e}")
             raise RuntimeError(f"Could not enable selected bakers: {e}")

        # --- Set the parameters using the class method ---
        baking.BakingParameters.set(parameters_to_set)
        
        logger.info("Baker parameters configured. Starting asynchronous bake...")
        
        # --- Call the asynchronous baking function --- 
        # Call with no arguments as per TypeError
        baking.bake_selected_textures_async()         

    except Exception as e:
        error_msg = f"Failed to configure or start bake for '{material_name}': {str(e)}"
        logger.exception(error_msg) # Log with traceback
        raise RuntimeError(error_msg)

#--------------------------------------------------------
# PLUGIN ENTRY POINTS
#--------------------------------------------------------

def start_plugin():
    """Initialize the plugin"""
    global batch_baker_widget
    
    # Create widget
    batch_baker_widget = BatchBakerWidget()
    
    # Set window title for the dock
    batch_baker_widget.setWindowTitle("Batch Baker")
    
    # Create a docker widget
    docker = sp.ui.add_dock_widget(batch_baker_widget)
    
    logger.info("Batch Baker plugin started")
    
def close_plugin():
    """Clean up when the plugin is closed"""
    global batch_baker_widget
    
    if batch_baker_widget:
        sp.ui.delete_ui_element(batch_baker_widget)
        batch_baker_widget = None
    
    # Clean up temporary files
    temp_dir = os.path.join(PLUGIN_PATH, "temp")
    if os.path.exists(temp_dir):
        try:
            import shutil
            shutil.rmtree(temp_dir)
            logger.info(f"Cleaned up temporary files in {temp_dir}")
        except Exception as e:
            logger.warning(f"Failed to clean up temporary files: {str(e)}")
        
    logger.info("Batch Baker plugin closed") 

#--------------------------------------------------------
# Helper Functions (Ensure these are defined above their first use)
#--------------------------------------------------------
def _find_mesh_files(folder_path: str) -> List[str]:
    """Finds mesh files (.fbx, .obj) in the specified folder."""
    mesh_files = []
    supported_extensions = ('.fbx', '.obj') # Add more if needed
    try:
        for filename in os.listdir(folder_path):
            if filename.lower().endswith(supported_extensions):
                mesh_files.append(os.path.join(folder_path, filename))
    except FileNotFoundError:
        logger.warning(f"Mesh folder not found: {folder_path}")
    except Exception as e:
         logger.error(f"Error reading mesh folder {folder_path}: {e}")
    logger.info(f"Found {len(mesh_files)} mesh files in {folder_path}")
    return sorted(mesh_files) # Sort for consistent ordering

def _extract_base_name(filename: str) -> str:
    """Extracts the base name from a mesh filename (e.g., 'mesh_low.fbx' -> 'mesh')."""
    base = os.path.basename(filename)
    # Remove common suffixes like _low, _high, _lp, _hp before the extension
    base = re.sub(r'(_low|_lp|_high|_hp)?(\.fbx|\.obj)$', '', base, flags=re.IGNORECASE)
    return base

def _match_meshes(high_poly_meshes: List[str], low_poly_meshes: List[str], match_by_naming: bool) -> List[Tuple[str, str | None]]:
    """
    Matches high poly meshes to low poly meshes.
    
    If match_by_naming is True, it tries to find pairs like 'name_high.fbx' and 'name_low.fbx'.
    If False, or if naming match fails, it assumes a single high poly should be used for all low polys (if only one high poly exists).
    
    Returns:
        A list of tuples: [(low_poly_path, high_poly_path_or_None), ...]
    """
    mesh_pairs = []
    
    if not low_poly_meshes:
        logger.warning("No low poly meshes provided for matching.")
        return []

    if not high_poly_meshes:
        logger.warning("No high poly meshes provided. Baking from high poly will not be possible.")
        # Return low polys paired with None
        return [(lp, None) for lp in low_poly_meshes]

    if match_by_naming:
        logger.info("Attempting to match high/low meshes by base name...")
        low_poly_map = { _extract_base_name(lp): lp for lp in low_poly_meshes }
        high_poly_map = { _extract_base_name(hp): hp for hp in high_poly_meshes }
        
        matched_low_polys = set()

        for base_name, lp_path in low_poly_map.items():
            hp_path = high_poly_map.get(base_name)
            if hp_path:
                mesh_pairs.append((lp_path, hp_path))
                matched_low_polys.add(lp_path)
            else:
                 mesh_pairs.append((lp_path, None)) # Low poly without a matching high poly
                 logger.warning(f"  No matching high poly found for base name '{base_name}' (Low: '{os.path.basename(lp_path)}')")
            
    else:
        logger.info("Match by naming disabled.")
        # If only one high poly, assume it's for all low polys
        if len(high_poly_meshes) == 1:
            hp_path = high_poly_meshes[0]
            logger.info(f"Using single high poly '{os.path.basename(hp_path)}' for all low poly meshes.")
            mesh_pairs = [(lp, hp_path) for lp in low_poly_meshes]
        elif len(high_poly_meshes) > 1:
             # Ambiguous case: Multiple high polys but no naming convention. Pair with None.
             logger.warning("Multiple high poly meshes found, but matching by name is disabled. Cannot determine pairings.")
             mesh_pairs = [(lp, None) for lp in low_poly_meshes]
        # If zero high_poly_meshes, the initial check handles this.

    if not mesh_pairs:
         logger.warning("Could not form any mesh pairs based on the current settings.")
         
    return mesh_pairs 