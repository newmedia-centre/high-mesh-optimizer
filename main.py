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
import substance_painter.event

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
        
        # Add state for batch processing
        self.mesh_pairs_to_process: List[Tuple[str, str | None]] = []
        self.current_pair_index: int = -1
        self.is_batch_running: bool = False
        self.loading_low_poly: str | None = None  # Store mesh being loaded
        self.loading_high_poly: str | None = None # Store mesh being loaded
        
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
            "Load low poly meshes and bake selected maps from high poly meshes"
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
        
        # Format combo (keep hidden)
        self.format_combo = QtWidgets.QComboBox()
        for format in ["png", "tga", "exr"]:
            self.format_combo.addItem(format)
        self.format_combo.setVisible(False)
        
        # --- Action Buttons --- 
        buttons_layout = QtWidgets.QHBoxLayout()
        
        # NEW Run Batch button
        self.run_batch_button = QtWidgets.QPushButton("Run Batch Process")
        self.run_batch_button.setMinimumHeight(40)
        self.run_batch_button.setStyleSheet("font-weight: bold;") # Make it stand out
        self.run_batch_button.clicked.connect(self._run_batch_process) 
        buttons_layout.addWidget(self.run_batch_button)
        
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
        main_layout.addLayout(buttons_layout) # Use the layout with the new button
        main_layout.addWidget(self.status_label)
        main_layout.addWidget(self.progress_bar)
        
        # Connect listeners
        sp.event.DISPATCHER.connect(sp.event.BakingProcessEnded, self._on_bake_finished)

    def _browse_folder(self, line_edit):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Directory")
        if folder:
            line_edit.setText(folder)
    
    def _browse_file(self, line_edit, dialog_title, filter):
        file_path = QtWidgets.QFileDialog.getOpenFileName(self, dialog_title, "", filter)[0]
        if file_path:
            line_edit.setText(file_path)

    def _run_batch_process(self):
        """Starts the batch processing workflow."""
        if self.is_batch_running:
            logger.warning("Batch process already running.")
            return
            
        self._update_progress(0, 1, "Starting batch process...")
        self.run_batch_button.setEnabled(False)
        self.is_batch_running = True
        
        # 1. Validate Inputs
        if not self._validate_inputs():
            self.status_label.setText("Input validation failed. Batch cancelled.")
            self.run_batch_button.setEnabled(True)
            self.is_batch_running = False
            self._update_progress(0, 0, self.status_label.text())
            return
            
        # 2. Get Settings
        settings = self._get_settings()
        low_poly_folder = settings['low_poly_folder']
        high_poly_folder = settings['high_poly_folder']
        self.resolution_int = int(settings['resolution'].split('x')[0]) # Store for use in loop
        self.enabled_maps = settings['maps']
        match_naming = settings['match_naming']
        test_mode = settings['test_mode']
        
        # Check if any maps are selected for baking
        self.any_bake_selected = any(self.enabled_maps.values())
        if not self.any_bake_selected:
             logger.info("No bake maps selected. Batch process will only load meshes.")

        # 3. Find and Match Meshes
        try:
            self._update_progress(0, 1, "Finding mesh files...")
            low_poly_meshes = _find_mesh_files(low_poly_folder)
            if not low_poly_meshes:
                raise ValueError("No mesh files found in the low poly folder.")

            high_poly_meshes = []
            needs_high_poly_globally = self.enabled_maps.get('normal', False) or self.enabled_maps.get('ambient_occlusion', False)
            
            if self.any_bake_selected and needs_high_poly_globally:
                high_poly_meshes = _find_mesh_files(high_poly_folder)
                if not high_poly_meshes:
                    logger.warning("No mesh files found in the high poly folder. Normal/AO baking might fail for some meshes.")

            all_mesh_pairs = _match_meshes(high_poly_meshes, low_poly_meshes, match_naming)
            if not all_mesh_pairs:
                raise ValueError("Could not match any high poly to low poly meshes (or no low-poly meshes found).")

            # 4. Prepare List for Processing (Apply Test Mode)
            if test_mode:
                self.mesh_pairs_to_process = all_mesh_pairs[:1]
                logger.info("Test Mode enabled: Processing only the first mesh pair.")
            else:
                self.mesh_pairs_to_process = all_mesh_pairs
                logger.info(f"Processing {len(self.mesh_pairs_to_process)} mesh pairs.")

            if not self.mesh_pairs_to_process:
                 raise ValueError("No mesh pairs selected for processing (after applying test mode).")

            # 5. Start Processing
            self.current_pair_index = -1
            self.progress_bar.setMaximum(len(self.mesh_pairs_to_process))
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(True)
            
            self._process_next_mesh_pair() # Kick off the first iteration

        except Exception as e:
            error_msg = f"Error preparing batch: {str(e)}"
            logger.error(error_msg)
            self.status_label.setText(error_msg)
            QtWidgets.QMessageBox.critical(self, "Batch Error", error_msg)
            self.run_batch_button.setEnabled(True)
            self.is_batch_running = False
            self._update_progress(0, 0, self.status_label.text())

    def _process_next_mesh_pair(self):
        """Loads and initiates baking for the next mesh pair in the list."""
        if not self.is_batch_running:
            logger.info("Process next mesh pair called, but batch is not running. Stopping.")
            return
            
        self.current_pair_index += 1
        
        if self.current_pair_index >= len(self.mesh_pairs_to_process):
            self._finish_batch_process("Batch process completed successfully.")
            return
            
        current_low_poly, current_high_poly = self.mesh_pairs_to_process[self.current_pair_index]
        mesh_name = os.path.basename(current_low_poly)
        progress_msg = f"Processing {self.current_pair_index + 1}/{len(self.mesh_pairs_to_process)}: {mesh_name}"
        logger.info(progress_msg)
        self._update_progress(self.current_pair_index, len(self.mesh_pairs_to_process), progress_msg)

        # Store the pair we are about to load (still needed for polling logic)
        self.loading_low_poly = current_low_poly
        self.loading_high_poly = current_high_poly

        # --- Load Mesh --- 
        try:
            logger.info(f"Initiating project creation for: {mesh_name}")
            _load_mesh_into_new_project(current_low_poly, self.resolution_int)
            
            # Start polling for idle status after initiating load
            self._start_polling_for_idle(mesh_name)

        except Exception as e:
            error_msg = f"Failed to initiate loading for {mesh_name}: {str(e)}. Skipping."
            logger.error(error_msg)
            QtWidgets.QMessageBox.warning(self, "Loading Error", error_msg)
            QtCore.QTimer.singleShot(0, self._process_next_mesh_pair) 
            
    def _on_bake_finished(self, event_object):
        """Callback triggered when an asynchronous bake finishes.
        
        Args:
            event_object: The event object passed by the dispatcher.
        """
        logger.info(f"--- Entered _on_bake_finished --- Event Object Type: {type(event_object)}")
        logger.debug(f"Event Object Dir: {dir(event_object)}")
        
        # Check if the event object is an instance of BakingProcessEnded
        if isinstance(event_object, sp.event.BakingProcessEnded):
            logger.info("Event type matched BakingProcessEnded (using isinstance).")
            if not self.is_batch_running or self.current_pair_index < 0 or self.current_pair_index >= len(self.mesh_pairs_to_process):
                 logger.warning("_on_bake_finished: Batch not running or index out of bounds. Returning.")
                 return 
                 
            mesh_name = os.path.basename(self.mesh_pairs_to_process[self.current_pair_index][0])
            logger.info(f"BakingProcessEnded event received for {mesh_name}.")
            
            # Try accessing event data - it might be the object itself or a .data attribute
            bake_data = None
            if isinstance(event_object, dict): # Should not happen now based on type check, but keep for safety
                logger.debug("Treating event_object directly as bake_data dictionary.")
                bake_data = event_object
            elif hasattr(event_object, 'data') and isinstance(event_object.data, dict):
                logger.debug("Accessing event_object.data as bake_data dictionary.")
                bake_data = event_object.data
            else:
                # If it's not a dict and doesn't have a .data dict, maybe the object *itself* has the keys?
                # Try getting status directly from the object attributes
                if hasattr(event_object, 'status'):
                    logger.debug("Attempting to read 'status' attribute directly from event_object.")
                    # Construct a dict-like structure if needed downstream
                    bake_data = {'status': getattr(event_object, 'status', 'success')} 
                else:
                     logger.warning(f"Could not determine bake_data from event_object. Type: {type(event_object)}, Dir: {dir(event_object)}")

            # Check status if we found data
            bake_failed = False 
            if bake_data:
                 status = bake_data.get('status') # Get the status object/enum
                 # Compare against the actual enum for success
                 if status != baking.BakingStatus.Success:
                      bake_failed = True
                      # Log as error only if it's truly not Success
                      logger.error(f"Bake reported failure. Status: {status}, Data: {bake_data}")
                      QtWidgets.QMessageBox.warning(self, "Bake Error", f"Baking failed for {mesh_name}. Status: {status}. Check logs. Continuing...")
                 else:
                     logger.info(f"Bake completed successfully for {mesh_name} (Status: {status}).")
            else:
                logger.warning(f"Could not extract bake status dictionary for {mesh_name}.")

            if bake_failed:
                 pass # Decide behavior on failure (currently logs and continues)

            logger.info(f"Proceeding to next mesh after bake attempt for {mesh_name}.")
            QtCore.QTimer.singleShot(0, self._process_next_mesh_pair)
        # Removed the else block as isinstance handles non-matching types

    def _finish_batch_process(self, final_message):
        """Cleans up and resets UI after the batch process finishes or is stopped."""
        logger.info(f"Finishing batch process: {final_message}")
        self.status_label.setText(final_message)
        self.run_batch_button.setEnabled(True)
        self.is_batch_running = False
        self.mesh_pairs_to_process = []
        self.current_pair_index = -1
        self.loading_low_poly = None
        self.loading_high_poly = None
        
        self._update_progress(len(self.mesh_pairs_to_process) if len(self.mesh_pairs_to_process)>0 else 1, 
                              len(self.mesh_pairs_to_process) if len(self.mesh_pairs_to_process)>0 else 1, 
                              final_message) 
        self.progress_bar.setVisible(False)

    def _update_progress(self, value, max_value, message=None):
        safe_max = max(1, max_value) 
        self.progress_bar.setMaximum(safe_max)
        self.progress_bar.setValue(min(value, safe_max)) 
        self.progress_bar.setVisible(max_value > 0 and self.is_batch_running) 
        if message:
            self.status_label.setText(message)
    
    def _validate_inputs(self):
        # Check if folders exist
        if not os.path.isdir(self.low_poly_folder.text()):
            QtWidgets.QMessageBox.warning(self, "Warning", "Low poly folder does not exist")
            return False
            
        low_poly_meshes = _find_mesh_files(self.low_poly_folder.text())
        if not low_poly_meshes:
            QtWidgets.QMessageBox.warning(self, "Warning", "No mesh files found in low poly folder")
            return False
        
        # Check high poly folder if maps requiring it are checked
        needs_high_poly = self.bake_normal_checkbox.isChecked() or self.bake_ao_checkbox.isChecked()
        if needs_high_poly:
            if not os.path.isdir(self.high_poly_folder.text()):
                QtWidgets.QMessageBox.warning(self, "Warning", "High poly folder does not exist (required for Normal/AO bake)")
                return False
                
            high_poly_meshes = _find_mesh_files(self.high_poly_folder.text())
            if not high_poly_meshes:
                QtWidgets.QMessageBox.warning(self, "Warning", "No mesh files found in high poly folder (required for Normal/AO bake)")
                return False
        
        # Check template path
        if self.template_path.text() and not os.path.isfile(self.template_path.text()):
            QtWidgets.QMessageBox.warning(self, "Warning", "Template project file does not exist")
            return False
        
        if self.template_path.text() and not self.template_path.text().lower().endswith('.spp'):
            QtWidgets.QMessageBox.warning(self, "Warning", "Template project must be a .spp file")
            return False
            
        return True

    def _get_settings(self):
        # Collect settings from the UI
        settings = {
            'low_poly_folder': self.low_poly_folder.text(),
            'high_poly_folder': self.high_poly_folder.text(),
            'export_folder': '', 
            'resolution': self.resolution_combo.currentText(),
            'format': self.format_combo.currentText(), 
            'maps': {
                'normal': self.bake_normal_checkbox.isChecked(),
                'ambient_occlusion': self.bake_ao_checkbox.isChecked(),
                'id': self.bake_id_checkbox.isChecked()
            },
            'match_naming': self.match_naming_checkbox.isChecked(),
            'test_mode': self.test_mode_checkbox.isChecked(),
        }
        return settings

    def _continue_after_load(self, current_low_poly, current_high_poly):
        """Continues processing after the project is ready, checks for baking."""
        if not self.is_batch_running: 
            logger.warning("_continue_after_load called, but batch is not running. Stopping.")
            return 
        
        mesh_name = os.path.basename(current_low_poly)
        
        # --- Check if Baking is Needed ---
        if not self.any_bake_selected:
            logger.info(f"No maps selected for baking. Skipping bake for {mesh_name}.")
            QtCore.QTimer.singleShot(0, self._process_next_mesh_pair)
            return

        # --- Prepare for Bake ---
        try:
            logger.info(f"Attempting to get texture sets for {mesh_name}...") 
            texture_sets = textureset.all_texture_sets()
            logger.info(f"Found {len(texture_sets)} texture sets for {mesh_name}.") 
            
            if not texture_sets:
                 raise RuntimeError(f"No texture sets found after loading {mesh_name}.")
            
            material_name = texture_sets[0].name() 
            
            needs_high_poly_for_maps = self.enabled_maps.get('normal', False) or self.enabled_maps.get('ambient_occlusion', False)
            
            if needs_high_poly_for_maps and not current_high_poly:
                logger.warning(f"Normal/AO bake requested but no matching high poly found for {mesh_name}. Skipping bake.")
                QtWidgets.QMessageBox.warning(self, "Baking Skipped", f"Normal/AO map baking skipped for {mesh_name} as no matching high poly was found.")
                QtCore.QTimer.singleShot(0, self._process_next_mesh_pair)
                return

            # --- Initiate Bake ---
            logger.info(f"Initiating bake for {mesh_name} (Material: {material_name})...")
            self.status_label.setText(f"Baking {self.current_pair_index + 1}/{len(self.mesh_pairs_to_process)}: {mesh_name}...")
            
            _bake_selected_maps(current_high_poly, material_name, self.enabled_maps)

        except Exception as e:
            error_msg = f"Error preparing/initiating bake for {mesh_name}: {str(e)}. Skipping."
            logger.error(error_msg)
            QtWidgets.QMessageBox.critical(self, "Baking Error", error_msg)
            QtCore.QTimer.singleShot(0, self._process_next_mesh_pair)

    def _start_polling_for_idle(self, mesh_name):
        """Starts a timer to periodically check if Painter is busy."""
        logger.info(f"Starting polling for idle status (mesh: {mesh_name})...")
        # Store loading state for the polling check
        self.loading_low_poly = self.mesh_pairs_to_process[self.current_pair_index][0]
        self.loading_high_poly = self.mesh_pairs_to_process[self.current_pair_index][1]
        
        self.idle_poll_timer = QtCore.QTimer(self)
        self.idle_poll_timer.setInterval(250) 
        self.idle_poll_timer.timeout.connect(self._check_if_idle)
        self.idle_poll_timer.start()

    def _check_if_idle(self):
        """Checks if Painter is busy using project.is_busy()."""
        if not self.is_batch_running or self.loading_low_poly is None:
            if hasattr(self, 'idle_poll_timer') and self.idle_poll_timer.isActive():
                self.idle_poll_timer.stop()
                logger.info("Polling stopped because batch is not running or mesh not loading.")
            return

        try:
            is_busy = project.is_busy()
            if not is_busy:
                self.idle_poll_timer.stop()
                mesh_name = os.path.basename(self.loading_low_poly)
                logger.info(f"Polling detected idle status for {mesh_name}. Proceeding...")
                
                current_low = self.loading_low_poly
                current_high = self.loading_high_poly
                
                self.loading_low_poly = None
                self.loading_high_poly = None
                
                self._continue_after_load(current_low, current_high)
                
        except Exception as e:
            logger.error(f"Error during idle polling: {e}")
            if hasattr(self, 'idle_poll_timer') and self.idle_poll_timer.isActive():
                self.idle_poll_timer.stop()
            self._finish_batch_process(f"Error during idle polling: {e}")

#--------------------------------------------------------
# BAKER FUNCTIONALITY (Reverted)
#--------------------------------------------------------

def _load_mesh_into_new_project(low_poly: str, resolution: int):
    """Creates a new project with the given low poly mesh. (Reverted)"""
    logger.info(f"Attempting to load mesh: {os.path.basename(low_poly)}")
    
    if project.is_open():
        logger.info("Closing existing project...")
        project.close()

    logger.info(f"Creating new project with mesh: {low_poly}")
    try:
        project_settings = project.Settings(
            normal_map_format=project.NormalMapFormat.DirectX,
            default_texture_resolution=resolution
        )
        project.create(mesh_file_path=low_poly, settings=project_settings)
        logger.info(f"Project creation command sent for: {os.path.basename(low_poly)}")

    except Exception as e:
        logger.error(f"Error during project creation: {str(e)}")
        if project.is_open():
            project.close()
        raise RuntimeError(f"Failed to create project with mesh {low_poly}: {str(e)}")

def _bake_selected_maps(high_poly: str | None, material_name: str, enabled_maps: Dict[str, bool]):
    """Initiates asynchronous baking of the selected maps. (Reverted to simpler version)"""
    bake_normal = enabled_maps.get('normal', False)
    bake_ao = enabled_maps.get('ambient_occlusion', False)
    bake_id = enabled_maps.get('id', False) # Assuming ID comes from Vertex Color implicitly

    if not (bake_normal or bake_ao or bake_id):
        logger.info("No maps selected for baking in _bake_selected_maps.")
        return # Nothing to do

    log_high_poly = os.path.basename(high_poly) if high_poly else "None"
    enabled_map_names = [k for k, v in enabled_maps.items() if v]
    logger.info(f"Configuring bake for material '{material_name}' with high poly '{log_high_poly}'. Enabled maps: {enabled_map_names}")

    try:
        baking_params = baking.BakingParameters.from_texture_set_name(material_name)
        if not baking_params:
            raise ValueError(f"Could not get BakingParameters for TextureSet '{material_name}'.")

        # Get common parameters (may not be strictly needed if not setting them)
        common_params = baking_params.common()
        if not common_params:
             logger.warning("Could not retrieve common baking parameters (might be ok).")

        # --- Prepare minimal parameters ---
        parameters_to_set = {}
        if (bake_normal or bake_ao) and high_poly:
            # Find the HipolyMesh key dynamically if possible
            hipoly_key_name = 'HipolyMesh' # Assume default key name
            hipoly_prop = common_params.get(hipoly_key_name) if common_params else None
            
            if hipoly_prop:
                 highpoly_mesh_path_url = QtCore.QUrl.fromLocalFile(high_poly).toString()
                 parameters_to_set[hipoly_prop] = highpoly_mesh_path_url
                 logger.info(f"Setting high poly mesh: {highpoly_mesh_path_url}")
            else:
                 logger.warning(f"Could not find property for '{hipoly_key_name}'. High poly might not be set.")
                 # Optionally, could try setting by string key if property lookup fails
                 # parameters_to_set[hipoly_key_name] = QtCore.QUrl.fromLocalFile(high_poly).toString()

        # --- Enable Bakers ---
        available_enums = {}
        if hasattr(baking, 'MeshMapUsage'):
            for name in dir(baking.MeshMapUsage):
                if not name.startswith('_'):
                    try:
                        enum_member = getattr(baking.MeshMapUsage, name)
                        if isinstance(enum_member, baking.MeshMapUsage):
                             available_enums[name] = enum_member
                    except AttributeError:
                        continue
        
        requested_to_enum_name = {}
        if bake_normal: requested_to_enum_name['normal'] = 'Normal'
        if bake_ao: requested_to_enum_name['ambient_occlusion'] = 'AO'
        if bake_id: requested_to_enum_name['id'] = 'ID' # Assuming 'ID' corresponds to VertexColor source implicitly

        bakers_to_enable_enums = []
        enabled_baker_names_log = []
        for map_key, enum_name in requested_to_enum_name.items():
            if enum_name in available_enums:
                bakers_to_enable_enums.append(available_enums[enum_name])
                enabled_baker_names_log.append(enum_name)
            else:
                 logger.warning(f"Cannot enable baker for '{map_key}': Enum 'baking.MeshMapUsage.{enum_name}' not found.")

        if not bakers_to_enable_enums:
             raise RuntimeError("No requested bakers could be enabled.")
        
        baking_params.set_enabled_bakers(bakers_to_enable_enums)
        logger.info(f"Successfully enabled bakers: {enabled_baker_names_log}")

        # --- Set Parameters (only high poly if needed) ---
        if parameters_to_set:
            logger.info(f"Setting parameters: {parameters_to_set}")
            baking.BakingParameters.set(parameters_to_set)
        else:
            logger.info("No specific parameters needed to be set apart from enabling bakers.")

        # --- Start Bake ---
        logger.info("Starting asynchronous bake...")
        baking.bake_selected_textures_async()         
        logger.info("Asynchronous bake initiated.")

    except Exception as e:
        error_msg = f"Failed to configure or start bake for '{material_name}': {str(e)}"
        logger.exception(error_msg) 
        raise RuntimeError(error_msg)

#--------------------------------------------------------
# PLUGIN ENTRY POINTS
#--------------------------------------------------------

def start_plugin():
    """Initialize the plugin"""
    global batch_baker_widget
    batch_baker_widget = BatchBakerWidget()
    batch_baker_widget.setWindowTitle("Batch Baker")
    docker = sp.ui.add_dock_widget(batch_baker_widget)
    logger.info("Batch Baker plugin started")
    
def close_plugin():
    """Clean up when the plugin is closed"""
    global batch_baker_widget
    
    if batch_baker_widget:
        # Disconnect the listeners first
        try:
            sp.event.DISPATCHER.disconnect(sp.event.BakingProcessEnded, batch_baker_widget._on_bake_finished)
            logger.info("Disconnected BakingProcessEnded listener.")
        except Exception as e:
            logger.warning(f"Failed to disconnect BakingProcessEnded listener: {str(e)}")
            
        # Stop any running batch cleanly
        if batch_baker_widget.is_batch_running:
             batch_baker_widget._finish_batch_process("Batch process stopped by plugin closure.")

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
# Helper Functions 
#--------------------------------------------------------
def _find_mesh_files(folder_path: str) -> List[str]:
    """Finds mesh files (.fbx, .obj) in the specified folder."""
    mesh_files = []
    supported_extensions = ('.fbx', '.obj') 
    try:
        for filename in os.listdir(folder_path):
            if filename.lower().endswith(supported_extensions):
                mesh_files.append(os.path.join(folder_path, filename))
    except FileNotFoundError:
        logger.warning(f"Mesh folder not found: {folder_path}")
    except Exception as e:
         logger.error(f"Error reading mesh folder {folder_path}: {e}")
    logger.info(f"Found {len(mesh_files)} mesh files in {folder_path}")
    return sorted(mesh_files) 

def _extract_base_name(filename: str) -> str:
    """Extracts the base name from a mesh filename (e.g., 'mesh_low.fbx' -> 'mesh')."""
    base = os.path.basename(filename)
    base = re.sub(r'(_low|_lp|_high|_hp)?(\.fbx|\.obj)$', '', base, flags=re.IGNORECASE)
    return base

def _match_meshes(high_poly_meshes: List[str], low_poly_meshes: List[str], match_by_naming: bool) -> List[Tuple[str, str | None]]:
    """Matches high poly meshes to low poly meshes."""
    mesh_pairs = []
    
    if not low_poly_meshes:
        logger.warning("No low poly meshes provided for matching.")
        return []

    if not high_poly_meshes:
        logger.warning("No high poly meshes provided. Baking from high poly will not be possible.")
        return [(lp, None) for lp in low_poly_meshes]

    if match_by_naming:
        logger.info("Attempting to match high/low meshes by base name...")
        low_poly_map = { _extract_base_name(lp): lp for lp in low_poly_meshes }
        high_poly_map = { _extract_base_name(hp): hp for hp in high_poly_meshes }
        
        for base_name, lp_path in low_poly_map.items():
            hp_path = high_poly_map.get(base_name)
            mesh_pairs.append((lp_path, hp_path)) # Will be None if no match
            if not hp_path:
                 logger.warning(f"  No matching high poly found for base name '{base_name}' (Low: '{os.path.basename(lp_path)}')")
            
    else:
        logger.info("Match by naming disabled.")
        if len(high_poly_meshes) == 1:
            hp_path = high_poly_meshes[0]
            logger.info(f"Using single high poly '{os.path.basename(hp_path)}' for all low poly meshes.")
            mesh_pairs = [(lp, hp_path) for lp in low_poly_meshes]
        elif len(high_poly_meshes) > 1:
             logger.warning("Multiple high poly meshes found, but matching by name is disabled. Cannot determine pairings.")
             mesh_pairs = [(lp, None) for lp in low_poly_meshes]
        else: # No high poly meshes
             mesh_pairs = [(lp, None) for lp in low_poly_meshes]

    if not mesh_pairs:
         logger.warning("Could not form any mesh pairs based on the current settings.")
         
    return mesh_pairs 