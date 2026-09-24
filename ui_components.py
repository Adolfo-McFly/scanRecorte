import math
from PyQt6.QtWidgets import (QGraphicsView, QGraphicsRectItem, QWidget, 
                             QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
                             QGraphicsDropShadowEffect, QGraphicsItem, QGraphicsOpacityEffect,
                             QDialog, QComboBox, QRadioButton, QButtonGroup, QMessageBox)
from PyQt6.QtGui import QPen, QColor, QBrush, QPainter, QPainterPath, QTransform, QCursor, QPixmap
from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer, QPropertyAnimation, QEasingCurve

def get_rotate_cursor():
    """Genera un cursor personalizado de flecha circular estilo Photoshop"""
    if not hasattr(get_rotate_cursor, "cursor"):
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Sombra negra para que resalte
        pen_bg = QPen(QColor(0,0,0,180), 5)
        pen_bg.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_bg)
        painter.drawArc(4, 4, 24, 24, 45 * 16, 270 * 16)
        painter.translate(16, 16)
        painter.rotate(45)
        painter.drawLine(12, 0, 4, -8)
        painter.drawLine(12, 0, 20, -8)
        painter.resetTransform()
        
        # Flecha principal blanca
        pen_fg = QPen(Qt.GlobalColor.white, 2)
        pen_fg.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_fg)
        painter.drawArc(4, 4, 24, 24, 45 * 16, 270 * 16)
        painter.translate(16, 16)
        painter.rotate(45)
        painter.drawLine(12, 0, 4, -8)
        painter.drawLine(12, 0, 20, -8)
        painter.end()
        
        get_rotate_cursor.cursor = QCursor(pixmap, 16, 16)
    return get_rotate_cursor.cursor

class ZoomView(QGraphicsView):
    def __init__(self, scene):
        super().__init__(scene)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.NoDrag) 
        self.setStyleSheet("border: none; background-color: #121212;") 
        self._is_panning = False
        self._pan_start_pos = None

    def mousePressEvent(self, event):
        item = self.itemAt(event.pos())
        if event.button() == Qt.MouseButton.LeftButton:
            if not item or (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                self._is_panning = True
                self._pan_start_pos = event.pos()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_panning:
            delta = event.pos() - self._pan_start_pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self._pan_start_pos = event.pos()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._is_panning:
            self._is_panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)
        
    def wheelEvent(self, event):
        zoom_in_factor = 1.15
        zoom_out_factor = 1 / zoom_in_factor
        if event.angleDelta().y() > 0: self.scale(zoom_in_factor, zoom_in_factor)
        else: self.scale(zoom_out_factor, zoom_out_factor)

class CajaRecorteInteractiva(QGraphicsRectItem):
    def __init__(self, cx, cy, w, h, angle, on_release_callback, on_lupa_callback, on_press_callback):
        super().__init__(-w/2, -h/2, w, h)
        self.setPos(cx, cy)
        self.setRotation(angle)
        self.on_release_callback = on_release_callback
        self.on_lupa_callback = on_lupa_callback
        self.on_press_callback = on_press_callback 
        
        self.rotacion_salida = 0 
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setAcceptHoverEvents(True) 
        
        self.accion_actual = None
        self._logical_mouse_pos = None

    def get_scale_factor(self):
        if self.scene() and self.scene().views():
            return self.scene().views()[0].transform().m11()
        return 1.0

    def obtener_posiciones_nodos(self):
        scale = self.get_scale_factor()
        if scale == 0: scale = 1.0
        dist_rot = 80.0 / scale 
        
        r = self.rect()
        return {
            'TL': r.topLeft(), 'TR': r.topRight(), 'BL': r.bottomLeft(), 'BR': r.bottomRight(),
            'T': QPointF(0, r.top()), 'B': QPointF(0, r.bottom()), 
            'L': QPointF(r.left(), 0), 'R': QPointF(r.right(), 0),
            'ROT': QPointF(0, r.top() - dist_rot)
        }

    def boundingRect(self):
        r = QRectF(self.rect())
        r.adjust(-2000, -2000, 2000, 2000)
        return r

    def shape(self):
        path = QPainterPath()
        scale = self.get_scale_factor()
        if scale == 0: scale = 1.0
        
        # El radio físico para los clics en PyQt es exactamente igual al dibujo visual
        radio_visual = 8.0 / scale 
        
        # Permitir seleccionar el centro de la caja para moverla
        path.addRect(self.rect())
        
        # Agregar exclusivamente los círculos exactos a la zona de clic
        nodos = self.obtener_posiciones_nodos()
        for clave, pos in nodos.items():
            r_hit = radio_visual * 1.5 if clave == 'ROT' else radio_visual
            path.addEllipse(pos, r_hit, r_hit)
            
        return path

    def paint(self, painter, option, widget=None):
        r = self.rect()
        scale = self.get_scale_factor()
        if scale == 0: scale = 1.0
        
        # TAMAÑOS VISUALES
        radio_visual = 8.0 / scale 
        grosor_linea = 1.5 / scale 
        
        if self.isSelected():
            painter.setBrush(QBrush(QColor(0, 162, 237, 20)))
            painter.setPen(QPen(QColor("#0078D7"), grosor_linea, Qt.PenStyle.DashLine))
            painter.drawRect(r)
            
            nodos = self.obtener_posiciones_nodos()
            rot_pos = nodos['ROT']
            
            painter.setPen(QPen(QColor("#404040"), grosor_linea))
            painter.drawLine(QPointF(0, r.top()), rot_pos)
            
            painter.setBrush(QBrush(QColor("white")))
            painter.setPen(QPen(QColor("#404040"), grosor_linea * 1.5)) 
            
            for clave, pos in nodos.items():
                if clave != 'ROT':
                    # Dibuja el círculo exactamente del mismo radio que se usará para el clic
                    painter.drawEllipse(pos, radio_visual, radio_visual)
            
            painter.drawEllipse(rot_pos, radio_visual * 1.5, radio_visual * 1.5) 
            
            painter.setPen(QPen(QColor("#404040"), grosor_linea * 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.save()
            painter.translate(rot_pos)
            ar = radio_visual * 2.0
            painter.drawArc(QRectF(-ar, -ar, ar*2, ar*2), 45 * 16, 270 * 16)
            painter.rotate(45)
            painter.drawLine(QPointF(ar, 0), QPointF(ar - radio_visual*0.6, -radio_visual*0.6))
            painter.drawLine(QPointF(ar, 0), QPointF(ar + radio_visual*0.6, -radio_visual*0.6))
            painter.restore()
            
        else:
            painter.setBrush(QBrush(QColor(0, 162, 237, 10))) 
            painter.setPen(QPen(QColor("#00A2ED"), grosor_linea * 1.5, Qt.PenStyle.SolidLine))
            painter.drawRect(r)

    def obtener_accion_click(self, pos):
        """
        PRECISIÓN MILIMÉTRICA: 
        Comprueba si la distancia del ratón al centro del punto es menor 
        o igual al radio dibujado. Cero tolerancia extra.
        """
        scale = self.get_scale_factor()
        if scale == 0: scale = 1.0
        
        radio_visual = 8.0 / scale 
        nodos = self.obtener_posiciones_nodos()
        
        for clave, pos_nodo in nodos.items():
            if clave == 'ROT' and not self.isSelected(): continue
            
            dist = math.hypot(pos.x() - pos_nodo.x(), pos.y() - pos_nodo.y())
            radio_actual = radio_visual * 1.5 if clave == 'ROT' else radio_visual
            
            # Si el clic está físicamente tocando el blanco del círculo pintado:
            if dist <= radio_actual:
                return clave
                
        return None

    def hoverMoveEvent(self, event):
        nodo = self.obtener_accion_click(event.pos())
        if nodo in ('TL', 'BR'): self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif nodo in ('TR', 'BL'): self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif nodo in ('T', 'B'): self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif nodo in ('L', 'R'): self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif nodo == 'ROT': self.setCursor(get_rotate_cursor()) 
        elif self.rect().contains(event.pos()): self.setCursor(Qt.CursorShape.SizeAllCursor)
        else: self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        self.accion_actual = self.obtener_accion_click(event.pos())
        if self.accion_actual:
            self.setSelected(True) 
            self.on_press_callback() 
            self._inicio_escena_pos = self.scenePos()
            self._inicio_rect = self.rect()
            self._inicio_mouse_pos = event.scenePos()
            self._logical_mouse_pos = event.scenePos()
            self.on_lupa_callback(event.scenePos(), True)
            event.accept() 
        else:
            self.on_press_callback()
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        scene_rect = self.scene().sceneRect()
        
        if self.accion_actual == 'ROT':
            old_angle = self.rotation()
            centro_escena = self.mapToScene(QPointF(0, 0))
            vector = event.scenePos() - centro_escena
            angulo = math.degrees(math.atan2(vector.y(), vector.x())) + 90
            self.setRotation(angulo)
            
            poly = self.mapToScene(self.rect())
            if any(not scene_rect.contains(p) for p in poly):
                self.setRotation(old_angle)
                
            self.on_lupa_callback(event.scenePos(), True)
            
        elif self.accion_actual:
            delta_real = event.scenePos() - event.lastScenePos()
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._logical_mouse_pos += delta_real * 0.25 
            else:
                self._logical_mouse_pos += delta_real

            lx = max(scene_rect.left(), min(self._logical_mouse_pos.x(), scene_rect.right()))
            ly = max(scene_rect.top(), min(self._logical_mouse_pos.y(), scene_rect.bottom()))
            self._logical_mouse_pos = QPointF(lx, ly)

            old_rect = self.rect()
            old_pos = self.pos()

            delta_escena = self._logical_mouse_pos - self._inicio_mouse_pos
            ang_rad = -math.radians(self.rotation())
            dx_local = delta_escena.x() * math.cos(ang_rad) - delta_escena.y() * math.sin(ang_rad)
            dy_local = delta_escena.x() * math.sin(ang_rad) + delta_escena.y() * math.cos(ang_rad)
            
            left, right = self._inicio_rect.left(), self._inicio_rect.right()
            top, bottom = self._inicio_rect.top(), self._inicio_rect.bottom()
            
            if self.accion_actual in ['L', 'TL', 'BL']: left += dx_local
            if self.accion_actual in ['R', 'TR', 'BR']: right += dx_local
            if self.accion_actual in ['T', 'TL', 'TR']: top += dy_local
            if self.accion_actual in ['B', 'BL', 'BR']: bottom += dy_local
            
            if right - left < 40:
                if self.accion_actual in ['L', 'TL', 'BL']: left = right - 40
                else: right = left + 40
            if bottom - top < 40:
                if self.accion_actual in ['T', 'TL', 'TR']: top = bottom - 40
                else: bottom = top + 40
                
            nuevo_centro_x = (left + right) / 2
            nuevo_centro_y = (top + bottom) / 2
            
            ang_rad_pos = math.radians(self.rotation())
            offset_x = nuevo_centro_x * math.cos(ang_rad_pos) - nuevo_centro_y * math.sin(ang_rad_pos)
            offset_y = nuevo_centro_x * math.sin(ang_rad_pos) + nuevo_centro_y * math.cos(ang_rad_pos)
            
            nuevo_w = right - left
            nuevo_h = bottom - top
            
            self.setRect(-nuevo_w/2, -nuevo_h/2, nuevo_w, nuevo_h)
            self.setPos(self._inicio_escena_pos.x() + offset_x, self._inicio_escena_pos.y() + offset_y)
            
            poly = self.mapToScene(self.rect())
            if any(not scene_rect.contains(p) for p in poly):
                self.setRect(old_rect)
                self.setPos(old_pos)

            self.on_lupa_callback(event.scenePos(), True) 
        else:
            delta_real = event.scenePos() - event.lastScenePos()
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                delta_real *= 0.25
                
            old_pos = self.pos()
            self.setPos(self.pos() + delta_real)
            
            poly = self.mapToScene(self.rect())
            if any(not scene_rect.contains(p) for p in poly):
                self.setPos(old_pos)

            self.on_lupa_callback(event.scenePos(), True)

    def mouseReleaseEvent(self, event):
        self.accion_actual = None
        super().mouseReleaseEvent(event)
        self.on_lupa_callback(None, False)
        self.on_release_callback()


class VistaPreviaWidget(QWidget):
    def __init__(self, pixmap, index, caja_ref, callback_press):
        super().__init__()
        self.caja_ref = caja_ref
        self.callback_press = callback_press
        self.pixmap_actual = pixmap 
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 15, 10, 25) 
        
        lbl_titulo = QLabel(f"Foto {index}")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_titulo.setObjectName("titulo_previa")
        
        self.lbl_img = QLabel()
        self._actualizar_imagen()
        
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 5)
        self.lbl_img.setGraphicsEffect(shadow)
        
        btn_layout = QHBoxLayout()
        btn_izq = QPushButton("↶ Rotar")
        btn_der = QPushButton("Rotar ↷")
        btn_izq.setObjectName("btn_secundario")
        btn_der.setObjectName("btn_secundario")
        btn_izq.clicked.connect(self.rotar_izq)
        btn_der.clicked.connect(self.rotar_der)
        btn_layout.addWidget(btn_izq)
        btn_layout.addWidget(btn_der)
        
        layout.addWidget(lbl_titulo)
        layout.addWidget(self.lbl_img)
        layout.addLayout(btn_layout)
        
    def _actualizar_imagen(self):
        pixmap_escalado = self.pixmap_actual.scaled(220, 220, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.lbl_img.setPixmap(pixmap_escalado)
        self.lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def rotar_izq(self):
        self.callback_press()
        self.caja_ref.rotacion_salida = (self.caja_ref.rotacion_salida - 90) % 360
        transform = QTransform().rotate(-90)
        self.pixmap_actual = self.pixmap_actual.transformed(transform, Qt.TransformationMode.SmoothTransformation)
        self._actualizar_imagen()
        
    def rotar_der(self):
        self.callback_press()
        self.caja_ref.rotacion_salida = (self.caja_ref.rotacion_salida + 90) % 360
        transform = QTransform().rotate(90)
        self.pixmap_actual = self.pixmap_actual.transformed(transform, Qt.TransformationMode.SmoothTransformation)
        self._actualizar_imagen()


class PantallaCarga(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFixedSize(250, 250) 
        
        self.tiempo_desvanecimiento = 1500 
        self.modo_progreso = False
        self.porcentaje = 0
        self.cancelado = False
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignBottom)
        
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setObjectName("btn_eliminar")
        self.btn_cancelar.clicked.connect(self.intentar_cancelar)
        self.btn_cancelar.hide()
        layout.addWidget(self.btn_cancelar)
        
        self.mensaje = "Procesando..."
        self.angulo = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.rotar)
        
        self.efecto_opacidad = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.efecto_opacidad)
        self.efecto_opacidad.setOpacity(0)
        
        self.animacion = QPropertyAnimation(self.efecto_opacidad, b"opacity")
        self.animacion.setDuration(self.tiempo_desvanecimiento) 
        self.animacion.setEasingCurve(QEasingCurve.Type.OutQuad)
        self.animacion.finished.connect(self._on_anim_finished)
        
        self._ocultando = False
        self.hide()

    def intentar_cancelar(self):
        resp = QMessageBox.question(self, "Confirmar", "¿Seguro que deseas cancelar el proceso actual?", 
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if resp == QMessageBox.StandardButton.Yes:
            self.cancelado = True

    def mostrar(self, texto, modo_progreso=False):
        self.mensaje = texto
        self.modo_progreso = modo_progreso
        self.porcentaje = 0
        self.cancelado = False
        
        if self.modo_progreso:
            self.btn_cancelar.show()
        else:
            self.btn_cancelar.hide()
            
        if self.parent():
            px = (self.parent().width() - self.width()) // 2
            py = (self.parent().height() - self.height()) // 2
            self.move(px, py)
            
        self._ocultando = False
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False) 
        self.show()
        self.raise_()
        
        if not self.timer.isActive():
            self.timer.start(16) 
            
        self.animacion.stop()
        self.efecto_opacidad.setOpacity(1.0)

    def actualizar_progreso(self, val):
        self.porcentaje = val
        
    def ocultar(self):
        if self._ocultando: return
        self._ocultando = True
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True) 
        self.btn_cancelar.hide()
        
        self.animacion.stop()
        self.animacion.setStartValue(self.efecto_opacidad.opacity())
        self.animacion.setEndValue(0.0)
        self.animacion.start()

    def _on_anim_finished(self):
        if self._ocultando:
            self.hide()
            self.timer.stop() 

    def rotar(self):
        if not self.modo_progreso:
            self.angulo = (self.angulo + 10) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        painter.setBrush(QColor(30, 30, 30, 230))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 15, 15)
        
        cx, cy = self.width() // 2, self.height() // 2 - 20
        
        pen_track = QPen(QColor(255, 255, 255, 30), 6)
        painter.setPen(pen_track)
        painter.drawArc(cx - 35, cy - 35, 70, 70, 0, 360 * 16)
        
        pen = QPen(QColor("#00A2ED"), 6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        
        if self.modo_progreso:
            grados = int((self.porcentaje / 100.0) * 360)
            painter.drawArc(cx - 35, cy - 35, 70, 70, 90 * 16, -grados * 16)
            
            painter.setPen(QColor("white"))
            font = painter.font()
            font.setPointSize(14)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(cx - 35, cy - 35, 70, 70, Qt.AlignmentFlag.AlignCenter, f"{self.porcentaje}%")
        else:
            painter.drawArc(cx - 35, cy - 35, 70, 70, -self.angulo * 16, 120 * 16)
            
        painter.setPen(QColor("white"))
        font = painter.font()
        font.setPointSize(12)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(0, cy + 60, self.width(), 30, Qt.AlignmentFlag.AlignCenter, self.mensaje)

class DialogoEscaner(QDialog):
    def __init__(self, escaneres_disponibles, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Seleccione Escáner y Resolución")
        self.setFixedSize(650, 350)
        self.setStyleSheet("background-color: #1E1E1E; color: white;")
        
        layout = QVBoxLayout(self)
        
        cabecera = QLabel("¿Qué le gustaría escanear?")
        cabecera.setStyleSheet("background-color: #007ACC; color: white; padding: 10px; font-weight: bold; font-size: 16px;")
        cabecera.setAlignment(Qt.AlignmentFlag.AlignCenter) 
        layout.addWidget(cabecera)
        
        color_layout = QHBoxLayout()
        self.grupo_color = QButtonGroup(self)
        self.rad_color = QRadioButton("Color verdadero (24 bits)")
        self.rad_gris = QRadioButton("Escala de grises (16 bits)")
        self.rad_color.setChecked(True)
        self.grupo_color.addButton(self.rad_color)
        self.grupo_color.addButton(self.rad_gris)
        
        color_layout.addWidget(self.rad_color)
        color_layout.addWidget(self.rad_gris)
        color_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(color_layout)
        
        form_layout = QVBoxLayout()
        
        row_escaner = QHBoxLayout()
        lbl_esc = QLabel("Seleccione Escáner:")
        lbl_esc.setFixedWidth(150)
        self.combo_escaner = QComboBox()
        self.combo_escaner.setObjectName("combo_oscuro")
        
        self.escaneres = escaneres_disponibles
        if not self.escaneres:
            self.combo_escaner.addItem("No se encontraron escáneres encendidos")
            self.combo_escaner.setEnabled(False)
        else:
            for esc in self.escaneres:
                self.combo_escaner.addItem(esc['nombre'], esc['id'])
                
        btn_actualizar = QPushButton("Actualizar")
        btn_actualizar.setObjectName("btn_secundario")
        btn_actualizar.clicked.connect(self.solicitar_actualizacion)
        
        row_escaner.addWidget(lbl_esc)
        row_escaner.addWidget(self.combo_escaner)
        row_escaner.addWidget(btn_actualizar)
        
        row_res = QHBoxLayout()
        lbl_res = QLabel("Seleccione Resolución:")
        lbl_res.setFixedWidth(150)
        self.combo_res = QComboBox()
        self.combo_res.setObjectName("combo_oscuro")
        self.combo_res.addItems(["150 PPP (Rápido)", "300 PPP (Recomendado)", "600 PPP (Alta Calidad)", "1200 PPP (Lento/Negativos)"])
        self.combo_res.setCurrentIndex(1) 
        
        row_res.addWidget(lbl_res)
        row_res.addWidget(self.combo_res)
        row_res.addStretch()
        
        form_layout.addLayout(row_escaner)
        form_layout.addLayout(row_res)
        
        alerta = QLabel("Asegúrese de que el escáner esté enchufado y encendido.")
        alerta.setStyleSheet("background-color: #332B00; color: #FFD700; padding: 15px; border: 1px solid #B29600; border-radius: 4px;")
        alerta.setWordWrap(True)
        form_layout.addWidget(alerta)
        
        layout.addLayout(form_layout)
        layout.addStretch()
        
        botones_layout = QHBoxLayout()
        botones_layout.setAlignment(Qt.AlignmentFlag.AlignRight)
        
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.clicked.connect(self.reject)
        
        btn_ok = QPushButton("Escanear")
        btn_ok.setObjectName("btn_escanear_azul") 
        btn_ok.clicked.connect(self.accept)
        
        if not self.escaneres:
            btn_ok.setEnabled(False)
            btn_ok.setStyleSheet("background-color: #555555;")
            
        botones_layout.addWidget(btn_cancelar)
        botones_layout.addWidget(btn_ok)
        layout.addLayout(botones_layout)

    def solicitar_actualizacion(self):
        self.parent().overlay_carga.mostrar("Buscando escáneres...")
        QTimer.singleShot(500, self.parent()._procesar_ventana_escaner)
        self.accept()

    def obtener_configuracion(self):
        dpi_str = self.combo_res.currentText().split(" ")[0]
        return {
            'device_id': self.combo_escaner.currentData(),
            'dpi': int(dpi_str),
            'modo_color': "Color" if self.rad_color.isChecked() else "Gris"
        }