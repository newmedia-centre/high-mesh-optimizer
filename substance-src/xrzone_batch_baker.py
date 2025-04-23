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
import substance_painter.event as event

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("XRZone Batch Baker")

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
        
        self.default_low_poly = ""
        self.default_high_poly = ""
        
        # Add title and description
        title_label = QtWidgets.QLabel("XRZone Batch Baker")
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
   
        # Add to source layout
        source_layout.addLayout(low_poly_layout)
        source_layout.addLayout(high_poly_layout)
        
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
        self.bake_ao_checkbox = QtWidgets.QCheckBox("Bake Ambient Occlusion")
        self.bake_id_checkbox = QtWidgets.QCheckBox("Bake ID Map (Vertex Color -> BaseColor)")
        baking_layout.addWidget(self.bake_normal_checkbox)
        baking_layout.addWidget(self.bake_ao_checkbox)
        baking_layout.addWidget(self.bake_id_checkbox)
        
        # Add to settings layout
        settings_layout.addLayout(resolution_layout)
        settings_layout.addLayout(baking_layout)
        
        # Additional options
        options_layout = QtWidgets.QVBoxLayout()
        self.test_mode_checkbox = QtWidgets.QCheckBox("Test Mode (process only the first mesh)")
        self.test_mode_checkbox.setChecked(True)
        options_layout.addWidget(self.test_mode_checkbox)
        
        # Format combo
        self.format_combo = QtWidgets.QComboBox()
        for format in ["png", "tga", "exr"]:
            self.format_combo.addItem(format)
        self.format_combo.setVisible(True)
        format_label = QtWidgets.QLabel("Export Format:")
        format_layout = QtWidgets.QHBoxLayout()
        format_layout.addWidget(format_label)
        format_layout.addWidget(self.format_combo)
        format_layout.addStretch()
        options_layout.addLayout(format_layout) # Add format selector here
        
        # Export Settings
        export_group = QtWidgets.QGroupBox("Export Settings")
        export_layout = QtWidgets.QVBoxLayout()
        export_group.setLayout(export_layout)
        
        export_folder_layout = QtWidgets.QHBoxLayout()
        self.export_folder = QtWidgets.QLineEdit()
        # Set export folder to empty by default
        self.export_folder.setText("")
        export_folder_button = QtWidgets.QPushButton("Browse...")
        export_folder_button.clicked.connect(lambda: self._browse_folder(self.export_folder))
        export_folder_layout.addWidget(QtWidgets.QLabel("Export Folder:"))
        export_folder_layout.addWidget(self.export_folder)
        export_folder_layout.addWidget(export_folder_button)
        
        # Add export widgets to export layout
        export_layout.addLayout(export_folder_layout)
        
        # Action Buttons
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
        main_layout.addWidget(export_group)
        main_layout.addLayout(options_layout)
        main_layout.addLayout(buttons_layout) # Use the layout with the new button
        main_layout.addWidget(self.status_label)
        main_layout.addWidget(self.progress_bar)
        
        # Connect listeners
        event.DISPATCHER.connect(event.BakingProcessEnded, self._on_bake_finished)
        
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
        
        # Validate Inputs
        if not self._validate_inputs():
            self.status_label.setText("Input validation failed. Batch cancelled.")
            self.run_batch_button.setEnabled(True)
            self.is_batch_running = False
            self._update_progress(0, 0, self.status_label.text())
            return

        # Get Settings
        settings = self._get_settings()
        low_poly_folder = settings['low_poly_folder']
        high_poly_folder = settings['high_poly_folder']
        self.resolution_int = int(settings['resolution'].split('x')[0]) # Store for use in loop
        self.enabled_maps = settings['maps']
        test_mode = settings['test_mode']
        
        # Check if any maps are selected for baking
        self.any_bake_selected = any(self.enabled_maps.values())
        if not self.any_bake_selected:
             logger.info("No bake maps selected. Batch process will only load meshes.")

        # Find and Match Meshes
        try:
            self._update_progress(0, 1, "Finding mesh files...")
            low_poly_meshes = _find_mesh_files(low_poly_folder)
            if not low_poly_meshes:
                raise ValueError("No mesh files found in the low poly folder.")

            high_poly_meshes = []
            # ID map now also needs high poly
            needs_high_poly_globally = self.enabled_maps.get('normal', False) or \
                                       self.enabled_maps.get('ambient_occlusion', False) or \
                                       self.enabled_maps.get('id', False)
            
            if self.any_bake_selected and needs_high_poly_globally:
                high_poly_meshes = _find_mesh_files(high_poly_folder)
                if not high_poly_meshes:
                    # Make warning more specific
                    needed_by = []
                    if self.enabled_maps.get('normal'): needed_by.append("Normal")
                    if self.enabled_maps.get('ambient_occlusion'): needed_by.append("AO")
                    if self.enabled_maps.get('id'): needed_by.append("ID")
                    logger.warning(f"No mesh files found in high poly folder, but required for [{', '.join(needed_by)}]. Baking might fail.")

            all_mesh_pairs = _match_meshes(high_poly_meshes, low_poly_meshes)
            if not all_mesh_pairs:
                raise ValueError("Could not match any high poly to low poly meshes (or no low-poly meshes found).")

            # Prepare List for Processing (Apply Test Mode)
            if test_mode:
                self.mesh_pairs_to_process = all_mesh_pairs[:1]
                logger.info("Test Mode enabled: Processing only the first mesh pair.")
            else:
                self.mesh_pairs_to_process = all_mesh_pairs
                logger.info(f"Processing {len(self.mesh_pairs_to_process)} mesh pairs.")

            if not self.mesh_pairs_to_process:
                 raise ValueError("No mesh pairs selected for processing (after applying test mode).")

            # Start Processing
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

        # Store the pair we are about to load
        self.loading_low_poly = current_low_poly
        self.loading_high_poly = current_high_poly

        # Load Mesh
        try:
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
        
        # Check if the event object is an instance of BakingProcessEnded
        if isinstance(event_object, sp.event.BakingProcessEnded):
            if not self.is_batch_running or self.current_pair_index < 0 or self.current_pair_index >= len(self.mesh_pairs_to_process):
                 logger.warning("_on_bake_finished: Batch not running or index out of bounds. Returning.")
                 return 
                 
            mesh_name = os.path.basename(self.mesh_pairs_to_process[self.current_pair_index][0])
            
            # Try accessing event data - it might be the object itself or a .data attribute
            bake_data = None
            if isinstance(event_object, dict): # Should not happen now based on type check, but keep for safety
                bake_data = event_object
            elif hasattr(event_object, 'data') and isinstance(event_object.data, dict):
                bake_data = event_object.data
            else:
                # If it's not a dict and doesn't have a .data dict, maybe the object *itself* has the keys?
                # Try getting status directly from the object attributes
                if hasattr(event_object, 'status'):
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
                      QtWidgets.QMessageBox.warning(self, "Bake Error", f"Baking failed for {mesh_name}. Status: {status}. Check logs. Continuing...")
                 else:
                     logger.info(f"Bake completed successfully for {mesh_name}.")
            else:
                logger.warning(f"Could not extract bake status dictionary for {mesh_name}.")

            if bake_failed:
                 pass # Decide behavior on failure (currently logs and continues)
            else:
                # --- Export After Successful Bake --- 
                export_path_base = self._get_settings().get('export_folder')
                export_success = self._export_textures(export_path_base, mesh_name)
                if not export_success:
                    logger.warning(f"Export failed after successful bake for {mesh_name}, but continuing batch process.")
                    # Decide if we should stop the batch here

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
        
        # Use the length before clearing for final progress update
        final_count = len(self.mesh_pairs_to_process) if self.mesh_pairs_to_process else 0
        self._update_progress(final_count, final_count, final_message) 
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
        needs_high_poly = self.bake_normal_checkbox.isChecked() or \
                          self.bake_ao_checkbox.isChecked() or \
                          self.bake_id_checkbox.isChecked()
        if needs_high_poly:
            if not os.path.isdir(self.high_poly_folder.text()):
                QtWidgets.QMessageBox.warning(self, "Warning", "High poly folder does not exist (required for selected bakes)")
                return False
                
            high_poly_meshes = _find_mesh_files(self.high_poly_folder.text())
            if not high_poly_meshes:
                QtWidgets.QMessageBox.warning(self, "Warning", "No mesh files found in high poly folder (required for selected bakes)")
                return False
        
        # Check export folder (now mandatory for batch process)
        export_path = self.export_folder.text()
        if not export_path:
            QtWidgets.QMessageBox.warning(self, "Warning", "Export folder path cannot be empty.")
            return False
        # Check if the parent directory exists, as the export folder itself might not exist yet
        parent_dir = os.path.dirname(export_path)
        if parent_dir and not os.path.isdir(parent_dir): # Check parent only if export_path is not root
            QtWidgets.QMessageBox.warning(self, "Warning", f"Parent directory for export folder does not exist: {parent_dir}")
            return False
        elif not parent_dir and not os.path.isdir(export_path): # Handle case where export path is root (e.g., D:\)
            QtWidgets.QMessageBox.warning(self, "Warning", f"Export root directory does not exist: {export_path}")
            return False
        
        return True

    def _get_settings(self):
        # Collect settings from the UI
        settings = {
            'low_poly_folder': self.low_poly_folder.text(),
            'high_poly_folder': self.high_poly_folder.text(),
            'resolution': self.resolution_combo.currentText(),
            'format': self.format_combo.currentText(),
            'maps': {
                'normal': self.bake_normal_checkbox.isChecked(),
                'ambient_occlusion': self.bake_ao_checkbox.isChecked(),
                'id': self.bake_id_checkbox.isChecked()
            },
            'test_mode': self.test_mode_checkbox.isChecked(),
            # Export settings
            'export_folder': self.export_folder.text()
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
            logger.info(f"Skipping export for {mesh_name} as no maps were baked.")
            QtCore.QTimer.singleShot(0, self._process_next_mesh_pair)
            return

        # --- Prepare for Bake --- 
        try:
            texture_sets = textureset.all_texture_sets()
            
            if not texture_sets:
                 raise RuntimeError(f"No texture sets found after loading {mesh_name}.")
            
            material_name = texture_sets[0].name() 
            
            needs_high_poly_for_maps = self.enabled_maps.get('normal', False) or \
                                       self.enabled_maps.get('ambient_occlusion', False) or \
                                       self.enabled_maps.get('id', False)
            
            if needs_high_poly_for_maps and not current_high_poly:
                needed_by = []
                if self.enabled_maps.get('normal'): needed_by.append("Normal")
                if self.enabled_maps.get('ambient_occlusion'): needed_by.append("AO")
                if self.enabled_maps.get('id'): needed_by.append("ID")
                warning_msg = f"Baking skipped for {mesh_name}: Maps [{', '.join(needed_by)}] require a high poly mesh, but none was found/matched."
                logger.warning(warning_msg)
                QtWidgets.QMessageBox.warning(self, "Baking Skipped", warning_msg)
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
            return

        try:
            is_busy = project.is_busy()
            if not is_busy:
                self.idle_poll_timer.stop()
                
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

    def _export_textures(self, export_path_base: str, mesh_name: str) -> bool:
        """Exports textures for the current project using a custom configuration.

        Args:
            export_path_base: The base directory selected for export.
            mesh_name: The base name of the mesh (e.g., '126_low') to create a subfolder.
            
        Returns:
            True if export was successful, False otherwise.
        """
        if not project.is_open():
            logger.error("Export called but no project is open.")
            return False

        # --- Get Settings Needed for Export ---         
        settings = self._get_settings() 
        export_format = settings.get('format', 'png') # Default to png
        enabled_maps = settings.get('maps', {}) # Get which maps were baked
        
        # --- Use Export Path Directly --- 
        if not os.path.isdir(export_path_base):
            try:
                os.makedirs(export_path_base, exist_ok=True)
            except OSError as e:
                logger.error(f"Could not create export directory '{export_path_base}': {e}")
                QtWidgets.QMessageBox.critical(self, "Export Error", f"Could not create export directory: {export_path_base}\n{e}")
                return False
        
        logger.info(f"Starting texture export for {mesh_name} to '{export_path_base}'...")
        self.status_label.setText(f"Exporting {mesh_name}...")
        QtWidgets.QApplication.processEvents() # Update UI
        
        # --- Get Texture Sets --- 
        texture_sets = textureset.all_texture_sets()
        if not texture_sets:
             logger.error(f"No texture sets found to export for {mesh_name}.")
             return False 

        # --- Build Custom Export Preset Maps --- 
        preset_maps = []
        output_map_names_for_filter = [] # Keep track of defined map names for the filter

        # Define basic parameters based on UI format choice
        bit_depth = '8' # Default
        if export_format == 'exr':
             bit_depth = '16' # Use 16-bit for EXR
        elif export_format == 'png':
             bit_depth = '16' # Allow 16-bit PNG
        
        map_base_parameters = {
            "fileFormat": export_format,
            "bitDepth": bit_depth,
            "dithering": False,
            # sizeLog2 will use project default if not specified
            "paddingAlgorithm": "infinite" # Apply infinite padding globally later, but can be default here
        }

        # -- Normal Map --
        if enabled_maps.get('normal'):
            map_name = "$mesh_$textureSet_Normal"
            preset_maps.append({
                "fileName": map_name,
                "channels": [
                    {"destChannel": "R", "srcChannel": "R", "srcMapType": "meshMap", "srcMapName": "normal_base"},
                    {"destChannel": "G", "srcChannel": "G", "srcMapType": "meshMap", "srcMapName": "normal_base"},
                    {"destChannel": "B", "srcChannel": "B", "srcMapType": "meshMap", "srcMapName": "normal_base"}
                ],
                "parameters": map_base_parameters.copy()
            })
            output_map_names_for_filter.append(map_name)
            
        # -- Ambient Occlusion Map --
        if enabled_maps.get('ambient_occlusion'):
            map_name = "$mesh_$textureSet_AmbientOcclusion"
            preset_maps.append({
                "fileName": map_name,
                "channels": [
                    # Export AO to grayscale (Luminance)
                    {"destChannel": "L", "srcChannel": "L", "srcMapType": "meshMap", "srcMapName": "ambient_occlusion"}
                ],
                "parameters": map_base_parameters.copy()
            })
            output_map_names_for_filter.append(map_name)

        # -- ID Map --
        if enabled_maps.get('id'):
            map_name = "$mesh_$textureSet_BaseColor" # Output ID data as BaseColor filename, now with mesh name
            preset_maps.append({
                "fileName": map_name,
                "channels": [
                    # Source is still the ID mesh map
                    {"destChannel": "R", "srcChannel": "R", "srcMapType": "meshMap", "srcMapName": "id"},
                    {"destChannel": "G", "srcChannel": "G", "srcMapType": "meshMap", "srcMapName": "id"},
                    {"destChannel": "B", "srcChannel": "B", "srcMapType": "meshMap", "srcMapName": "id"}
                ],
                "parameters": map_base_parameters.copy()
            })
            output_map_names_for_filter.append(map_name)
            
        # --- Handle Case Where No Maps Were Baked (Maybe export default channels?) ---
        # For now, if preset_maps is empty, we cannot export based on this config.
        if not preset_maps:
            logger.warning(f"No bake maps were enabled for {mesh_name}. Cannot export using custom preset method.")
            # Optionally: Fallback to a default preset or skip export?
            # For now, let's skip and return success as nothing *failed*, just nothing to do.
            self.status_label.setText(f"Skipped export for {mesh_name} (no maps baked)")
            return True # Return success because no *error* occurred

        # --- Build Export List --- 
        export_list_items = []
        for ts in texture_sets:
            export_list_items.append({
                "rootPath": ts.name(),
                "exportPreset": "BatchBakerCustomPreset" # Use our defined preset
            })

        # --- Define Full Export Configuration --- 
        export_config = {
            "exportPath": export_path_base,
            "exportShaderParams": False, # Typically not needed for just textures
            "exportPresets": [
                {
                    "name": "BatchBakerCustomPreset",
                    "maps": preset_maps
                }
            ],
            "exportList": export_list_items,
            "exportParameters": [
                # Global parameter override (e.g., ensure infinite padding for all)
                # Note: padding was also set in map_base_parameters, this acts as a final override
                { 
                    "filter": {}, # Apply to all
                    "parameters": { "paddingAlgorithm": "infinite" } 
                }
            ]
        }

        # --- Execute Export --- 
        try:
            result = export.export_project_textures(export_config)
            
            if result.status == ExportStatus.Success:
                logger.info(f"Texture export successful for {mesh_name}.")
                self.status_label.setText(f"Exported {mesh_name}")
                return True
            else:
                logger.error(f"Texture export failed for {mesh_name}. Status: {result.status}, Message: {result.message}")
                # Attempt to log configuration on failure for easier debug
                try:
                     logger.error(f"Failing Export Config: {export_config}")
                except Exception as log_e:
                     logger.error(f"Could not log full export config on failure: {log_e}")
                QtWidgets.QMessageBox.critical(self, "Export Error", f"Texture export failed for {mesh_name}:\n{result.message}")
                return False
                
        except Exception as e:
            logger.exception(f"An unexpected error occurred during export for {mesh_name}: {e}")
            # Attempt to log configuration on exception
            try:
                 logger.error(f"Failing Export Config (Exception): {export_config}")
            except Exception as log_e:
                 logger.error(f"Could not log full export config on exception: {log_e}")
            QtWidgets.QMessageBox.critical(self, "Export Error", f"An unexpected error occurred during export for {mesh_name}:\n{e}")
            return False

#--------------------------------------------------------
# BAKER FUNCTIONALITY
#--------------------------------------------------------

def _load_mesh_into_new_project(low_poly: str, resolution: int):
    """Creates a new project with the given low poly mesh."""
    logger.info(f"Attempting to load mesh: {os.path.basename(low_poly)}")
    
    if project.is_open():
        project.close()

    try:
        project_settings = project.Settings(
            normal_map_format=project.NormalMapFormat.DirectX,
            default_texture_resolution=resolution
        )
        project.create(mesh_file_path=low_poly, settings=project_settings)

    except Exception as e:
        logger.error(f"Error during project creation: {str(e)}")
        if project.is_open():
            project.close()
        raise RuntimeError(f"Failed to create project with mesh {low_poly}: {str(e)}")

def _bake_selected_maps(high_poly: str | None, material_name: str, enabled_maps: Dict[str, bool]):
    """Initiates asynchronous baking of the selected maps."""
    bake_normal = enabled_maps.get('normal', False)
    bake_ao = enabled_maps.get('ambient_occlusion', False)
    bake_id = enabled_maps.get('id', False)

    if not (bake_normal or bake_ao or bake_id):
        return
    
    try:
        baking_params = baking.BakingParameters.from_texture_set_name(material_name)
        if not baking_params:
            raise ValueError(f"Could not get BakingParameters for TextureSet '{material_name}'.")

        common_params = baking_params.common()
        if not common_params:
             logger.warning("Could not retrieve common baking parameters (might be ok).")

        # --- Prepare minimal parameters --- 
        parameters_to_set = {}
        hipoly_key_name = 'HipolyMesh'
        # Set high poly mesh if needed by ANY selected map that uses it
        if (bake_normal or bake_ao or bake_id) and high_poly:
            hipoly_prop = common_params.get(hipoly_key_name) if common_params else None
            if hipoly_prop:
                 highpoly_mesh_path_url = QtCore.QUrl.fromLocalFile(high_poly).toString()
                 parameters_to_set[hipoly_prop] = highpoly_mesh_path_url
            elif hipoly_key_name not in parameters_to_set: 
                 logger.warning(f"Could not find property object for '{hipoly_key_name}'. Attempting to set high poly mesh by key string.")
                 try:
                     parameters_to_set[hipoly_key_name] = QtCore.QUrl.fromLocalFile(high_poly).toString()
                 except Exception as e:
                      logger.error(f"Failed to set high poly mesh using key string '{hipoly_key_name}': {e}")
        elif (bake_normal or bake_ao or bake_id) and not high_poly:
            needed_by = []
            if bake_normal: needed_by.append("Normal")
            if bake_ao: needed_by.append("AO")
            if bake_id: needed_by.append("ID (from High Poly)")
            logger.warning(f"High poly mesh required by [{', '.join(needed_by)}] but not provided or found. Bake may fail or produce incorrect results.")

        # Set Cage Mode only if needed for Normal/AO
        cage_key = 'CageMode'
        cage_value = 'Automatic (experimental)'
        if (bake_normal or bake_ao) and high_poly: 
            if common_params and cage_key in common_params:
                 cage_prop = common_params[cage_key]
                 try:
                      if hasattr(cage_prop, 'enum_value') and hasattr(cage_prop, 'enum_values') and cage_value in cage_prop.enum_values():
                          parameters_to_set[cage_prop] = cage_prop.enum_value(cage_value)
                      else:
                          parameters_to_set[cage_prop] = cage_value 
                 except Exception as e: 
                     logger.warning(f"Error setting cage mode via property '{cage_key}': {e}. Falling back to setting string value directly on property.")
                     try:
                         parameters_to_set[cage_prop] = cage_value 
                     except Exception as final_e:
                         logger.error(f"Failed to set cage mode even with string fallback on property: {final_e}. Trying key string assignment as last resort.")
                         parameters_to_set[cage_key] = cage_value
            else:
                 logger.warning(f"Could not find property for '{cage_key}' in common_params or common_params unavailable. Attempting to set cage mode by key string '{cage_key}'.")
                 parameters_to_set[cage_key] = cage_value

        # --- Configure ID Specific Parameters --- 
        if bake_id:
            if not high_poly:
                # Warning logged above if high poly missing but needed
                pass # logger.warning("ID bake requested, but no high poly mesh provided. Cannot bake ID map from high poly vertex colors. Skipping ID map configuration.")
            else:
                id_baker = baking_params.baker(baking.MeshMapUsage.ID)
                if id_baker:
                    id_params = id_baker
                    id_param_keys = id_params.keys()
                    color_source_key = None 
                    for key in id_param_keys:
                        if 'color' in key.lower() and 'source' in key.lower():
                            color_source_key = key
                            break 
                    if color_source_key:
                        color_source_prop = id_params[color_source_key]
                        try:
                            # Set Color Source to Vertex Color (assumes 0 means use Vertex Color param)
                            vertex_color_int_value = 0 
                            parameters_to_set[color_source_prop] = vertex_color_int_value
                        except Exception as e:
                            logger.error(f"  Failed to set ID Param '{color_source_key}' using integer value {vertex_color_int_value}: {e}")
                    else:
                        logger.warning("  Could not find the 'Color Source' parameter key for the ID baker.")
                else:
                     logger.warning("Could not get ID baker parameters.") 

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
        if bake_id: requested_to_enum_name['id'] = 'ID' 

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

        # --- Set Parameters --- 
        if parameters_to_set:
            baking.BakingParameters.set(parameters_to_set)
        else:
            logger.info("No specific bake parameters needed beyond defaults.")

        # --- Start Bake ---
        logger.info("Starting asynchronous bake...")
        baking.bake_selected_textures_async()

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
    batch_baker_widget.setWindowTitle("XRZone Batch Baker")
    docker = sp.ui.add_dock_widget(batch_baker_widget)
    logger.info("XRZone Batch Baker plugin started")
    
def close_plugin():
    """Clean up when the plugin is closed"""
    global batch_baker_widget
    
    if batch_baker_widget:
        # Disconnect the listeners first
        try:
            sp.event.DISPATCHER.disconnect(sp.event.BakingProcessEnded, batch_baker_widget._on_bake_finished)
        except Exception as e:
            logger.warning(f"Failed to disconnect BakingProcessEnded listener: {str(e)}")
            
        # Stop any running batch cleanly
        if batch_baker_widget.is_batch_running:
             batch_baker_widget._finish_batch_process("Batch process stopped by plugin closure.")

        sp.ui.delete_ui_element(batch_baker_widget)
        batch_baker_widget = None
    
    logger.info("XRZone Batch Baker plugin closed")

#--------------------------------------------------------
# Helper Functions 
#--------------------------------------------------------
def _find_mesh_files(folder_path: str) -> List[str]:
    """Finds mesh files (.fbx, .obj, .ply) in the specified folder."""
    mesh_files = []
    supported_extensions = ('.fbx', '.obj', '.ply') 
    try:
        for filename in os.listdir(folder_path):
            if filename.lower().endswith(supported_extensions):
                mesh_files.append(os.path.join(folder_path, filename))
    except FileNotFoundError:
        logger.warning(f"Mesh folder not found: {folder_path}")
    except Exception as e:
         logger.error(f"Error reading mesh folder {folder_path}: {e}")
    return sorted(mesh_files) 

def _extract_base_name(filename: str) -> str:
    """Extracts the base name from a mesh filename (e.g., 'mesh_low.fbx' -> 'mesh')."""
    base = os.path.basename(filename)
    base = re.sub(r'(_low|_lp|_high|_hp)?(\.fbx|\.obj|\.ply)$', '', base, flags=re.IGNORECASE)
    return base

def _match_meshes(high_poly_meshes: List[str], low_poly_meshes: List[str]) -> List[Tuple[str, str | None]]:
    """Matches high poly meshes to low poly meshes based on extracted base name."""
    mesh_pairs = []
    
    if not low_poly_meshes:
        logger.warning("No low poly meshes provided for matching.")
        return []

    if not high_poly_meshes:
        return [(lp, None) for lp in low_poly_meshes]

    # Proceed with matching by name since high poly meshes exist
    low_poly_map = { _extract_base_name(lp): lp for lp in low_poly_meshes }
    high_poly_map = { _extract_base_name(hp): hp for hp in high_poly_meshes }

    for base_name, lp_path in low_poly_map.items():
        hp_path = high_poly_map.get(base_name)
        mesh_pairs.append((lp_path, hp_path)) 
        if not hp_path:
             logger.warning(f"  No matching high poly found for base name '{base_name}' (Low: '{os.path.basename(lp_path)}')")
            
    if not mesh_pairs and low_poly_meshes: # Only warn if low polys existed but no pairs were made
         logger.warning("Could not form any mesh pairs based on the current settings and found meshes.")
         
    return mesh_pairs 