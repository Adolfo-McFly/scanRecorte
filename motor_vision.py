import cv2
import re
import math
import numpy as np
from PyQt6.QtGui import QImage

def ordenar_natural(archivo):
    """Permite que los archivos se ordenen 1, 2, 3... en lugar de 1, 10, 11..."""
    return [int(texto) if texto.isdigit() else texto.lower() for texto in re.split(r'(\d+)', archivo.name)]

def cv2_to_qimage(cv_img):
    """Convierte la matriz OpenCV a imagen de Qt compatible con hilos."""
    rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb_image.shape
    bytes_per_line = ch * w
    qimg = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
    return qimg.copy() 

class DetectorFotos:
    @staticmethod
    def snap_edges(gray_img, cx, cy, w, h, angle):
        """
        ALGORITMO DE CONTORNOS LOCALES:
        Extrae un parche de la imagen y encuentra la caja delimitadora exacta
        utilizando umbrales y detección de bordes, ignorando el polvo y fotos adyacentes.
        Funciona tanto con fondos oscuros como claros.
        """
        # Añadimos un pequeño padding adicional por seguridad.
        pad = 12 
        box_w, box_h = int(w + pad*2), int(h + pad*2)
        
        M = cv2.getRotationMatrix2D((cx, cy), angle, 1.0)
        M[0, 2] += box_w / 2.0 - cx
        M[1, 2] += box_h / 2.0 - cy
        
        patch = cv2.warpAffine(gray_img, M, (box_w, box_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        patch_blur = cv2.GaussianBlur(patch, (5, 5), 0)
        
        # Detectar si el fondo es claro u oscuro analizando los bordes del parche
        border_pixels = np.concatenate([
            patch_blur[0, :], patch_blur[-1, :],
            patch_blur[:, 0], patch_blur[:, -1]
        ])
        fondo_medio = np.mean(border_pixels)
        
        if fondo_medio > 127:
            # Fondo claro: invertir para que el objeto sea brillante
            _, thresh = cv2.threshold(patch_blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        else:
            # Fondo oscuro: umbral adaptativo más robusto
            _, thresh = cv2.threshold(patch_blur, 25, 255, cv2.THRESH_BINARY)
        
        # Añadir bordes ayuda con fotos que tengan bordes muy oscuros
        edges = cv2.Canny(patch_blur, 20, 80)
        combined = cv2.bitwise_or(thresh, edges)
        
        # Cerrar huecos
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        closed = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel)
        
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return cx, cy, w, h
            
        # Tomar el contorno más grande (la foto principal en el parche), ignorando basuritas
        c = max(contours, key=cv2.contourArea)
        x_edge, y_edge, w_edge, h_edge = cv2.boundingRect(c)
        
        # Seguridad: si el contorno es absurdamente pequeño, mantener original
        if w_edge < box_w * 0.4 or h_edge < box_h * 0.4:
            return cx, cy, w, h
            
        patch_cx = x_edge + w_edge / 2.0
        patch_cy = y_edge + h_edge / 2.0
        
        shift_x = patch_cx - (box_w / 2.0)
        shift_y = patch_cy - (box_h / 2.0)
        
        rad = math.radians(-angle)
        real_shift_x = shift_x * math.cos(rad) - shift_y * math.sin(rad)
        real_shift_y = shift_x * math.sin(rad) + shift_y * math.cos(rad)
        
        # Ajuste "Al Ras" muy fino: 1 píxel es suficiente para eliminar la sombra
        margin = 1
        new_w = w_edge - margin * 2
        new_h = h_edge - margin * 2
        
        return cx + real_shift_x, cy + real_shift_y, new_w, new_h

    @staticmethod
    def detectar(image_path, margen_recorte=18): 
        img = cv2.imread(image_path)
        if img is None: return [], None
        
        img_original = img.copy()
        scale = 800.0 / img.shape[1]
        img_small = cv2.resize(img, (int(img.shape[1]*scale), int(img.shape[0]*scale)))
        
        gray = cv2.cvtColor(img_small, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # Detectar si el fondo es claro u oscuro analizando los bordes de la imagen
        h_img, w_img = gray.shape
        border_size = max(5, min(h_img, w_img) // 20)
        border_pixels = np.concatenate([
            gray[:border_size, :].ravel(),
            gray[-border_size:, :].ravel(),
            gray[:, :border_size].ravel(),
            gray[:, -border_size:].ravel()
        ])
        fondo_medio = np.mean(border_pixels)
        fondo_claro = fondo_medio > 127
        
        # Estrategia adaptativa: usar Canny + umbral adaptativo para ambos fondos
        edges = cv2.Canny(blurred, 30, 100)
        
        if fondo_claro:
            # Fondo claro: usar umbralización adaptativa y diferencia con el fondo
            thresh = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                           cv2.THRESH_BINARY_INV, 51, 10)
            # También usar Otsu para capturar contraste global
            _, otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            combined_thresh = cv2.bitwise_or(thresh, otsu)
            combined = cv2.bitwise_or(combined_thresh, edges)
        else:
            # Fondo oscuro: el método original
            combined = edges.copy()
        
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
        dilated = cv2.dilate(combined, kernel, iterations=2)
        closed = cv2.morphologyEx(dilated, cv2.MORPH_CLOSE, kernel)
        
        # Para fondo claro, aplicar operaciones morfológicas adicionales para limpiar ruido
        if fondo_claro:
            kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            closed = cv2.morphologyEx(closed, cv2.MORPH_OPEN, kernel_open)
            closed = cv2.morphologyEx(closed, cv2.MORPH_CLOSE, 
                                       cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15)))
        
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        total_area = img_small.shape[0] * img_small.shape[1]
        rectangulos = []
        
        for c in contours:
            area = cv2.contourArea(c)
            pct_area = (area / total_area) * 100
            
            # Filtramos manchas diminutas o imágenes que ocupen más del 85% (el cristal entero)
            if 1.0 <= pct_area <= 85.0:
                rect = cv2.minAreaRect(c)
                (cx, cy), (w, h), angle = rect
                
                # Ignorar rectángulos extremadamente delgados
                if area / float(w * h if w*h > 0 else 1) > 0.50:
                    
                    # Llamamos a nuestro sistema "Al Ras" para limpiar las coordenadas crudas
                    cx_snap, cy_snap, w_snap, h_snap = DetectorFotos.snap_edges(gray, cx, cy, w, h, angle)
                    
                    rectangulos.append({
                        'cx': cx_snap / scale, 'cy': cy_snap / scale,
                        'w': (w_snap / scale) - margen_recorte, 'h': (h_snap / scale) - margen_recorte,
                        'angle': angle
                    })
                    
        return rectangulos, img_original

    @staticmethod
    def extraer_recorte(img_cv, cx, cy, w, h, angle, rot_out):
        """Extrae de forma eficiente el recorte de la imagen original."""
        size = int(math.hypot(w, h)) + 4
        # Extraemos un parche lo suficientemente grande centrado en la caja
        parche_pequeno = cv2.getRectSubPix(img_cv, (size, size), (cx, cy))
        
        centro_parche = (size / 2.0, size / 2.0)
        M = cv2.getRotationMatrix2D(centro_parche, angle, 1.0)
        
        parche_rotado = cv2.warpAffine(parche_pequeno, M, (size, size), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=[0,0,0])
        recorte = cv2.getRectSubPix(parche_rotado, (int(max(1, w)), int(max(1, h))), centro_parche)
        
        if rot_out == 90: recorte = cv2.rotate(recorte, cv2.ROTATE_90_CLOCKWISE)
        elif rot_out == 180: recorte = cv2.rotate(recorte, cv2.ROTATE_180)
        elif rot_out == 270: recorte = cv2.rotate(recorte, cv2.ROTATE_90_COUNTERCLOCKWISE)
            
        return recorte
