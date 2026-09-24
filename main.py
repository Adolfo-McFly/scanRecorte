import sys
from PyQt6.QtWidgets import QApplication
from ventana_principal import EscanerApp

def main():
    app = QApplication(sys.argv)
    
    # Fusion es el motor base que permite que nuestro archivo .qss se vea bien en Windows/Mac/Linux
    app.setStyle("Fusion") 
    
    ventana = EscanerApp()
    ventana.show()
    
    sys.exit(app.exec())

if __name__ == '__main__':
    main()