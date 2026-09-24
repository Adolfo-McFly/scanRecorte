import cv2
import re
from PyQt6.QtGui import QImage

def ordenar_natural(archivo):
    return [int(texto) if texto.isdigit() else texto.lower() for texto in re.split(r'(\d+)', archivo.name)]

def cv2_to_qimage(cv_img):
    rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb_image.shape
    bytes_per_line = ch * w
    qimg = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
    # .copy() es VITAL para evitar que se crashee al pasarlo de un hilo a otro
    return qimg.copy() 

class DetectorFotos:
    @staticmethod
    def detectar(image_path, margen_recorte=18):
        img = cv2.imread(image_path)
        if img is None: return [], None
        
        img_original = img.copy()
        scale = 800.0 / img.shape[1]
        img_small = cv2.resize(img, (int(img.shape[1]*scale), int(img.shape[0]*scale)))
        
        gray = cv2.cvtColor(img_small, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 30, 100)
        
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
        dilated = cv2.dilate(edges, kernel, iterations=2)
        closed = cv2.morphologyEx(dilated, cv2.MORPH_CLOSE, kernel)
        
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        total_area = img_small.shape[0] * img_small.shape[1]
        rectangulos = []
        
        for c in contours:
            area = cv2.contourArea(c)
            pct_area = (area / total_area) * 100
            if 1.0 <= pct_area <= 85.0:
                rect = cv2.minAreaRect(c)
                (cx, cy), (w, h), angle = rect
                if area / float(w * h if w*h > 0 else 1) > 0.50:
                    w_ajustado = max(10, w - margen_recorte)
                    h_ajustado = max(10, h - margen_recorte)
                    rectangulos.append({
                        'cx': cx / scale, 'cy': cy / scale,
                        'w': w_ajustado / scale, 'h': h_ajustado / scale,
                        'angle': angle
                    })
        return rectangulos, img_original