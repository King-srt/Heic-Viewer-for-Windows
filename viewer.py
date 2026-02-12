
import os
import sys
from collections import OrderedDict
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from PIL import ExifTags, Image, ImageOps
from PIL.ImageQt import ImageQt
from PyQt6.QtCore import QEvent, QSettings, QThread, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QImage, QKeySequence, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except Exception:
    pass

try:
    import rawpy
    RAW_AVAILABLE = True
except Exception:
    rawpy = None
    RAW_AVAILABLE = False

SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff",
    ".heic", ".heif", ".cr2", ".nef", ".arw", ".dng",
}
RAW_EXTENSIONS = {".cr2", ".nef", ".arw", ".dng"}


def _safe_ratio(value: Any) -> str:
    try:
        if isinstance(value, tuple) and len(value) == 2 and value[1]:
            return f"{value[0] / value[1]:.2f}"
        if hasattr(value, "numerator") and hasattr(value, "denominator") and value.denominator:
            return f"{value.numerator / value.denominator:.2f}"
        return str(value)
    except Exception:
        return str(value)


def _format_shutter(value: Any) -> str:
    try:
        if isinstance(value, tuple) and len(value) == 2 and value[1]:
            frac = Fraction(value[0], value[1]).limit_denominator()
            if frac.numerator < frac.denominator:
                return f"{frac.numerator}/{frac.denominator}s"
            return f"{float(frac):.2f}s"
        if hasattr(value, "numerator") and hasattr(value, "denominator") and value.denominator:
            frac = Fraction(value.numerator, value.denominator).limit_denominator()
            if frac.numerator < frac.denominator:
                return f"{frac.numerator}/{frac.denominator}s"
            return f"{float(frac):.2f}s"
        return str(value)
    except Exception:
        return str(value)


def _decode_gps(gps_info: dict[int, Any]) -> str:
    if not gps_info:
        return "-"

    gps_map = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps_info.items()}
    lat = gps_map.get("GPSLatitude")
    lat_ref = gps_map.get("GPSLatitudeRef", "N")
    lon = gps_map.get("GPSLongitude")
    lon_ref = gps_map.get("GPSLongitudeRef", "E")

    def dms_to_decimal(dms: Any, ref: str) -> float | None:
        try:
            deg = float(Fraction(dms[0][0], dms[0][1]))
            mins = float(Fraction(dms[1][0], dms[1][1]))
            secs = float(Fraction(dms[2][0], dms[2][1]))
            out = deg + mins / 60.0 + secs / 3600.0
            if ref in ("S", "W"):
                out *= -1
            return out
        except Exception:
            return None

    lat_dec = dms_to_decimal(lat, lat_ref) if lat else None
    lon_dec = dms_to_decimal(lon, lon_ref) if lon else None
    if lat_dec is None or lon_dec is None:
        return "-"
    return f"{lat_dec:.6f}, {lon_dec:.6f}"


def extract_metadata(path: str, image: Image.Image) -> tuple[dict[str, str], dict[str, str]]:
    info = {
        "filename": os.path.basename(path),
        "resolution": f"{image.size[0]}x{image.size[1]}",
        "mode": image.mode,
    }
    meta = {
        "Camera": "-",
        "ISO": "-",
        "Shutter": "-",
        "Aperture": "-",
        "Focal Length": "-",
        "Date Taken": "-",
        "GPS": "-",
    }
    try:
        exif = image.getexif()
        data = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
        meta["Camera"] = str(data.get("Model", "-"))
        meta["ISO"] = str(data.get("PhotographicSensitivity", data.get("ISOSpeedRatings", "-")))
        meta["Shutter"] = _format_shutter(data.get("ExposureTime", "-"))
        f_num = data.get("FNumber", "-")
        meta["Aperture"] = "-" if f_num == "-" else f"f/{_safe_ratio(f_num)}"
        focal = data.get("FocalLength", "-")
        meta["Focal Length"] = "-" if focal == "-" else f"{_safe_ratio(focal)} mm"
        meta["Date Taken"] = str(data.get("DateTimeOriginal", data.get("DateTime", "-")))
        meta["GPS"] = _decode_gps(data.get("GPSInfo", {}))
    except Exception:
        pass
    return info, meta


def decode_image(path: str) -> tuple[QImage, dict[str, str], dict[str, str]]:
    ext = os.path.splitext(path)[1].lower()
    if ext in RAW_EXTENSIONS:
        if not RAW_AVAILABLE:
            raise RuntimeError("RAW support requires rawpy")
        with rawpy.imread(path) as raw_file:
            arr = raw_file.postprocess(output_bps=8, use_camera_wb=True, no_auto_bright=False)
        img = Image.fromarray(arr)
        info, meta = extract_metadata(path, img)
        img = img.convert("RGBA")
    else:
        with Image.open(path) as src:
            img = ImageOps.exif_transpose(src)
            info, meta = extract_metadata(path, img)
            img = img.convert("RGBA")
    qimage = ImageQt(img).copy()
    return qimage, info, meta


@dataclass
class CachedImage:
    qimage: QImage
    info: dict[str, str]
    meta: dict[str, str]


class ImageCache:
    def __init__(self, capacity: int = 15):
        self.capacity = max(1, capacity)
        self._items: OrderedDict[str, CachedImage] = OrderedDict()

    def get(self, path: str) -> CachedImage | None:
        item = self._items.pop(path, None)
        if item is None:
            return None
        self._items[path] = item
        return item

    def put(self, path: str, item: CachedImage) -> None:
        if path in self._items:
            self._items.pop(path, None)
        self._items[path] = item
        while len(self._items) > self.capacity:
            self._items.popitem(last=False)

class ImageLoaderThread(QThread):
    loaded = pyqtSignal(int, str, object, object, object, str)

    def __init__(self, request_id: int, path: str, role: str):
        super().__init__()
        self.request_id = request_id
        self.path = path
        self.role = role

    def run(self) -> None:
        try:
            qimage, info, meta = decode_image(self.path)
            self.loaded.emit(self.request_id, self.path, qimage, info, meta, self.role)
        except Exception:
            self.loaded.emit(self.request_id, self.path, None, None, None, self.role)


class ThumbnailLoaderThread(QThread):
    thumbnail_ready = pyqtSignal(int, str, object)

    def __init__(self, token: int, files: list[str], size: tuple[int, int] = (200, 140)):
        super().__init__()
        self.token = token
        self.files = files
        self.size = size

    def run(self) -> None:
        for path in self.files:
            try:
                ext = os.path.splitext(path)[1].lower()
                if ext in RAW_EXTENSIONS and RAW_AVAILABLE:
                    with rawpy.imread(path) as raw_file:
                        arr = raw_file.postprocess(output_bps=8, use_camera_wb=True, no_auto_bright=False)
                    img = Image.fromarray(arr)
                else:
                    with Image.open(path) as src:
                        img = ImageOps.exif_transpose(src)
                img = img.convert("RGB")
                img.thumbnail(self.size, Image.Resampling.LANCZOS)
                self.thumbnail_ready.emit(self.token, path, ImageQt(img).copy())
            except Exception:
                continue


class FolderScanThread(QThread):
    scanned = pyqtSignal(int, str, object)

    def __init__(self, token: int, folder: str, selected: str | None):
        super().__init__()
        self.token = token
        self.folder = folder
        self.selected = os.path.abspath(selected) if selected else None

    def run(self) -> None:
        files: list[str] = []
        index = 0
        try:
            with os.scandir(self.folder) as entries:
                for entry in entries:
                    if entry.is_file() and os.path.splitext(entry.name)[1].lower() in SUPPORTED_EXTENSIONS:
                        files.append(os.path.abspath(entry.path))
            files.sort()
            if self.selected and self.selected in files:
                index = files.index(self.selected)
            self.scanned.emit(self.token, self.folder, {"files": files, "index": index})
        except Exception:
            self.scanned.emit(self.token, self.folder, {"files": [], "index": 0})


class MetadataPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.labels: dict[str, QLabel] = {}
        layout = QFormLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        for key in ["Camera", "ISO", "Shutter", "Aperture", "Focal Length", "Date Taken", "GPS"]:
            value = QLabel("-")
            value.setWordWrap(True)
            layout.addRow(f"{key}:", value)
            self.labels[key] = value

    def set_data(self, data: dict[str, str] | None) -> None:
        data = data or {}
        for key, label in self.labels.items():
            label.setText(str(data.get(key, "-")))


class ImageViewer(QGraphicsView):
    zoom_changed = pyqtSignal(float)

    def __init__(self):
        super().__init__()
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._item: QGraphicsPixmapItem | None = None
        self._zoom = 1.0
        self._fit_mode = True
        self._rotation = 0

    def set_image(self, qimage: QImage) -> None:
        pix = QPixmap.fromImage(qimage)
        if self._item is None:
            self._item = self._scene.addPixmap(pix)
        else:
            self._item.setPixmap(pix)
        self._item.setRotation(0)
        self._rotation = 0
        self._scene.setSceneRect(self._item.boundingRect())
        self.fit_to_view()

    def clear_view(self) -> None:
        self._scene.clear()
        self._item = None
        self._zoom = 1.0
        self._rotation = 0
        self.zoom_changed.emit(self._zoom)

    def rotate_clockwise(self) -> None:
        if not self._item:
            return
        self._rotation = (self._rotation + 90) % 360
        self._item.setTransformOriginPoint(self._item.boundingRect().center())
        self._item.setRotation(self._rotation)
        if self._fit_mode:
            self.fit_to_view()

    def fit_to_view(self) -> None:
        if not self._item:
            return
        self._fit_mode = True
        self.resetTransform()
        self.fitInView(self._item, Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom = max(0.01, self.transform().m11())
        self.zoom_changed.emit(self._zoom)

    def zoom_percent(self, percent: int) -> None:
        self.set_zoom(percent / 100.0)

    def set_zoom(self, factor: float) -> None:
        if not self._item:
            return
        self._fit_mode = False
        factor = max(0.05, min(factor, 8.0))
        self.resetTransform()
        self.scale(factor, factor)
        self._zoom = factor
        self.zoom_changed.emit(self._zoom)

    def current_zoom_text(self) -> str:
        return f"{self._zoom * 100:.0f}%"

    def wheelEvent(self, event) -> None:
        if not self._item:
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        self._fit_mode = False
        mul = 1.15 if delta > 0 else 1 / 1.15
        target = max(0.05, min(self._zoom * mul, 8.0))
        self.scale(target / self._zoom, target / self._zoom)
        self._zoom = target
        self.zoom_changed.emit(self._zoom)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fit_mode and self._item:
            self.fit_to_view()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("King Viewer - Professional Image Viewer")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.image_files: list[str] = []
        self.current_index = -1
        self.cache = ImageCache(capacity=15)
        self.current_info: dict[str, str] = {}
        self.current_meta: dict[str, str] = {}
        self._thumb_preview: dict[str, QImage] = {}
        self._thumb_index: dict[str, int] = {}
        self._inflight_loads: set[str] = set()

        self._request_id = 0
        self._scan_token = 0
        self._thumb_token = 0
        self._loaders: list[ImageLoaderThread] = []
        self.settings = QSettings("King", "KingViewer")

        self._build_ui()
        self._show_help_on_first_run()
        self._build_shortcuts()
        self._apply_theme()
        QApplication.instance().installEventFilter(self)
        self.showFullScreen()

    def _build_ui(self) -> None:
        self._build_toolbar()

        root = QWidget(self)
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root_layout.addWidget(splitter)

        self.thumbnail_list = QListWidget()
        self.thumbnail_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.thumbnail_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.thumbnail_list.setIconSize(QSize(160, 110))
        self.thumbnail_list.setMovement(QListWidget.Movement.Static)
        self.thumbnail_list.setSpacing(8)
        self.thumbnail_list.setMinimumWidth(220)
        self.thumbnail_list.itemClicked.connect(self.on_thumbnail_clicked)
        splitter.addWidget(self.thumbnail_list)

        viewer_holder = QWidget()
        viewer_layout = QHBoxLayout(viewer_holder)
        viewer_layout.setContentsMargins(0, 0, 0, 0)
        self.viewer = ImageViewer()
        self.viewer.zoom_changed.connect(self._update_status)
        viewer_layout.addWidget(self.viewer)
        splitter.addWidget(viewer_holder)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        self._build_statusbar()
        self._build_help_overlay()
        self._build_metadata_dock()

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main", self)
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)

        self.act_open_file = QAction("Open File", self)
        self.act_open_folder = QAction("Open Folder", self)
        self.act_rotate = QAction("Rotate", self)
        self.act_prev = QAction("Prev", self)
        self.act_next = QAction("Next", self)
        self.act_full = QAction("Toggle Fullscreen", self)
        self.act_help = QAction("Help", self)
        self.act_select_prev = QAction("Select Prev", self)
        self.act_select_next = QAction("Select Next", self)
        self.act_open_selected = QAction("Open Selected", self)

        self.act_open_file.triggered.connect(self.open_file)
        self.act_open_folder.triggered.connect(self.open_folder)
        self.act_rotate.triggered.connect(self.rotate_image)
        self.act_prev.triggered.connect(self.prev_image)
        self.act_next.triggered.connect(self.next_image)
        self.act_full.triggered.connect(self.toggle_fullscreen)
        self.act_help.triggered.connect(self.toggle_help)
        self.act_select_prev.triggered.connect(lambda: self._move_selection_only(-1))
        self.act_select_next.triggered.connect(lambda: self._move_selection_only(1))
        self.act_open_selected.triggered.connect(self._open_selected)

        self.act_open_file.setShortcut(QKeySequence.StandardKey.Open)
        self.act_open_folder.setShortcut(QKeySequence("Ctrl+Shift+O"))
        self.act_rotate.setShortcut(QKeySequence("R"))
        self.act_prev.setShortcuts(
            [
                QKeySequence(Qt.Key.Key_Left),
                QKeySequence(Qt.Key.Key_Home),
            ]
        )
        self.act_next.setShortcuts(
            [
                QKeySequence(Qt.Key.Key_Right),
                QKeySequence(Qt.Key.Key_End),
            ]
        )
        self.act_prev.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self.act_next.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self.act_full.setShortcut(QKeySequence("F"))
        self.act_select_prev.setShortcut(QKeySequence(Qt.Key.Key_PageUp))
        self.act_select_next.setShortcut(QKeySequence(Qt.Key.Key_PageDown))
        self.act_open_selected.setShortcuts(
            [
                QKeySequence(Qt.Key.Key_Return),
                QKeySequence(Qt.Key.Key_Enter),
                QKeySequence(Qt.Key.Key_Space),
            ]
        )
        self.act_select_prev.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self.act_select_next.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self.act_open_selected.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)

        tb.addAction(self.act_open_file)
        tb.addAction(self.act_open_folder)
        tb.addSeparator()
        tb.addAction(self.act_rotate)
        tb.addAction(self.act_prev)
        tb.addAction(self.act_next)
        tb.addSeparator()
        tb.addAction(self.act_full)
        tb.addAction(self.act_help)

    def _build_statusbar(self) -> None:
        bar = QStatusBar(self)
        self.setStatusBar(bar)
        self.lbl_file = QLabel("File: -")
        self.lbl_res = QLabel("Resolution: -")
        self.lbl_mode = QLabel("Mode: -")
        self.lbl_zoom = QLabel("Zoom: 100%")
        for w in [self.lbl_file, self.lbl_res, self.lbl_mode, self.lbl_zoom]:
            w.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
            bar.addPermanentWidget(w)

    def _build_shortcuts(self) -> None:
        # Ensure help toggle works even when focus is inside child widgets.
        self.act_help.setShortcut(QKeySequence("H"))
        self.act_help.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self.addAction(self.act_help)
        self.addAction(self.act_select_prev)
        self.addAction(self.act_select_next)
        self.addAction(self.act_open_selected)

    def _build_help_overlay(self) -> None:
        self.help_overlay = QLabel(self)
        self.help_overlay.setObjectName("helpOverlay")
        self.help_overlay.setTextFormat(Qt.TextFormat.RichText)
        self.help_overlay.setText(
            "Shortcuts<br>"
            "H: Help  T: Thumbnails  E: EXIF<br>"
            "1: Fit  2: 100%  3: 200%<br>"
            "Left/Right: Prev/Next  R: Rotate  F or Esc: Fullscreen<br>"
            "<span style='font-size: 24px; font-weight: 700; color: #4aa2ff;'>⭐⭐⭐⭐⭐</span>"
        )
        self.help_overlay.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.help_overlay.setMargin(12)
        self.help_overlay.resize(500, 120)
        self.help_overlay.move(24, 80)

        self.help_close_btn = QPushButton("X", self.help_overlay)
        self.help_close_btn.setObjectName("helpCloseBtn")
        self.help_close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.help_close_btn.setFixedSize(22, 22)
        self.help_close_btn.move(self.help_overlay.width() - 30, 8)
        self.help_close_btn.clicked.connect(self.help_overlay.hide)

        self.help_overlay.hide()

    def _show_help_on_first_run(self) -> None:
        shown_before = self.settings.value("help_shown_once", False, type=bool)
        if not shown_before:
            self.help_overlay.show()
            self.settings.setValue("help_shown_once", True)

    def _build_metadata_dock(self) -> None:
        self.meta_panel = MetadataPanel()
        self.meta_dock = QDockWidget("Metadata", self)
        self.meta_dock.setWidget(self.meta_panel)
        self.meta_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.meta_dock)
        self.meta_dock.hide()

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #15171b; color: #e7e7e7; }
            QToolBar { background: #1b1e24; border: none; spacing: 6px; padding: 6px; }
            QToolButton { background: #242933; border: 1px solid #313744; padding: 6px 10px; border-radius: 6px; }
            QToolButton:hover { background: #2e3645; }
            QStatusBar { background: #111318; border-top: 1px solid #2a2f38; }
            QListWidget { background: #111318; border-right: 1px solid #2a2f38; }
            QListWidget::item { border: 1px solid transparent; padding: 4px; }
            QListWidget::item:selected { border: 1px solid #4aa2ff; background: #1d2633; }
            QDockWidget::title { background: #1b1e24; text-align: left; padding-left: 8px; }
            QLabel#helpOverlay { background: rgba(20, 24, 32, 220); border: 1px solid #3b4456; border-radius: 8px; }
            QPushButton#helpCloseBtn {
                background: #1f7cff;
                color: #ffffff;
                border: none;
                border-radius: 11px;
                font-weight: 700;
            }
            QPushButton#helpCloseBtn:hover { background: #3990ff; }
            """
        )

    def open_file(self) -> None:
        filt = "Images (*.jpg *.jpeg *.png *.bmp *.gif *.webp *.tif *.tiff *.heic *.heif *.cr2 *.nef *.arw *.dng)"
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Image", "", filt)
        if not file_path:
            return
        selected = os.path.abspath(file_path)
        self._scan_folder(os.path.dirname(selected), selected)

    def open_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Open Folder")
        if folder:
            self._scan_folder(os.path.abspath(folder), None)

    def _scan_folder(self, folder: str, selected: str | None) -> None:
        self.statusBar().showMessage("Scanning folder...", 1500)
        self._scan_token += 1
        token = self._scan_token
        self.scan_thread = FolderScanThread(token, folder, selected)
        self.scan_thread.scanned.connect(self._on_scanned)
        self.scan_thread.start()

    def _on_scanned(self, token: int, folder: str, payload: dict[str, Any]) -> None:
        if token != self._scan_token:
            return
        files = payload.get("files", [])
        index = payload.get("index", 0)
        if not files:
            QMessageBox.information(self, "King Viewer", "No supported images found in this folder.")
            return

        self.image_files = files
        self._thumb_preview.clear()
        self._thumb_index = {path: idx for idx, path in enumerate(self.image_files)}
        self.current_index = max(0, min(index, len(files) - 1))
        self._populate_thumbnails()
        self._start_thumbnail_loader()
        self.load_current()

    def _populate_thumbnails(self) -> None:
        self.thumbnail_list.clear()
        placeholder = self.style().standardIcon(self.style().StandardPixmap.SP_FileIcon)
        self._thumb_index = {path: idx for idx, path in enumerate(self.image_files)}
        for path in self.image_files:
            item = QListWidgetItem(placeholder, os.path.basename(path))
            item.setToolTip(path)
            self.thumbnail_list.addItem(item)
        if 0 <= self.current_index < self.thumbnail_list.count():
            self.thumbnail_list.setCurrentRow(self.current_index)

    def _start_thumbnail_loader(self) -> None:
        self._thumb_token += 1
        token = self._thumb_token
        self.thumb_thread = ThumbnailLoaderThread(token, self.image_files)
        self.thumb_thread.thumbnail_ready.connect(self._on_thumbnail_ready)
        self.thumb_thread.start()

    def _on_thumbnail_ready(self, token: int, path: str, qimage: QImage) -> None:
        if token != self._thumb_token:
            return
        self._thumb_preview[path] = qimage
        idx = self._thumb_index.get(path)
        if idx is None:
            return
        item = self.thumbnail_list.item(idx)
        if item is None:
            return
        item.setIcon(QIcon(QPixmap.fromImage(qimage)))

    def on_thumbnail_clicked(self, item: QListWidgetItem) -> None:
        row = self.thumbnail_list.row(item)
        if 0 <= row < len(self.image_files):
            self.current_index = row
            self.load_current()

    def rotate_image(self) -> None:
        self.viewer.rotate_clockwise()
        self._update_status()

    def next_image(self) -> None:
        if not self.image_files:
            return
        self.current_index = (self.current_index + 1) % len(self.image_files)
        self.load_current()

    def prev_image(self) -> None:
        if not self.image_files:
            return
        self.current_index = (self.current_index - 1) % len(self.image_files)
        self.load_current()

    def _move_selection_only(self, step: int) -> None:
        if not self.image_files:
            return
        self.current_index = (self.current_index + step) % len(self.image_files)
        self._sync_thumb_selection()
        name = os.path.basename(self.image_files[self.current_index])
        self.statusBar().showMessage(
            f"Selected {self.current_index + 1}/{len(self.image_files)}: {name} (Press Enter/Space to display)",
            1800,
        )

    def _open_selected(self) -> None:
        if not self.image_files:
            return
        row = self.thumbnail_list.currentRow()
        if 0 <= row < len(self.image_files):
            self.current_index = row
        self.load_current()

    def load_current(self) -> None:
        if not (0 <= self.current_index < len(self.image_files)):
            return
        path = self.image_files[self.current_index]
        cached = self.cache.get(path)
        if cached:
            self._display(path, cached)
        else:
            preview = self._thumb_preview.get(path)
            if preview is not None:
                self.viewer.set_image(preview)
                self.current_info = {"filename": os.path.basename(path), "resolution": "Preview", "mode": "RGB"}
                self.current_meta = {}
                self.meta_panel.set_data(None)
                self._update_status()
            self._request_load(path, "main")
            self.statusBar().showMessage("Loading image...", 1200)
        self._sync_thumb_selection()
        self._preload_neighbors()

    def _display(self, path: str, cached: CachedImage) -> None:
        self.viewer.set_image(cached.qimage)
        self.current_info = cached.info
        self.current_meta = cached.meta
        self.meta_panel.set_data(self.current_meta)
        self._update_status()
        self.setWindowTitle(
            f"King Viewer - Professional Image Viewer  [{self.current_index + 1}/{len(self.image_files)}]  {os.path.basename(path)}"
        )

    def _request_load(self, path: str, role: str) -> int | None:
        if path in self._inflight_loads:
            return None
        self._request_id += 1
        req = self._request_id
        thread = ImageLoaderThread(req, path, role)
        thread.loaded.connect(self._on_loaded)
        thread.finished.connect(lambda: self._drop_loader(thread))
        self._inflight_loads.add(path)
        self._loaders.append(thread)
        thread.start()
        return req

    def _drop_loader(self, thread: ImageLoaderThread) -> None:
        self._inflight_loads.discard(thread.path)
        if thread in self._loaders:
            self._loaders.remove(thread)
        thread.deleteLater()

    def _on_loaded(
        self,
        request_id: int,
        path: str,
        qimage: QImage | None,
        info: dict[str, str] | None,
        meta: dict[str, str] | None,
        role: str,
    ) -> None:
        if qimage is None or info is None or meta is None:
            cur_path = self.image_files[self.current_index] if self.image_files and self.current_index >= 0 else None
            if path == cur_path:
                self.statusBar().showMessage(f"Failed to load: {os.path.basename(path)}", 3000)
                self._skip_corrupted_current()
            return

        cached = CachedImage(qimage=qimage, info=info, meta=meta)
        self.cache.put(path, cached)

        cur_path = self.image_files[self.current_index] if self.image_files and self.current_index >= 0 else None
        if path == cur_path:
            self._display(path, cached)

    def _skip_corrupted_current(self) -> None:
        if not self.image_files:
            self.viewer.clear_view()
            return
        if len(self.image_files) == 1:
            self.viewer.clear_view()
            return
        bad = self.image_files.pop(self.current_index)
        self.statusBar().showMessage(f"Skipped corrupted file: {os.path.basename(bad)}", 3000)
        if self.current_index >= len(self.image_files):
            self.current_index = len(self.image_files) - 1
        self._populate_thumbnails()
        self.load_current()

    def _preload_neighbors(self) -> None:
        if not self.image_files:
            return
        for off in (-1, 1):
            idx = self.current_index + off
            if 0 <= idx < len(self.image_files):
                path = self.image_files[idx]
                if self.cache.get(path) is None:
                    self._request_load(path, "preload")

    def _sync_thumb_selection(self) -> None:
        if 0 <= self.current_index < self.thumbnail_list.count():
            self.thumbnail_list.blockSignals(True)
            self.thumbnail_list.setCurrentRow(self.current_index)
            self.thumbnail_list.scrollToItem(self.thumbnail_list.item(self.current_index))
            self.thumbnail_list.blockSignals(False)

    def _update_status(self, *_args) -> None:
        self.lbl_file.setText(f"File: {self.current_info.get('filename', '-')}")
        self.lbl_res.setText(f"Resolution: {self.current_info.get('resolution', '-')}")
        self.lbl_mode.setText(f"Mode: {self.current_info.get('mode', '-')}")
        self.lbl_zoom.setText(f"Zoom: {self.viewer.current_zoom_text()}")

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showMaximized()
        else:
            self.showFullScreen()

    def toggle_help(self) -> None:
        self.help_overlay.setVisible(not self.help_overlay.isVisible())

    def toggle_thumbnails(self) -> None:
        self.thumbnail_list.setVisible(not self.thumbnail_list.isVisible())

    def toggle_metadata(self) -> None:
        self.meta_dock.setVisible(not self.meta_dock.isVisible())

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Right, Qt.Key.Key_End):
            self.next_image()
            return
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Home):
            self.prev_image()
            return
        if key == Qt.Key.Key_R:
            self.rotate_image()
            return
        if key == Qt.Key.Key_1:
            self.viewer.fit_to_view()
            return
        if key == Qt.Key.Key_2:
            self.viewer.zoom_percent(100)
            return
        if key == Qt.Key.Key_3:
            self.viewer.zoom_percent(200)
            return
        if key == Qt.Key.Key_H:
            self.toggle_help()
            return
        if key == Qt.Key.Key_T:
            self.toggle_thumbnails()
            return
        if key == Qt.Key.Key_E:
            self.toggle_metadata()
            return
        if key in (Qt.Key.Key_F, Qt.Key.Key_Escape):
            self.toggle_fullscreen()
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_End,):
                self.next_image()
                return True
            if key in (Qt.Key.Key_Home,):
                self.prev_image()
                return True
        return super().eventFilter(obj, event)


def main() -> None:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
