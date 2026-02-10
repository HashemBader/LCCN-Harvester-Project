import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget, QLabel

# Ensure src is in path
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from src.gui.input_tab import InputTab

def main():
    app = QApplication(sys.argv)
    window = QWidget()
    window.setWindowTitle("Input Tab Manual Test")
    window.resize(600, 500)
    
    layout = QVBoxLayout(window)
    
    input_tab = InputTab()
    layout.addWidget(input_tab)
    
    # Status label to verify signal emission
    status_label = QLabel("Waiting for file selection...")
    status_label.setStyleSheet("font-weight: bold; color: yellow; font-size: 14px;")
    layout.addWidget(status_label)
    
    def on_file_selected(path):
        if path:
            status_label.setText(f"✅ VALID FILE: {path}")
            status_label.setStyleSheet("font-weight: bold; color: #a9d48f; font-size: 14px;")
        else:
            status_label.setText("⛔ INVALID / CLEARED (Start Button would be DISABLED)")
            status_label.setStyleSheet("font-weight: bold; color: #e78284; font-size: 14px;")
        
    input_tab.file_selected.connect(on_file_selected)
    
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
