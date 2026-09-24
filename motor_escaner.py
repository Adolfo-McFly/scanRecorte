import os
import tempfile
import cv2
import pythoncom
import win32com.client
import numpy as np

class MotorEscaner:
    @staticmethod
    def listar_escaneres():
        pythoncom.CoInitialize()
        try:
            dev_manager = win32com.client.Dispatch("WIA.DeviceManager")
            escaneres = []
            for i in range(1, dev_manager.DeviceInfos.Count + 1):
                info = dev_manager.DeviceInfos(i)
                if info.Type == 1: 
                    nombre = "Escáner Desconocido"
                    for p in info.Properties:
                        if p.PropertyID == 7: 
                            nombre = p.Value
                            break
                    escaneres.append({'id': info.DeviceID, 'nombre': nombre})
            return escaneres
        except Exception as e:
            return []
        finally:
            pythoncom.CoUninitialize()

    @staticmethod
    def escanear(device_id, dpi=300, modo_color="Color"):
        """Genera imagen simulada. Retorna la imagen CV2."""
        pythoncom.CoInitialize()
        temp_path = os.path.join(tempfile.gettempdir(), "temp_scan_photoscanpro.bmp")
        try:
            if os.path.exists(temp_path): os.remove(temp_path)
            
            alto, ancho = int(11.69 * dpi), int(8.27 * dpi)
            img_simulada = np.ones((alto, ancho, 3), dtype=np.uint8) * 240
            cv2.putText(img_simulada, f"Hoja Escaneada a {dpi} DPI ({modo_color})", 
                        (200, 500), cv2.FONT_HERSHEY_SIMPLEX, 3, (100, 100, 100), 5)
            
            cv2.imwrite(temp_path, img_simulada)
            img_cv = cv2.imread(temp_path)
            return img_cv
        except Exception as e:
            raise Exception(f"Error de hardware al escanear: {e}")
        finally:
            if os.path.exists(temp_path):
                try: os.remove(temp_path)
                except: pass
            pythoncom.CoUninitialize()