# gui.py
"""
Minimal GUI for screenshot capture and annotation using PyQt5.

Updated flow (two-stage annotation):
1. Stage 1 – Rectangle selection: user clicks four corners of a rectangle (can drag to adjust).  Once the four
   points are chosen, press the "Next" button to advance.
2. Stage 2 – Point selection: a single point is pre-placed in the geometric centre of the rectangle.  User can
   click anywhere inside the image to reposition this point.  Finally, press "Save" to persist the annotation.

Saving now generates two entries (and, optionally, screenshot copies) in dedicated sub-folders:
* ~/Desktop/Images/rectangles/ – JSON list of rectangle annotations (annotations.json)
* ~/Desktop/Images/points/     – JSON list of point annotations      (annotations.json)

The original screenshot is still written once to ~/Desktop/Images/ but is **also** copied into the two
sub-folders so that each annotation folder is self-contained.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

from PyQt5.QtCore import Qt, QPoint, pyqtSignal
from PyQt5.QtGui import QPixmap, QPainter, QPen, QImage, QFontMetrics, QKeySequence
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
    QShortcut,
)

from adb import AdbTools  # Local module

# ---------------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------------
IMAGES_DIR = Path(os.path.expanduser("~/Desktop/Images"))
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

RECTANGLES_DIR = IMAGES_DIR / "rectangles"
POINTS_DIR = IMAGES_DIR / "points"
RECTANGLES_DIR.mkdir(parents=True, exist_ok=True)
POINTS_DIR.mkdir(parents=True, exist_ok=True)

RECT_ANNOTATIONS_PATH = RECTANGLES_DIR / "annotations.json"
POINT_ANNOTATIONS_PATH = POINTS_DIR / "annotations.json"

# ---------------------------------------------------------------------------


class ClickableLabel(QLabel):
    """QLabel that emits mouse interaction signals for click & drag."""

    clicked = pyqtSignal(QPoint)  # Mouse press (left button)
    dragged = pyqtSignal(QPoint)  # Mouse move while pressed
    released = pyqtSignal(QPoint)  # Mouse release

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dragging = False
        self.setMouseTracking(True)

    # Qt event overrides ----------------------------------------------------

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


# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    """Main application window implementing the two-stage annotation flow."""

    # Annotation stages
    _STAGE_RECTANGLE = 0  # User selecting four rectangle corners
    _STAGE_POINT = 1      # Single point selection inside rectangle

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Screenshot Annotator")

        # Core Adb helper
        self.adb_tools = AdbTools()

        # ------------------------------------------------------------------
        # UI – toolbar row (take screenshot)
        # ------------------------------------------------------------------
        self.take_ss_btn = QPushButton("Take Screenshot")
        self.take_ss_btn.clicked.connect(self.handle_take_screenshot)

        # ------------------------------------------------------------------
        # Image display (scrollable) – captures clicks / drags
        # ------------------------------------------------------------------
        self.image_label = ClickableLabel()
        self.image_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.image_label.clicked.connect(self.handle_image_click)
        self.image_label.dragged.connect(self.handle_drag_move)
        self.image_label.released.connect(self.handle_drag_release)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.image_label)

        # ------------------------------------------------------------------
        # Annotation control panel
        # ------------------------------------------------------------------
        annot_layout = QVBoxLayout()

        # First row – status & actions
        coords_layout = QHBoxLayout()
        self.point_count_label = QLabel("Points: 0/4")

        self.undo_btn = QPushButton("Undo")
        self.redo_btn = QPushButton("Redo")
        self.back_btn = QPushButton("← Back")
        self.next_btn = QPushButton("Next →")
        self.zoom_in_btn = QPushButton("+")
        self.zoom_out_btn = QPushButton("–")
        self.save_btn = QPushButton("Save")
        self.cancel_btn = QPushButton("Cancel")

        # Wire signals
        self.undo_btn.clicked.connect(self.handle_undo)
        self.redo_btn.clicked.connect(self.handle_redo)
        self.back_btn.clicked.connect(self.handle_back_stage)
        self.next_btn.clicked.connect(self.handle_next_stage)
        self.zoom_in_btn.clicked.connect(lambda: self._zoom(1.25))
        self.zoom_out_btn.clicked.connect(lambda: self._zoom(0.8))
        self.save_btn.clicked.connect(self.handle_save_annotation)
        self.cancel_btn.clicked.connect(self.handle_cancel_annotation)

        # Compose row
        coords_layout.addWidget(self.point_count_label)
        coords_layout.addStretch(1)
        coords_layout.addWidget(self.undo_btn)
        coords_layout.addWidget(self.redo_btn)
        coords_layout.addStretch(1)
        coords_layout.addWidget(self.back_btn)
        coords_layout.addWidget(self.next_btn)
        coords_layout.addStretch(1)
        coords_layout.addWidget(QLabel("Zoom:"))
        coords_layout.addWidget(self.zoom_out_btn)
        coords_layout.addWidget(self.zoom_in_btn)
        coords_layout.addStretch(1)
        coords_layout.addWidget(self.save_btn)
        coords_layout.addWidget(self.cancel_btn)

        annot_layout.addLayout(coords_layout)

        # Spin boxes – rectangle vs centre point
        self.point_spin_boxes: List[Tuple[QDoubleSpinBox, QDoubleSpinBox]] = []
        rect_grid = QVBoxLayout()
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
            x_spin.valueChanged.connect(lambda _v, i=idx: self.on_spin_changed(i))
            y_spin.valueChanged.connect(lambda _v, i=idx: self.on_spin_changed(i))
            row.addWidget(x_spin)
            row.addWidget(y_spin)
            rect_grid.addLayout(row)
            self.point_spin_boxes.append((x_spin, y_spin))
        self.rect_spin_container = QWidget()
        self.rect_spin_container.setLayout(rect_grid)
        annot_layout.addWidget(self.rect_spin_container)

        # Single point spin boxes (stage 2)
        center_row = QHBoxLayout()
        center_row.addWidget(QLabel("Point:"))
        self.center_x_spin = QDoubleSpinBox()
        self.center_y_spin = QDoubleSpinBox()
        for sp in (self.center_x_spin, self.center_y_spin):
            sp.setDecimals(3)
            sp.setRange(0.0, 1.0)
            sp.setSingleStep(0.001)
            sp.setEnabled(False)
        self.center_x_spin.valueChanged.connect(self.on_center_spin_changed)
        self.center_y_spin.valueChanged.connect(self.on_center_spin_changed)
        center_row.addWidget(self.center_x_spin)
        center_row.addWidget(self.center_y_spin)
        self.point_spin_container = QWidget()
        self.point_spin_container.setLayout(center_row)
        self.point_spin_container.setVisible(False)
        annot_layout.addWidget(self.point_spin_container)

        # Description box (enabled only in stage 2)
        self.desc_input = QTextEdit()
        self.desc_input.setPlaceholderText("Enter description…")
        self.desc_min_lines = 2
        self._set_desc_height(self.desc_min_lines)
        self.desc_input.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.desc_input.textChanged.connect(self.adjust_desc_height)
        self.desc_input.setEnabled(False)
        annot_layout.addWidget(self.desc_input)

        # ------------------------------------------------------------------
        # Main layout (top level)
        # ------------------------------------------------------------------
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.take_ss_btn)
        main_layout.addWidget(scroll_area)
        main_layout.addLayout(annot_layout)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        # ------------------------------------------------------------------
        # Internal state
        # ------------------------------------------------------------------
        # Screenshot data
        self.current_screenshot_path: Optional[Path] = None
        self.current_img_bytes: Optional[bytes] = None
        self.original_pixmap: Optional[QPixmap] = None  # Full-resolution
        self.base_pixmap: Optional[QPixmap] = None      # Scaled with saved dots / lines
        self.current_scale: float = 1.0

        # Annotation state
        self.stage: int = self._STAGE_RECTANGLE
        self.rectangle_points: List[tuple[float, float]] = []  # Finalised after stage 1
        self.pending_points: List[tuple[float, float]] = []    # While selecting rectangle
        self.center_point: Optional[tuple[float, float]] = None  # Stage 2 single point

        # Undo / redo (only for rectangle selection)
        self.undo_stack: List[List[tuple[float, float]]] = []
        self.redo_stack: List[List[tuple[float, float]]] = []

        # Misc trackers
        self._drag_index: Optional[int] = None
        self.last_description: str = ""
        self.last_saved_screenshot: Optional[str] = None

        # Keyboard shortcuts for zooming
        for key_seq in ("Ctrl++", "Ctrl+="):
            QShortcut(QKeySequence(key_seq), self, activated=lambda: self._zoom(1.25))
        QShortcut(QKeySequence("Ctrl+-"), self, activated=lambda: self._zoom(0.8))

        # Initially disable controls that need an image loaded
        for w in (
            self.undo_btn,
            self.redo_btn,
            self.back_btn,
            self.next_btn,
            self.save_btn,
            self.cancel_btn,
            self.zoom_in_btn,
            self.zoom_out_btn,
        ):
            w.setEnabled(False)
        self.back_btn.setVisible(False)

    # ------------------------------------------------------------------
    # Screenshot handling
    # ------------------------------------------------------------------

    def handle_take_screenshot(self):
        """Capture screenshot, save to disk & display."""
        try:
            fmt, img_bytes = self.adb_tools.take_screenshot()
        except Exception as exc:  # pylint: disable=broad-except
            QMessageBox.critical(self, "Error", f"Failed to take screenshot: {exc}")
            return

        # Store bytes in memory for deferred saving
        self.current_img_bytes = img_bytes
        self.current_screenshot_path = None  # Not yet persisted

        # Load into QPixmap
        image = QImage.fromData(img_bytes, fmt)
        pixmap_full = QPixmap.fromImage(image)
        if pixmap_full.isNull():
            QMessageBox.critical(self, "Error", "Failed to load screenshot into GUI.")
            return

        # Scale to fit 80 % of screen height
        screen_geom = QApplication.primaryScreen().availableGeometry()
        max_height = int(screen_geom.height() * 0.8)
        if pixmap_full.height() > max_height:
            scaled_pixmap = pixmap_full.scaledToHeight(max_height, Qt.SmoothTransformation)
        else:
            scaled_pixmap = pixmap_full

        self.original_pixmap = pixmap_full
        self.base_pixmap = scaled_pixmap.copy()
        self.current_scale = scaled_pixmap.width() / max(1, self.original_pixmap.width())

        # UI reset ----------------------------------------------------------
        self.image_label.setPixmap(scaled_pixmap)
        self.image_label.adjustSize()
        self.resize(scaled_pixmap.width() + 50, scaled_pixmap.height() + 120)

        # Reset annotation related state
        self._fully_reset_annotation_state()

        # Enable zoom buttons now that an image is loaded
        self.zoom_in_btn.setEnabled(True)
        self.zoom_out_btn.setEnabled(True)

    # ------------------------------------------------------------------
    # Annotation flow – stage transitions
    # ------------------------------------------------------------------

    def handle_next_stage(self):
        """Finalize rectangle & advance to point-selection stage."""
        if self.stage != self._STAGE_RECTANGLE or len(self.pending_points) != 4:
            return

        self.rectangle_points = self.pending_points.copy()
        # Compute geometric centre (average of points)
        cx = sum(p[0] for p in self.rectangle_points) / 4
        cy = sum(p[1] for p in self.rectangle_points) / 4
        self.center_point = (round(cx, 6), round(cy, 6))

        # Clear temporary list used for rectangle editing
        self.pending_points.clear()
        self.stage = self._STAGE_POINT

        self._redraw_preview()
        self._update_action_buttons()
        self._refresh_spin_containers()

    # ------------------------------------------------------------------
    def handle_back_stage(self):
        """Return to rectangle editing (stage 1)."""
        if self.stage != self._STAGE_POINT:
            return
        # Restore rectangle points
        self.pending_points = self.rectangle_points.copy()
        self.stage = self._STAGE_RECTANGLE
        self.center_point = None
        self._redraw_preview()
        self._update_spin_boxes_state()
        self._refresh_spin_containers()
        self._update_action_buttons()

    # ------------------------------------------------------------------
    # Image interaction handlers
    # ------------------------------------------------------------------

    def handle_image_click(self, pos: QPoint):
        if self.original_pixmap is None:
            return
        displayed_pixmap = self.image_label.pixmap()
        if displayed_pixmap is None:
            return

        pix_w, pix_h = displayed_pixmap.width(), displayed_pixmap.height()
        if not (0 <= pos.x() < pix_w and 0 <= pos.y() < pix_h):
            return  # Click outside image

        x_norm = pos.x() / pix_w
        y_norm = pos.y() / pix_h

        # --------------------------------------------------------------
        if self.stage == self._STAGE_RECTANGLE:
            # Already four points? start drag selection
            if len(self.pending_points) == 4:
                idx = self._get_nearest_point_index(pos)
                if idx is not None:
                    self._drag_index = idx
                    self._record_state_for_undo()
                    return

            # Reject extra points beyond four
            if len(self.pending_points) >= 4:
                return

            # Record for undo & append
            self._record_state_for_undo()
            self.pending_points.append((round(x_norm, 6), round(y_norm, 6)))
            self.redo_stack.clear()
            self._redraw_preview()
            self._update_spin_boxes_state()
            self.point_count_label.setText(f"Points: {len(self.pending_points)}/4")
            self._update_action_buttons()

        elif self.stage == self._STAGE_POINT:
            # Simply reposition the centre point
            self.center_point = (round(x_norm, 6), round(y_norm, 6))
            self._redraw_preview()
            self._update_action_buttons()

    # ------------------------------------------------------------------
    def handle_drag_move(self, pos: QPoint):
        if self.stage != self._STAGE_RECTANGLE:
            return
        if self._drag_index is None or self.base_pixmap is None:
            return
        width, height = self.base_pixmap.width(), self.base_pixmap.height()
        x = max(0, min(pos.x(), width - 1))
        y = max(0, min(pos.y(), height - 1))
        x_norm = round(x / width, 6)
        y_norm = round(y / height, 6)
        self.pending_points[self._drag_index] = (x_norm, y_norm)
        # Update spin boxes
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

    # ------------------------------------------------------------------
    # Saving / cancelling
    # ------------------------------------------------------------------

    def handle_save_annotation(self):
        """Persist rectangle + point annotations."""
        if self.stage != self._STAGE_POINT or self.center_point is None or len(self.rectangle_points) != 4:
            return

        desc = self.desc_input.toPlainText().strip()
        if not desc:
            QMessageBox.warning(self, "Warning", "Please enter a description.")
            return

        # ------------------------------------------------------------------
        # Ensure screenshot is saved (once) to IMAGES_DIR
        # ------------------------------------------------------------------
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

        # ------------------------------------------------------------------
        # Copy screenshot into sub-folders (ignore errors if exists)
        # ------------------------------------------------------------------
        for dest_dir in (RECTANGLES_DIR, POINTS_DIR):
            try:
                shutil.copy(self.current_screenshot_path, dest_dir / self.current_screenshot_path.name)
            except Exception:  # noqa: BLE001
                pass  # Ignore if already copied

        # ------------------------------------------------------------------
        # Build and append annotation entries
        # ------------------------------------------------------------------
        rect_entry: Dict[str, Any] = {
            "screenshot": self.current_screenshot_path.name,
            "timestamp": int(time.time()),
            "points": [{"x": x, "y": y} for x, y in self.rectangle_points],
            "description": desc,
        }
        point_entry: Dict[str, Any] = {
            "screenshot": self.current_screenshot_path.name,
            "timestamp": int(time.time()),
            "point": {"x": self.center_point[0], "y": self.center_point[1]},
            "description": desc,
        }

        self._append_annotation_to(rect_entry, RECT_ANNOTATIONS_PATH)
        self._append_annotation_to(point_entry, POINT_ANNOTATIONS_PATH)

        # Commit current preview pixmap as new base (so further edits start here)
        self.base_pixmap = self.image_label.pixmap().copy()

        # Remember last description / screenshot to warn about duplicates
        self.last_description = desc
        self.last_saved_screenshot = self.current_screenshot_path.name

        # Reset UI back to stage 0 for next annotation
        self._fully_reset_annotation_state()

    def handle_cancel_annotation(self):
        if self.base_pixmap is not None:
            self.image_label.setPixmap(self.base_pixmap)
            self.image_label.adjustSize()
        self._fully_reset_annotation_state()

    # ------------------------------------------------------------------
    # Undo / redo (only valid while selecting rectangle)
    # ------------------------------------------------------------------

    def _record_state_for_undo(self):
        if self.stage != self._STAGE_RECTANGLE:
            return
        self.undo_stack.append(self.pending_points.copy())
        if len(self.undo_stack) > 20:
            self.undo_stack.pop(0)

    def handle_undo(self):
        if self.stage != self._STAGE_RECTANGLE:
            return
        if not self.undo_stack:
            return
        self.redo_stack.append(self.pending_points.copy())
        self.pending_points = self.undo_stack.pop()
        self._restore_state_from_points()

    def handle_redo(self):
        if self.stage != self._STAGE_RECTANGLE:
            return
        if not self.redo_stack:
            return
        self.undo_stack.append(self.pending_points.copy())
        self.pending_points = self.redo_stack.pop()
        self._restore_state_from_points()

    def _restore_state_from_points(self):
        self._update_spin_boxes_state()
        self.point_count_label.setText(f"Points: {len(self.pending_points)}/4")
        self._redraw_preview()
        self._update_action_buttons()

    # ------------------------------------------------------------------
    # Spin boxes (rectangle editing only)
    # ------------------------------------------------------------------

    def on_spin_changed(self, idx: int):
        if self.stage != self._STAGE_RECTANGLE:
            return
        if idx >= len(self.pending_points):
            return
        x_val = round(self.point_spin_boxes[idx][0].value(), 6)
        y_val = round(self.point_spin_boxes[idx][1].value(), 6)
        self.pending_points[idx] = (x_val, y_val)
        self._redraw_preview()

    def on_center_spin_changed(self, _v: float):
        """Update centre point when point spin boxes change."""
        if self.stage != self._STAGE_POINT or self.center_point is None:
            return
        x_val = round(self.center_x_spin.value(), 6)
        y_val = round(self.center_y_spin.value(), 6)
        self.center_point = (x_val, y_val)
        self._redraw_preview()

    def _update_spin_boxes_state(self):
        # Enabled only during rectangle selection
        enable = self.stage == self._STAGE_RECTANGLE
        for idx, (x_spin, y_spin) in enumerate(self.point_spin_boxes):
            if enable and idx < len(self.pending_points):
                for sp, val in ((x_spin, self.pending_points[idx][0]), (y_spin, self.pending_points[idx][1])):
                    sp.blockSignals(True)
                    sp.setValue(val)
                    sp.setEnabled(True)
                    sp.blockSignals(False)
            else:
                x_spin.setEnabled(False)
                y_spin.setEnabled(False)
                x_spin.setValue(0.0)
                y_spin.setValue(0.0)

    # ------------------------------------------------------------------
    # Action button enabling logic
    # ------------------------------------------------------------------

    def _update_action_buttons(self):
        if self.stage == self._STAGE_RECTANGLE:
            self.undo_btn.setEnabled(len(self.pending_points) > 0)
            self.redo_btn.setEnabled(len(self.redo_stack) > 0)
            self.next_btn.setEnabled(len(self.pending_points) == 4)
            self.save_btn.setEnabled(False)
            # Allow typing a description at any stage of the annotation flow
            self.desc_input.setEnabled(True)
            self.cancel_btn.setEnabled(len(self.pending_points) > 0)
            self.back_btn.setVisible(False)
            self.back_btn.setEnabled(False)
        else:
            # Stage POINT
            self.undo_btn.setEnabled(False)
            self.redo_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
            self.save_btn.setEnabled(self.center_point is not None)
            self.desc_input.setEnabled(True)
            self.cancel_btn.setEnabled(True)
            self.back_btn.setVisible(True)
            self.back_btn.setEnabled(True)

    # ------------------------------------------------------------------
    def _refresh_spin_containers(self):
        """Toggle visibility & sync spin containers according to stage."""
        if self.stage == self._STAGE_RECTANGLE:
            self.rect_spin_container.setVisible(True)
            self.point_spin_container.setVisible(False)
        else:
            self.rect_spin_container.setVisible(False)
            self.point_spin_container.setVisible(True)
            if self.center_point is not None:
                self.center_x_spin.blockSignals(True)
                self.center_y_spin.blockSignals(True)
                self.center_x_spin.setValue(self.center_point[0])
                self.center_y_spin.setValue(self.center_point[1])
                self.center_x_spin.setEnabled(True)
                self.center_y_spin.setEnabled(True)
                self.center_x_spin.blockSignals(False)
                self.center_y_spin.blockSignals(False)
            else:
                self.center_x_spin.setEnabled(False)
                self.center_y_spin.setEnabled(False)

    # ------------------------------------------------------------------
    # Preview drawing
    # ------------------------------------------------------------------

    def _redraw_preview(self):
        if self.base_pixmap is None:
            return

        temp_pixmap = self.base_pixmap.copy()
        painter = QPainter(temp_pixmap)

        # --- Draw rectangle (if ready) ------------------------------------
        if self.stage == self._STAGE_RECTANGLE:
            rect_pts = self.pending_points
        else:
            rect_pts = self.rectangle_points

        pen_rect = QPen(Qt.red)
        pen_rect.setWidth(4)
        painter.setPen(pen_rect)
        painter.setBrush(Qt.red)

        width, height = temp_pixmap.width(), temp_pixmap.height()
        pixel_points = [
            QPoint(int(x * width), int(y * height)) for x, y in rect_pts
        ]
        for pt in pixel_points:
            painter.drawEllipse(pt, 3, 3)
        if len(pixel_points) == 4:
            for i in range(4):
                painter.drawLine(pixel_points[i], pixel_points[(i + 1) % 4])

        # --- Draw centre point -------------------------------------------
        if self.center_point is not None:
            cx = int(self.center_point[0] * width)
            cy = int(self.center_point[1] * height)
            pen_point = QPen(Qt.blue)
            pen_point.setWidth(4)
            painter.setPen(pen_point)
            painter.setBrush(Qt.blue)
            painter.drawEllipse(QPoint(cx, cy), 4, 4)

        painter.end()
        self.image_label.setPixmap(temp_pixmap)
        self.image_label.adjustSize()

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------

    def _get_nearest_point_index(self, pos: QPoint) -> Optional[int]:
        if self.base_pixmap is None:
            return None
        width, height = self.base_pixmap.width(), self.base_pixmap.height()
        threshold = 8  # pixels
        for idx, (x_norm, y_norm) in enumerate(self.pending_points):
            px = int(x_norm * width)
            py = int(y_norm * height)
            if abs(px - pos.x()) <= threshold and abs(py - pos.y()) <= threshold:
                return idx
        return None

    def adjust_desc_height(self):
        metrics = QFontMetrics(self.desc_input.font())
        line_height = metrics.lineSpacing()
        lines = max(self.desc_input.document().blockCount(), self.desc_min_lines)
        new_height = (line_height * lines) + 10
        self.desc_input.setFixedHeight(new_height)

    def _set_desc_height(self, lines: int):
        metrics = QFontMetrics(self.desc_input.font())
        line_height = metrics.lineSpacing()
        self.desc_input.setFixedHeight((line_height * lines) + 10)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _append_annotation_to(self, entry: Dict[str, Any], target_path: Path):
        existing: List[Dict[str, Any]]
        if target_path.exists():
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError):
                existing = []
        else:
            existing = []
        existing.append(entry)
        try:
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2)
        except OSError as exc:
            QMessageBox.warning(self, "Warning", f"Failed to write annotations: {exc}")

    # ------------------------------------------------------------------
    # Zoom handling (unchanged)
    # ------------------------------------------------------------------

    def _zoom(self, factor: float):
        if self.base_pixmap is None or self.original_pixmap is None:
            return
        new_scale = self.current_scale * factor
        new_scale = max(0.2, min(new_scale, 5.0))
        if abs(new_scale - self.current_scale) < 0.001:
            return
        self.current_scale = new_scale
        target_w = int(self.original_pixmap.width() * self.current_scale)
        target_h = int(self.original_pixmap.height() * self.current_scale)
        # Rescale directly from the original, full-resolution pixmap to
        # avoid cumulative quality loss when zooming in and out repeatedly.
        self.base_pixmap = self.original_pixmap.scaled(
            target_w,
            target_h,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self._redraw_preview()
        self.image_label.adjustSize()
        self.resize(self.base_pixmap.width() + 50, self.base_pixmap.height() + 120)

    # ------------------------------------------------------------------
    # State reset helpers
    # ------------------------------------------------------------------

    def _fully_reset_annotation_state(self):
        """Return UI/control state to initial rectangle-selection stage."""
        self.stage = self._STAGE_RECTANGLE
        self.rectangle_points.clear()
        self.pending_points.clear()
        self.center_point = None
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._update_spin_boxes_state()
        self._refresh_spin_containers()
        self._update_action_buttons()
        self.point_count_label.setText("Points: 0/4")
        for w in (self.desc_input,):
            w.clear()
            w.setEnabled(True)
        self._set_desc_height(self.desc_min_lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:  # pragma: no cover
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec_()


if __name__ == "__main__":
    main()
