import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget, QLabel

# Ensure src is in path
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from src.gui.harvest_tab_v2 import HarvestTabV2

def main():
    app = QApplication(sys.argv)
    window = QWidget()
    window.setWindowTitle("Harvest Tab V2 Manual Test")
    window.resize(800, 600)
    window.setStyleSheet("background-color: #24273a;") # Base color
    
    layout = QVBoxLayout(window)
    
    tab = HarvestTabV2()
    
    # Mock Data Sources for standalone testing
    tab.set_data_sources(
        config_getter=lambda: {"retry_days": 7},
        targets_getter=lambda: [{"name": "Mock Target", "type": "api"}] 
    )
    
    layout.addWidget(tab)
    
    # Status label
    status_label = QLabel("Click Browse or Drag file to test validation")
    status_label.setStyleSheet("color: white; font-size: 14px; font-weight: bold;")
    layout.addWidget(status_label)
    
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
