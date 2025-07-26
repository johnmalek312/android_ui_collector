# gui.py
"""
Minimal GUI for screenshot capture and annotation using PyQt5.

Features:
1. Take Screenshot button captures screenshot from the first available Android device (via AdbTools),
   stores it under ~/Desktop/Images/ and shows it in the GUI.
2. User can click on the displayed screenshot to add an annotation:
   * Places a red dot at the click location.
   * Normalises coordinates to the range [0.0, 1.0].
   * Prompts the user for a textual description.
   * Appends the data to annotations.json under the same Images folder.

This file purposefully avoids tkinter in favour of PyQt5.
"""

import json
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple

from PyQt5.QtCore import Qt, QPoint, pyqtSignal
from PyQt5.QtGui import QPixmap, QPainter, QPen, QImage, QFontMetrics
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QTextEdit,
    QMessageBox,
    QScrollArea,
    QDoubleSpinBox,
)

from adb import AdbTools  # Local module


IMAGES_DIR = Path(os.path.expanduser("~/Desktop/Images"))
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
ANNOTATIONS_PATH = IMAGES_DIR / "annotations.json"


class ClickableLabel(QLabel):
    """QLabel that emits mouse interaction signals for click & drag."""

    clicked = pyqtSignal(QPoint)      # Mouse press (left button)
    dragged = pyqtSignal(QPoint)      # Mouse move while pressed
    released = pyqtSignal(QPoint)     # Mouse release

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dragging = False
        self.setMouseTracking(True)

    def mousePressEvent(self, event):  # noqa: N802
        if self.pixmap() is None:
            return
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self.clicked.emit(event.pos())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._dragging:
            self.dragged.emit(event.pos())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if self._dragging and event.button() == Qt.LeftButton:
            self._dragging = False
            self.released.emit(event.pos())
        super().mouseReleaseEvent(event)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Screenshot Annotator")

        # Core Adb helper
        self.adb_tools = AdbTools()

        # UI Elements
        self.take_ss_btn = QPushButton("Take Screenshot")
        self.take_ss_btn.clicked.connect(self.handle_take_screenshot)

        self.image_label = ClickableLabel()
        self.image_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.image_label.clicked.connect(self.handle_image_click)
        self.image_label.dragged.connect(self.handle_drag_move)
        self.image_label.released.connect(self.handle_drag_release)

        # Embed the label inside a scroll area so large images are scrollable
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.image_label)

        layout = QVBoxLayout()
        layout.addWidget(self.take_ss_btn)
        layout.addWidget(scroll_area)

        # Annotation input section - coords & buttons on one row, desc on next
        annot_layout = QVBoxLayout()

        coords_layout = QHBoxLayout()
        self.point_count_label = QLabel("Points: 0/4")

        # Undo / Redo & Zoom buttons
        self.undo_btn = QPushButton("Undo")
        self.redo_btn = QPushButton("Redo")
        self.zoom_in_btn = QPushButton("+")  # Zoom in
        self.zoom_out_btn = QPushButton("–")  # Zoom out

        self.undo_btn.clicked.connect(self.handle_undo)
        self.redo_btn.clicked.connect(self.handle_redo)
        self.zoom_in_btn.clicked.connect(lambda: self._zoom(1.25))
        self.zoom_out_btn.clicked.connect(lambda: self._zoom(0.8))

        self.save_btn = QPushButton("Save")
        self.cancel_btn = QPushButton("Cancel")

        self.save_btn.clicked.connect(self.handle_save_annotation)
        self.cancel_btn.clicked.connect(self.handle_cancel_annotation)

        coords_layout.addWidget(self.point_count_label)
        coords_layout.addStretch(1)
        coords_layout.addWidget(self.undo_btn)
        coords_layout.addWidget(self.redo_btn)
        coords_layout.addStretch(1)
        coords_layout.addWidget(QLabel("Zoom:"))
        coords_layout.addWidget(self.zoom_out_btn)
        coords_layout.addWidget(self.zoom_in_btn)
        # Save/Cancel at the end
        coords_layout.addStretch(1)
        coords_layout.addWidget(self.save_btn)
        coords_layout.addWidget(self.cancel_btn)

        # Add the buttons row into annotation layout
        annot_layout.addLayout(coords_layout)

        # Grid of spin boxes for point coordinates
        self.point_spin_boxes: List[Tuple[QDoubleSpinBox, QDoubleSpinBox]] = []
        points_grid = QVBoxLayout()
        for idx in range(4):
            row = QHBoxLayout()
            row.addWidget(QLabel(f"P{idx + 1}:"))
            x_spin = QDoubleSpinBox()
            y_spin = QDoubleSpinBox()
            for sp in (x_spin, y_spin):
                sp.setDecimals(3)
                sp.setRange(0.0, 1.0)
                sp.setSingleStep(0.001)
                sp.setEnabled(False)
            # Connect updates
            x_spin.valueChanged.connect(lambda _v, i=idx: self.on_spin_changed(i))
            y_spin.valueChanged.connect(lambda _v, i=idx: self.on_spin_changed(i))
            row.addWidget(x_spin)
            row.addWidget(y_spin)
            points_grid.addLayout(row)
            self.point_spin_boxes.append((x_spin, y_spin))

        annot_layout.addLayout(points_grid)

        self.desc_input = QTextEdit()
        self.desc_input.setPlaceholderText("Enter description…")
        # Auto-resizing: start at 2 lines and grow with content
        self.desc_min_lines = 2
        self._set_desc_height(self.desc_min_lines)
        self.desc_input.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.desc_input.textChanged.connect(self.adjust_desc_height)
        self.desc_input.setEnabled(False)

        annot_layout.addWidget(self.desc_input)

        layout.addLayout(annot_layout)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Internal state
        self.current_screenshot_path: Path | None = None
        self.current_img_bytes: bytes | None = None  # For deferred saving
        self.original_pixmap: QPixmap | None = None  # Full-resolution image
        self.base_pixmap: QPixmap | None = None  # Scaled pixmap with saved dots
        self.pending_points: List[tuple[float, float]] = []  # Accumulated normalized points (max 4)
        self.undo_stack: List[List[tuple[float, float]]] = []
        self.redo_stack: List[List[tuple[float, float]]] = []
        self.current_scale: float = 1.0  # Zoom scale relative to original
        self._drag_index: int | None = None  # Index of point being dragged
        self.last_description: str = ""  # Track last saved description
        self.last_saved_screenshot: str | None = None  # Track last saved screenshot filename

    # ----------------- GUI Slots -----------------
    def handle_take_screenshot(self):
        """Capture screenshot, save to disk & display."""
        try:
            fmt, img_bytes = self.adb_tools.take_screenshot()
        except Exception as exc:  # pylint: disable=broad-except
            QMessageBox.critical(self, "Error", f"Failed to take screenshot: {exc}")
            return

        # Store bytes in memory for deferred saving
        self.current_img_bytes = img_bytes
        self.current_screenshot_path = None  # Not saved yet

        # Load into QPixmap
        image = QImage.fromData(img_bytes, fmt)
        pixmap_full = QPixmap.fromImage(image)
        if pixmap_full.isNull():
            QMessageBox.critical(self, "Error", "Failed to load screenshot into GUI.")
            return

        # Scale to fit 80% of screen height if necessary
        screen_geom = QApplication.primaryScreen().availableGeometry()
        max_height = int(screen_geom.height() * 0.8)
        if pixmap_full.height() > max_height:
            scaled_pixmap = pixmap_full.scaledToHeight(max_height, Qt.SmoothTransformation)
        else:
            scaled_pixmap = pixmap_full

        self.original_pixmap = pixmap_full
        self.base_pixmap = scaled_pixmap.copy()
        self.current_scale = scaled_pixmap.width() / max(1, self.original_pixmap.width())
        # Reset description and last saved markers for new screenshot
        self.desc_input.clear()
        self.last_description = ""
        self.last_saved_screenshot = None
        self._set_desc_height(self.desc_min_lines)
        self.image_label.setPixmap(scaled_pixmap)
        self.image_label.adjustSize()
        self.resize(scaled_pixmap.width() + 50, scaled_pixmap.height() + 120)

        # Enable zoom buttons now that an image is loaded
        self.zoom_in_btn.setEnabled(True)
        self.zoom_out_btn.setEnabled(True)

    def handle_image_click(self, pos: QPoint):
        """Handle annotation creation on image click."""
        if self.original_pixmap is None:
            return  # Nothing to process
        # Compute normalized coords relative to displayed pixmap (top-left aligned)
        displayed_pixmap = self.image_label.pixmap()
        if displayed_pixmap is None:
            return

        pix_w = displayed_pixmap.width()
        pix_h = displayed_pixmap.height()

        img_x = pos.x()
        img_y = pos.y()

        if not (0 <= img_x < pix_w and 0 <= img_y < pix_h):
            return  # clicked outside the actual image

        x_norm = img_x / pix_w
        y_norm = img_y / pix_h

        # If already 4 points, check if click is near one to start drag
        if len(self.pending_points) == 4:
            idx = self._get_nearest_point_index(pos)
            if idx is not None:
                self._drag_index = idx
                self._record_state_for_undo()
                return  # Dragging will be handled in handle_drag_move

        # Append point (max 4)
        if len(self.pending_points) >= 4:
            return  # Ignore extra addition

        # Record state for undo
        self._record_state_for_undo()

        self.pending_points.append((round(x_norm, 6), round(y_norm, 6)))
        self.redo_stack.clear()
        self._redraw_preview()
        self._update_spin_boxes_state()

        # Update point count label
        self.point_count_label.setText(f"Points: {len(self.pending_points)}/4")

        # Enable cancel immediately, enable save & desc when 4 points selected
        self._update_action_buttons()

    def handle_save_annotation(self):
        """Persist the pending annotation and finalise dot."""
        if (
            len(self.pending_points) != 4
            or self.image_label.pixmap() is None
        ):
            return

        desc = self.desc_input.toPlainText().strip()
        if not desc:
            QMessageBox.warning(self, "Warning", "Please enter a description.")
            return

        # Ensure screenshot is saved to get path for duplicate check
        if self.current_screenshot_path is None:
            if self.current_img_bytes is None:
                QMessageBox.critical(self, "Error", "No image data available to save.")
                return
            timestamp = int(time.time())
            filename = f"screenshot_{timestamp}.png"
            img_path = IMAGES_DIR / filename
            try:
                with open(img_path, "wb") as f:
                    f.write(self.current_img_bytes)
            except OSError as exc:
                QMessageBox.critical(self, "Error", f"Failed to save image: {exc}")
                return
            self.current_screenshot_path = img_path

        # Confirm if description unchanged for same screenshot
        if (
            desc == self.last_description
            and self.current_screenshot_path is not None
            and self.last_saved_screenshot == self.current_screenshot_path.name
            and desc != ""
        ):
            reply = QMessageBox.question(
                self,
                "Confirm Save",
                "You have already used this description. Save again with the same description?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.No:
                return

        # Points list is finalised
        points_payload = [
            {"x": p[0], "y": p[1]} for p in self.pending_points
        ]
        # (Deferred screenshot saving is handled above)

        entry: Dict[str, Any] = {
            "screenshot": self.current_screenshot_path.name,
            "timestamp": int(time.time()),
            "points": points_payload,
            "description": desc,
        }
        self._append_annotation(entry)

        # Commit the temp pixmap as new base
        self.base_pixmap = self.image_label.pixmap().copy()

        # Remember last description and screenshot
        self.last_description = desc
        if self.current_screenshot_path is not None:
            self.last_saved_screenshot = self.current_screenshot_path.name

        # Clear input state
        self._reset_input_section()

    def handle_cancel_annotation(self):
        """Cancel pending annotation and revert to last saved state."""
        if self.base_pixmap is not None:
            self.image_label.setPixmap(self.base_pixmap)
            self.image_label.adjustSize()
        self._reset_input_section()

    def _reset_input_section(self):
        """Disable and clear the description input and buttons."""
        self.pending_points = []
        # Keep existing description (do not clear)
        # Adjust height in case user reduced content manually
        self._set_desc_height(max(self.desc_input.document().blockCount(), self.desc_min_lines))
        self.point_count_label.setText("Points: 0/4")
        for w in (self.desc_input, self.save_btn, self.cancel_btn, self.undo_btn, self.redo_btn, self.zoom_in_btn, self.zoom_out_btn):
            w.setEnabled(False)

        # Disable spin boxes
        for x_spin, y_spin in self.point_spin_boxes:
            x_spin.setEnabled(False)
            y_spin.setEnabled(False)

        # Clear stacks
        self.undo_stack.clear()
        self.redo_stack.clear()

    # The spin-based preview updates are no longer needed; retain stub for compatibility.

    def on_spin_changed(self, idx: int):
        """Update pending_points when a spin box is edited."""
        if idx >= len(self.pending_points):
            return
        x_val = round(self.point_spin_boxes[idx][0].value(), 6)
        y_val = round(self.point_spin_boxes[idx][1].value(), 6)
        self.pending_points[idx] = (x_val, y_val)
        self._redraw_preview()

    # Legacy stub kept for compatibility
    def update_preview_from_spin(self):
        pass

    def _redraw_preview(self):
        """Redraw the image label with current pending points overlay."""
        if self.base_pixmap is None:
            return

        temp_pixmap = self.base_pixmap.copy()
        painter = QPainter(temp_pixmap)
        pen = QPen(Qt.red)
        pen.setWidth(4)
        painter.setPen(pen)
        painter.setBrush(Qt.red)

        width = temp_pixmap.width()
        height = temp_pixmap.height()

        # Convert normalized points to pixel coords
        pixel_points = [QPoint(int(x * width), int(y * height)) for x, y in self.pending_points]

        # Draw points
        radius = 3
        for pt in pixel_points:
            painter.drawEllipse(pt, radius, radius)

        # Draw lines between consecutive points
        if len(pixel_points) >= 2:
            for i in range(len(pixel_points) - 1):
                painter.drawLine(pixel_points[i], pixel_points[i + 1])
        # Close the square if 4 points
        if len(pixel_points) == 4:
            painter.drawLine(pixel_points[3], pixel_points[0])

        painter.end()

        self.image_label.setPixmap(temp_pixmap)
        self.image_label.adjustSize()

    # ----------- Description auto-resize ------------
    def adjust_desc_height(self):
        """Adjust the QTextEdit height based on line count."""
        metrics = QFontMetrics(self.desc_input.font())
        line_height = metrics.lineSpacing()
        lines = max(self.desc_input.document().blockCount(), self.desc_min_lines)
        new_height = (line_height * lines) + 10  # padding
        self.desc_input.setFixedHeight(new_height)

    def _set_desc_height(self, lines: int):
        """Helper to set initial/fixed description height for given lines."""
        metrics = QFontMetrics(self.desc_input.font())
        line_height = metrics.lineSpacing()
        self.desc_input.setFixedHeight((line_height * lines) + 10)

    # ----------------- Persistence -----------------
    def _append_annotation(self, entry: Dict[str, Any]):
        """Append a new annotation entry to the annotations file."""
        existing: List[Dict[str, Any]]
        if ANNOTATIONS_PATH.exists():
            try:
                with open(ANNOTATIONS_PATH, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError):
                existing = []
        else:
            existing = []

        existing.append(entry)
        try:
            with open(ANNOTATIONS_PATH, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2)
        except OSError as exc:
            QMessageBox.warning(self, "Warning", f"Failed to write annotations: {exc}")

    # ---------------- Undo / Redo ------------------

    def _record_state_for_undo(self):
        """Push current points list onto undo stack."""
        self.undo_stack.append(self.pending_points.copy())
        # Limit history to avoid memory bloat (keep last 20)
        if len(self.undo_stack) > 20:
            self.undo_stack.pop(0)

    def handle_undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append(self.pending_points.copy())
        self.pending_points = self.undo_stack.pop()
        self._restore_state_from_points()

    def handle_redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(self.pending_points.copy())
        self.pending_points = self.redo_stack.pop()
        self._restore_state_from_points()

    def _restore_state_from_points(self):
        """Sync spin boxes, label, preview, and action buttons with current points list."""
        self._update_spin_boxes_state()
        self.point_count_label.setText(f"Points: {len(self.pending_points)}/4")
        self._redraw_preview()
        self._update_action_buttons()

    def _update_spin_boxes_state(self):
        """Enable/disable and set values of spin boxes based on current points."""
        for idx, (x_spin, y_spin) in enumerate(self.point_spin_boxes):
            if idx < len(self.pending_points):
                x_spin.blockSignals(True)
                y_spin.blockSignals(True)
                x_spin.setValue(self.pending_points[idx][0])
                y_spin.setValue(self.pending_points[idx][1])
                x_spin.setEnabled(True)
                y_spin.setEnabled(True)
                x_spin.blockSignals(False)
                y_spin.blockSignals(False)
            else:
                x_spin.setEnabled(False)
                y_spin.setEnabled(False)
                x_spin.setValue(0.0)
                y_spin.setValue(0.0)

    def _update_action_buttons(self):
        """Enable/disable save/undo/redo buttons according to state."""
        self.undo_btn.setEnabled(len(self.pending_points) > 0)
        self.redo_btn.setEnabled(len(self.redo_stack) > 0)
        self.cancel_btn.setEnabled(len(self.pending_points) > 0)
        # Save enabled only if 4 points
        self.save_btn.setEnabled(len(self.pending_points) == 4)
        self.desc_input.setEnabled(len(self.pending_points) == 4)

    # ----------------- Zoom Handling -----------------

    def _zoom(self, factor: float):
        """Zoom the image by a given factor (>1 zooms in, <1 zooms out)."""
        if self.base_pixmap is None or self.original_pixmap is None:
            return

        new_scale = self.current_scale * factor
        # Clamp scale
        new_scale = max(0.2, min(new_scale, 5.0))
        if abs(new_scale - self.current_scale) < 0.001:
            return  # No effective change

        self.current_scale = new_scale

        # Rescale the base pixmap (which includes saved dots)
        target_w = int(self.original_pixmap.width() * self.current_scale)
        target_h = int(self.original_pixmap.height() * self.current_scale)

        scaled_base = self.base_pixmap.scaled(target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.base_pixmap = scaled_base

        self._redraw_preview()

        # Adjust scroll area widget size
        self.image_label.adjustSize()
        self.resize(scaled_base.width() + 50, scaled_base.height() + 120)

    # ---------------- Drag Move --------------------

    def _get_nearest_point_index(self, pos: QPoint) -> int | None:
        """Return index of point whose pixel coords are within threshold of pos."""
        if self.base_pixmap is None:
            return None
        width = self.base_pixmap.width()
        height = self.base_pixmap.height()
        threshold = 8  # pixels
        for idx, (x_norm, y_norm) in enumerate(self.pending_points):
            px = int(x_norm * width)
            py = int(y_norm * height)
            if abs(px - pos.x()) <= threshold and abs(py - pos.y()) <= threshold:
                return idx
        return None

    def handle_drag_move(self, pos: QPoint):
        if self._drag_index is None or self.base_pixmap is None:
            return
        width = self.base_pixmap.width()
        height = self.base_pixmap.height()
        # Constrain pos within image bounds
        x = max(0, min(pos.x(), width - 1))
        y = max(0, min(pos.y(), height - 1))
        x_norm = round(x / width, 6)
        y_norm = round(y / height, 6)
        self.pending_points[self._drag_index] = (x_norm, y_norm)
        # Update spin boxes for this point
        x_spin, y_spin = self.point_spin_boxes[self._drag_index]
        x_spin.blockSignals(True)
        y_spin.blockSignals(True)
        x_spin.setValue(x_norm)
        y_spin.setValue(y_norm)
        x_spin.blockSignals(False)
        y_spin.blockSignals(False)
        self._redraw_preview()

    def handle_drag_release(self, _pos: QPoint):
        if self._drag_index is not None:
            self._drag_index = None
            self._redraw_preview()


def main() -> None:
    """Entry point."""
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec_()


if __name__ == "__main__":
    main() 