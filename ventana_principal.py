import cv2
import math
import os
import tempfile
from pathlib import Path
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QSplitter, QListWidget, 
                             QListWidgetItem, QGraphicsScene, QScrollArea, 
                             QFileDialog, QMessageBox, QMenu)
from PyQt6.QtGui import QPixmap, QImage, QPainter, QPainterPath, QColor, QPen, QKeySequence, QShortcut
from PyQt6.QtCore import Qt, QRect, QTimer, QRectF, QThread, pyqtSignal

from motor_vision import DetectorFotos, cv2_to_qimage, ordenar_natural
from motor_escaner import MotorEscaner
from ui_components import ZoomView, CajaRecorteInteractiva, VistaPreviaWidget, PantallaCarga, DialogoEscaner

class TareaDeteccion(QThread):
    terminado = pyqtSignal(list, object)
    def __init__(self, ruta):
        super().__init__()
        self.ruta = ruta
    def run(self):
        rects, img = DetectorFotos.detectar(self.ruta, margen_recorte=18)
        self.terminado.emit(rects, img)

class TareaCargarImagen(QThread):
    terminado = pyqtSignal(object, object) 
    def __init__(self, ruta):
        super().__init__()
        self.ruta = ruta
    def run(self):
        img = cv2.imread(self.ruta)
        qimg = cv2_to_qimage(img) 
        self.terminado.emit(img, qimg)

class TareaEscanear(QThread):
    terminado = pyqtSignal(object, object)
    error = pyqtSignal(str)
    progreso = pyqtSignal(int)
    
    def __init__(self, config, overlay):
        super().__init__()
        self.config = config
        self.overlay = overlay
        
    def run(self):
        # Simulación de progreso de Hardware WIA
        for i in range(1, 101):
            if self.overlay.cancelado:
                self.error.emit("Cancelado por el usuario.")
                return
            self.progreso.emit(i)
            self.msleep(20) 
            
        try:
            img_cv = MotorEscaner.escanear(self.config['device_id'], dpi=self.config['dpi'], modo_color=self.config['modo_color'])
            qimg = cv2_to_qimage(img_cv)
            self.terminado.emit(img_cv, qimg)
        except Exception as e:
            self.error.emit(str(e))

class TareaGuardar(QThread):
    terminado = pyqtSignal(int)
    def __init__(self, datos_cajas, img_cv, dir_destino, nombre_base):
        super().__init__()
        self.datos_cajas = datos_cajas
        self.img_cv = img_cv
        self.dir_destino = dir_destino
        self.nombre_base = nombre_base
        
    def run(self):
        contador = 1
        for box in self.datos_cajas:
            cx, cy, w, h, angle, rot_out = box['cx'], box['cy'], box['w'], box['h'], box['angle'], box['rot_out']
            pad = int(math.hypot(w, h) / 2) + 20
            padded_img = cv2.copyMakeBorder(self.img_cv, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=[0, 0, 0])
            cx_pad, cy_pad = cx + pad, cy + pad
            M = cv2.getRotationMatrix2D((cx_pad, cy_pad), angle, 1.0)
            rotated_img = cv2.warpAffine(padded_img, M, (padded_img.shape[1], padded_img.shape[0]), flags=cv2.INTER_CUBIC)
            recorte = cv2.getRectSubPix(rotated_img, (int(w), int(h)), (cx_pad, cy_pad))
            
            if rot_out == 90: recorte = cv2.rotate(recorte, cv2.ROTATE_90_CLOCKWISE)
            elif rot_out == 180: recorte = cv2.rotate(recorte, cv2.ROTATE_180)
            elif rot_out == 270: recorte = cv2.rotate(recorte, cv2.ROTATE_90_COUNTERCLOCKWISE)
                
            ruta = f"{self.dir_destino}/{self.nombre_base}_foto{contador}.jpg"
            cv2.imwrite(ruta, recorte)
            contador += 1
        self.terminado.emit(contador - 1)

class EscanerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PhotoScan Pro")
        self.setGeometry(50, 50, 1400, 800)
        
        self.ruta_imagen_actual = None
        self.imagen_opencv_actual = None
        self.pixmap_cached = None 
        self.recuadros = []
        self.directorio_guardado_predeterminado = None
        
        self.contador_escaneos = 1 # Para nombres incrementales
        self.undo_stack = []
        self.redo_stack = []
        
        self.initUI()
        self.aplicar_estilos()
        self.overlay_carga = PantallaCarga(self)
        
        QShortcut(QKeySequence("Ctrl+Z"), self).activated.connect(self.deshacer)
        QShortcut(QKeySequence("Ctrl+Y"), self).activated.connect(self.rehacer)
        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'overlay_carga'):
            px = (self.width() - self.overlay_carga.width()) // 2
            py = (self.height() - self.overlay_carga.height()) // 2
            self.overlay_carga.move(px, py)

    def aplicar_estilos(self):
        ruta_css = Path(__file__).parent / "estilos.qss"
        if ruta_css.exists():
            with open(ruta_css, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    def initUI(self):
        self.panel_izquierdo = QWidget()
        self.panel_izquierdo.setObjectName("panel_lateral")
        layout_izq = QVBoxLayout(self.panel_izquierdo)
        
        btn_archivo = QPushButton("📄 Archivo")
        btn_archivo.setObjectName("btn_primario")
        menu_archivo = QMenu(self)
        menu_archivo.addAction("📁 Cargar Carpeta...").triggered.connect(self.seleccionar_carpeta_origen)
        menu_archivo.addAction("📄 Cargar Archivo(s)...").triggered.connect(self.seleccionar_archivos_origen)
        btn_archivo.setMenu(menu_archivo)
        
        btn_escanear = QPushButton("🖨️ Escanear")
        btn_escanear.setObjectName("btn_primario")
        btn_escanear.clicked.connect(self.abrir_ventana_escaner)
        
        layout_izq.addWidget(btn_archivo)
        layout_izq.addWidget(btn_escanear)
        
        row_orden = QHBoxLayout()
        row_orden.addWidget(QLabel("Imágenes:"))
        btn_ordenar = QPushButton("↕️ Ordenar")
        btn_ordenar.setObjectName("btn_secundario")
        menu_orden = QMenu(self)
        menu_orden.addAction("Nombre (A-Z)").triggered.connect(lambda: self.ordenar_lista("nombre_asc"))
        menu_orden.addAction("Nombre (Z-A)").triggered.connect(lambda: self.ordenar_lista("nombre_desc"))
        menu_orden.addAction("Fecha (Más reciente)").triggered.connect(lambda: self.ordenar_lista("fecha_desc"))
        menu_orden.addAction("Fecha (Más antiguo)").triggered.connect(lambda: self.ordenar_lista("fecha_asc"))
        btn_ordenar.setMenu(menu_orden)
        row_orden.addWidget(btn_ordenar)
        
        layout_izq.addLayout(row_orden)
        
        self.lista_archivos = QListWidget()
        self.lista_archivos.itemClicked.connect(self.cargar_desde_lista)
        self.lista_archivos.itemChanged.connect(self._on_item_renombrado) # F2 Renombrar
        layout_izq.addWidget(self.lista_archivos)

        zona_central = QWidget()
        layout_central = QVBoxLayout(zona_central)
        layout_central.setContentsMargins(0, 0, 0, 0)
        
        toolbar_superior = QWidget()
        toolbar_superior.setObjectName("toolbar_superior")
        layout_tb = QHBoxLayout(toolbar_superior)
        layout_tb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        btn_detectar = QPushButton("🔍 Auto-Detectar")
        btn_detectar.setObjectName("btn_herramienta")
        btn_detectar.clicked.connect(self.ejecutar_deteccion)
        
        btn_manual = QPushButton("➕ Agregar")
        btn_manual.setObjectName("btn_herramienta")
        btn_manual.clicked.connect(self.agregar_recuadro_manual)
        
        btn_eliminar = QPushButton("🗑️ Eliminar (Supr)")
        btn_eliminar.setObjectName("btn_herramienta")
        btn_eliminar.clicked.connect(self.eliminar_recuadro_seleccionado)
        
        btn_deshacer = QPushButton("↩️ Deshacer")
        btn_deshacer.setObjectName("btn_herramienta")
        btn_deshacer.clicked.connect(self.deshacer)
        
        btn_rehacer = QPushButton("↪️ Rehacer")
        btn_rehacer.setObjectName("btn_herramienta")
        btn_rehacer.clicked.connect(self.rehacer)
        
        layout_tb.addWidget(btn_detectar)
        layout_tb.addWidget(btn_manual)
        layout_tb.addWidget(btn_eliminar)
        layout_tb.addWidget(btn_deshacer)
        layout_tb.addWidget(btn_rehacer)
        
        self.scene = QGraphicsScene()
        self.view = ZoomView(self.scene)
        self.lupa_widget = QLabel(self.view)
        self.lupa_widget.setFixedSize(160, 160)
        self.lupa_widget.hide()
        
        layout_central.addWidget(toolbar_superior)
        layout_central.addWidget(self.view)
        
        self.panel_derecho = QWidget()
        self.panel_derecho.setObjectName("panel_lateral")
        layout_der = QVBoxLayout(self.panel_derecho)
        
        self.lbl_ruta_guardado = QLabel("Guardar en:\n[No seleccionado]")
        self.lbl_ruta_guardado.setWordWrap(True)
        btn_set_ruta = QPushButton("Configurar Carpeta...")
        btn_set_ruta.clicked.connect(self.configurar_ruta_guardado)
        
        self.scroll_previas = QScrollArea()
        self.scroll_previas.setWidgetResizable(True)
        self.contenedor_previas = QWidget()
        self.layout_previas = QVBoxLayout(self.contenedor_previas)
        self.layout_previas.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_previas.setWidget(self.contenedor_previas)

        btn_extraer = QPushButton("✅ Guardar Fotos")
        btn_extraer.setObjectName("btn_guardar")
        btn_extraer.clicked.connect(self.guardar_con_carga)
        
        layout_der.addWidget(QLabel("Vista Previa (Corte Final):"))
        layout_der.addWidget(self.scroll_previas)
        
        ruta_layout = QHBoxLayout()
        ruta_layout.addWidget(btn_set_ruta)
        ruta_layout.addWidget(self.lbl_ruta_guardado)
        layout_der.addLayout(ruta_layout)
        layout_der.addWidget(btn_extraer)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.panel_izquierdo)
        splitter.addWidget(zona_central)
        splitter.addWidget(self.panel_derecho)
        splitter.setSizes([240, 800, 360]) 
        self.setCentralWidget(splitter)

    # --- ORDENAMIENTO DE LISTA ---
    def ordenar_lista(self, criterio):
        items = []
        for i in range(self.lista_archivos.count()):
            item = self.lista_archivos.item(i)
            ruta = item.data(Qt.ItemDataRole.UserRole)
            fecha = os.path.getmtime(ruta) if ruta and os.path.exists(ruta) else 0
            items.append({'nombre': item.text(), 'fecha': fecha, 'ruta': ruta})

        if criterio == "nombre_asc": items.sort(key=lambda x: x['nombre'].lower())
        elif criterio == "nombre_desc": items.sort(key=lambda x: x['nombre'].lower(), reverse=True)
        elif criterio == "fecha_desc": items.sort(key=lambda x: x['fecha'], reverse=True)
        elif criterio == "fecha_asc": items.sort(key=lambda x: x['fecha'])

        self.lista_archivos.clear()
        for d in items:
            new_item = QListWidgetItem(d['nombre'])
            new_item.setData(Qt.ItemDataRole.UserRole, d['ruta'])
            new_item.setFlags(new_item.flags() | Qt.ItemFlag.ItemIsEditable) # Permite F2
            self.lista_archivos.addItem(new_item)

    # --- RENOMBRAR (F2) ---
    def _on_item_renombrado(self, item):
        ruta_antigua = item.data(Qt.ItemDataRole.UserRole)
        if not ruta_antigua: return
        ruta_antigua_path = Path(ruta_antigua)
        nuevo_nombre = item.text()
        
        if ruta_antigua_path.name != nuevo_nombre:
            nueva_ruta = ruta_antigua_path.parent / nuevo_nombre
            try:
                os.rename(ruta_antigua, nueva_ruta)
                item.setData(Qt.ItemDataRole.UserRole, str(nueva_ruta))
                if self.ruta_imagen_actual == ruta_antigua:
                    self.ruta_imagen_actual = str(nueva_ruta)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"No se pudo renombrar: {e}")
                item.setText(ruta_antigua_path.name) 

    # --- ESCANEO FÍSICO ---
    def abrir_ventana_escaner(self):
        self.overlay_carga.mostrar("Buscando escáneres...")
        QTimer.singleShot(100, self._procesar_ventana_escaner)

    def _procesar_ventana_escaner(self):
        escaneres = MotorEscaner.listar_escaneres()
        self.overlay_carga.ocultar()
        
        dialogo = DialogoEscaner(escaneres, self)
        if dialogo.exec():
            config = dialogo.obtener_configuracion()
            self.overlay_carga.mostrar(f"Escaneando a {config['dpi']} PPP...", modo_progreso=True)
            
            self.thread_escaner = TareaEscanear(config, self.overlay_carga)
            self.thread_escaner.progreso.connect(self.overlay_carga.actualizar_progreso)
            self.thread_escaner.terminado.connect(self._on_escaneo_terminado)
            self.thread_escaner.error.connect(self._on_escaneo_error)
            self.thread_escaner.start()
            
    def _on_escaneo_terminado(self, img_cv, qimg):
        # FIX DE CRASHEO 2: Guardamos en un temporal físico para que OpenCV pueda leerlo luego
        temp_dir = tempfile.gettempdir()
        nombre_archivo = f"Escaneo_{self.contador_escaneos:02d}.bmp"
        file_path = os.path.join(temp_dir, nombre_archivo)
        cv2.imwrite(file_path, img_cv)
        
        item = QListWidgetItem(nombre_archivo)
        item.setData(Qt.ItemDataRole.UserRole, file_path)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable) # Permite F2
        
        self.lista_archivos.addItem(item)
        self.lista_archivos.setCurrentItem(item)
        self.contador_escaneos += 1
        
        self._on_imagen_cargada(img_cv, qimg)
        
    def _on_escaneo_error(self, mensaje):
        self.overlay_carga.ocultar()
        if "Cancelado" not in mensaje:
            QMessageBox.critical(self, "Error", f"Falló el escaneo:\n{mensaje}")

    # --- HISTORIAL DESHACER / REHACER ---
    def guardar_estado(self):
        estado = []
        for box in self.recuadros:
            estado.append({'cx': box.pos().x(), 'cy': box.pos().y(), 'w': box.rect().width(), 'h': box.rect().height(), 'angle': box.rotation(), 'rot_out': box.rotacion_salida})
        self.undo_stack.append(estado)
        if len(self.undo_stack) > 50: self.undo_stack.pop(0) 
        self.redo_stack.clear()

    def _obtener_estado_actual(self):
        return [{'cx': b.pos().x(), 'cy': b.pos().y(), 'w': b.rect().width(), 'h': b.rect().height(), 'angle': b.rotation(), 'rot_out': b.rotacion_salida} for b in self.recuadros]

    def deshacer(self):
        if not self.undo_stack: return
        self.redo_stack.append(self._obtener_estado_actual())
        estado_anterior = self.undo_stack.pop()
        self._aplicar_estado(estado_anterior)

    def rehacer(self):
        if not self.redo_stack: return
        self.undo_stack.append(self._obtener_estado_actual())
        estado_siguiente = self.redo_stack.pop()
        self._aplicar_estado(estado_siguiente)

    def _aplicar_estado(self, estado):
        self.limpiar_recuadros_sin_guardar()
        for data in estado:
            box = CajaRecorteInteractiva(data['cx'], data['cy'], data['w'], data['h'], data['angle'], self.generar_vistas_previas, self.actualizar_lupa, self.guardar_estado)
            box.rotacion_salida = data['rot_out']
            self.scene.addItem(box)
            self.recuadros.append(box)
        self.generar_vistas_previas()

    # --- LUPA ---
    def actualizar_lupa(self, scene_pos, show):
        if not show or self.pixmap_cached is None or scene_pos is None:
            self.lupa_widget.hide()
            return
            
        x, y = int(scene_pos.x()), int(scene_pos.y())
        rect_ext = QRect(x - 30, y - 30, 60, 60)
        patch = self.pixmap_cached.copy(rect_ext)
        if patch.isNull(): return
        
        patch_zoomed = patch.scaled(180, 180, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
        target = QPixmap(160, 160)
        target.fill(Qt.GlobalColor.transparent)
        painter = QPainter(target)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        path = QPainterPath()
        path.addEllipse(5, 5, 150, 150)
        painter.setClipPath(path)
        painter.drawPixmap(-10, -10, patch_zoomed)
        
        painter.setPen(QPen(QColor(0, 255, 0), 2))
        painter.drawLine(80, 70, 80, 90)
        painter.drawLine(70, 80, 90, 80)
        
        painter.setClipping(False)
        painter.setPen(QPen(QColor("#00A2ED"), 4))
        painter.drawEllipse(5, 5, 150, 150)
        painter.end()
        
        self.lupa_widget.setPixmap(target)
        view_pos = self.view.mapFromScene(scene_pos)
        self.lupa_widget.move(view_pos.x() + 30, view_pos.y() + 30)
        self.lupa_widget.show()

    # --- ARCHIVOS ---
    def seleccionar_carpeta_origen(self):
        directorio = QFileDialog.getExistingDirectory(self, "Selecciona Carpeta")
        if directorio:
            self.overlay_carga.mostrar("Cargando carpeta...")
            QTimer.singleShot(50, lambda: self._procesar_archivos(list(Path(directorio).glob("*.[pj][np][g]*")) + list(Path(directorio).glob("*.BMP"))))

    def seleccionar_archivos_origen(self):
        archivos, _ = QFileDialog.getOpenFileNames(self, "Selecciona Archivos", "", "Imágenes (*.png *.jpg *.jpeg *.bmp)")
        if archivos:
            self.overlay_carga.mostrar("Cargando imágenes...")
            QTimer.singleShot(50, lambda: self._procesar_archivos([Path(a) for a in archivos]))

    def _procesar_archivos(self, archivos_path):
        self.lista_archivos.clear()
        archivos_path.sort(key=ordenar_natural)
        for archivo in archivos_path:
            item = QListWidgetItem(archivo.name)
            item.setData(Qt.ItemDataRole.UserRole, str(archivo))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.lista_archivos.addItem(item)
        self.overlay_carga.ocultar()

    def configurar_ruta_guardado(self):
        dir_destino = QFileDialog.getExistingDirectory(self, "Carpeta de Guardado")
        if dir_destino:
            self.directorio_guardado_predeterminado = dir_destino
            self.lbl_ruta_guardado.setText(f"Guardar en:\n{Path(dir_destino).name}")

    def cargar_desde_lista(self, item):
        ruta = item.data(Qt.ItemDataRole.UserRole)
        self.ruta_imagen_actual = ruta
        self.overlay_carga.mostrar("Cargando escaneo...")
        
        self.thread_cargar = TareaCargarImagen(ruta)
        self.thread_cargar.terminado.connect(self._on_imagen_cargada)
        self.thread_cargar.start()
        
    def _on_imagen_cargada(self, img_cv, qimg):
        # FIX DE CRASHEO 1: Vaciamos python primero y luego QScene
        self.limpiar_recuadros_sin_guardar()
        self.scene.clear()
        self.undo_stack.clear()
        self.redo_stack.clear()
        
        self.imagen_opencv_actual = img_cv
        self.pixmap_cached = QPixmap.fromImage(qimg)
        self.scene.addPixmap(self.pixmap_cached)
        self.scene.setSceneRect(QRectF(self.pixmap_cached.rect()))
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.overlay_carga.ocultar()

    # --- RECUADROS ---
    def ejecutar_deteccion(self):
        if not self.ruta_imagen_actual: return
        self.guardar_estado()
        self.overlay_carga.mostrar("Auto-Detectando Fotos...")
        
        self.thread_det = TareaDeteccion(self.ruta_imagen_actual)
        self.thread_det.terminado.connect(self._on_deteccion_terminada)
        self.thread_det.start()

    def _on_deteccion_terminada(self, rects, img_cv):
        self.imagen_opencv_actual = img_cv
        self.limpiar_recuadros_sin_guardar()
        for r in rects:
            box = CajaRecorteInteractiva(r['cx'], r['cy'], r['w'], r['h'], r['angle'], self.generar_vistas_previas, self.actualizar_lupa, self.guardar_estado)
            self.scene.addItem(box)
            self.recuadros.append(box)
        self.generar_vistas_previas()
        self.overlay_carga.ocultar()
        
    def agregar_recuadro_manual(self):
        if not self.ruta_imagen_actual: return
        self.guardar_estado()
        img_h, img_w = self.imagen_opencv_actual.shape[:2]
        cx, cy = img_w / 2, img_h / 2
        w, h = min(500, img_w * 0.4), min(500, img_h * 0.4)
        box = CajaRecorteInteractiva(cx, cy, w, h, 0, self.generar_vistas_previas, self.actualizar_lupa, self.guardar_estado)
        self.scene.addItem(box)
        self.scene.clearSelection()
        box.setSelected(True)
        self.recuadros.append(box)
        self.generar_vistas_previas()

    def eliminar_recuadro_seleccionado(self):
        items = self.scene.selectedItems()
        if not items: return
        self.guardar_estado()
        for item in items:
            if isinstance(item, CajaRecorteInteractiva):
                self.scene.removeItem(item)
                if item in self.recuadros: self.recuadros.remove(item)
        self.generar_vistas_previas()

    def limpiar_recuadros_sin_guardar(self):
        for box in self.recuadros:
            if box.scene() == self.scene:
                self.scene.removeItem(box)
        self.recuadros.clear()
        for i in reversed(range(self.layout_previas.count())): 
            widget = self.layout_previas.itemAt(i).widget()
            if widget: widget.deleteLater()

    def extraer_recorte_cv2(self, box):
        cx, cy = box.pos().x(), box.pos().y()
        w, h = box.rect().width(), box.rect().height()
        angle = box.rotation()
        size = int(math.hypot(w, h)) + 4 
        parche_pequeno = cv2.getRectSubPix(self.imagen_opencv_actual, (size, size), (cx, cy))
        centro_parche = (size / 2, size / 2)
        M = cv2.getRotationMatrix2D(centro_parche, angle, 1.0)
        parche_rotado = cv2.warpAffine(parche_pequeno, M, (size, size), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=[0,0,0])
        recorte = cv2.getRectSubPix(parche_rotado, (int(w), int(h)), centro_parche)
        
        if box.rotacion_salida == 90: recorte = cv2.rotate(recorte, cv2.ROTATE_90_CLOCKWISE)
        elif box.rotacion_salida == 180: recorte = cv2.rotate(recorte, cv2.ROTATE_180)
        elif box.rotacion_salida == 270: recorte = cv2.rotate(recorte, cv2.ROTATE_90_COUNTERCLOCKWISE)
            
        return recorte

    def generar_vistas_previas(self):
        if self.imagen_opencv_actual is None: return
        for i in reversed(range(self.layout_previas.count())): 
            widget = self.layout_previas.itemAt(i).widget()
            if widget: widget.deleteLater()
            
        for idx, box in enumerate(self.recuadros):
            try:
                recorte_cv = self.extraer_recorte_cv2(box)
                rgb_image = cv2.cvtColor(recorte_cv, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_image.shape
                qimg = QImage(rgb_image.data, w, h, ch * w, QImage.Format.Format_RGB888)
                pixmap = QPixmap.fromImage(qimg)
                
                widget_previa = VistaPreviaWidget(pixmap, idx + 1, box, self.guardar_estado)
                self.layout_previas.addWidget(widget_previa)
            except: pass

    def guardar_con_carga(self):
        if not self.recuadros: return
        if not self.directorio_guardado_predeterminado:
            self.configurar_ruta_guardado()
            if not self.directorio_guardado_predeterminado: return
            
        self.overlay_carga.mostrar("Guardando Fotos...")
        
        datos = []
        for box in self.recuadros:
            datos.append({'cx': box.pos().x(), 'cy': box.pos().y(), 'w': box.rect().width(), 'h': box.rect().height(), 'angle': box.rotation(), 'rot_out': box.rotacion_salida})
            
        nombre_base = Path(self.ruta_imagen_actual).stem
        self.thread_guardar = TareaGuardar(datos, self.imagen_opencv_actual, self.directorio_guardado_predeterminado, nombre_base)
        self.thread_guardar.terminado.connect(self._on_guardado_terminado)
        self.thread_guardar.start()

    def _on_guardado_terminado(self, cantidad):
        self.overlay_carga.ocultar()
        self.preguntar_siguiente(cantidad)
        
    def preguntar_siguiente(self, cantidad):
        dialogo = QMessageBox(self)
        dialogo.setWindowTitle("Éxito")
        dialogo.setText(f"Se guardaron {cantidad} fotos exitosamente.\n¿Qué deseas hacer ahora?")
        btn_siguiente = dialogo.addButton("Siguiente Escaneo", QMessageBox.ButtonRole.ActionRole)
        btn_cerrar = dialogo.addButton("Cerrar", QMessageBox.ButtonRole.RejectRole)
        dialogo.exec()
        
        if dialogo.clickedButton() == btn_siguiente:
            fila_actual = self.lista_archivos.currentRow()
            if fila_actual < self.lista_archivos.count() - 1:
                siguiente_item = self.lista_archivos.item(fila_actual + 1)
                self.lista_archivos.setCurrentItem(siguiente_item)
                self.cargar_desde_lista(siguiente_item)
            else:
                alerta = QMessageBox(self)
                alerta.setIcon(QMessageBox.Icon.Information)
                alerta.setWindowTitle("Fin de la lista")
                alerta.setText("Ya no hay más escaneos en esta carpeta.")
                btn_ok = alerta.addButton("Ok", QMessageBox.ButtonRole.AcceptRole)
                btn_volver = alerta.addButton("Volver al inicio", QMessageBox.ButtonRole.ActionRole)
                
                alerta.exec()
                if alerta.clickedButton() == btn_volver:
                    primer_item = self.lista_archivos.item(0)
                    self.lista_archivos.setCurrentItem(primer_item)
                    self.cargar_desde_lista(primer_item)