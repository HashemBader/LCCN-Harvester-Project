import os

def create_project_structure():
    # This structure maps directly to your Feature List in the Project Plan
    directories = {
        "src": ["__init__.py", "main.py"],  # Application Entry Point
        
        # F3: Database Architecture (DB Manager, Schema)
        "src/database": ["__init__.py", "db_manager.py", "schema.sql"],
        
        # F5: HTTP API Integration (LoC, Harvard, OpenLibrary classes)
        "src/api": ["__init__.py", "loc_api.py", "harvard_api.py", "openlibrary_api.py"],
        
        # F6: Z39.50 Protocol (Session Manager, MARC Decoder)
        "src/z3950": ["__init__.py", "session_manager.py", "marc_decoder.py"],
        
        # F7 & F8: GUI Implementation (Main Window, Targets Tab)
        "src/gui": ["__init__.py", "main_window.py", "targets_tab.py"],
        
        # F4: Core Logic (ISBN cleaning, Validation, MARC parsing)
        "src/utils": ["__init__.py", "isbn_validator.py", "marc_parser.py", "config_manager.py"],
        
        # F11: Quality Assurance (Unit & Integration Tests)
        "tests": ["__init__.py", "test_isbn.py", "test_db.py"],
        
        # F12: Documentation (User Manuals)
        "docs": ["user_guide.md", "dev_setup.md"],
        
        # Data storage (Local DB location - .gitkeep needed to track empty folder)
        "data": [".gitkeep"] 
    }

    print("🚀 Initializing LCCN Harvester Directory Structure...")

    for folder, files in directories.items():
        # Create the directory
        os.makedirs(folder, exist_ok=True)
        print(f"   📂 Created: {folder}/")
        
        # Create the placeholder files
        for filename in files:
            filepath = os.path.join(folder, filename)
            if not os.path.exists(filepath):
                with open(filepath, "w") as f:
                    # Add a simple docstring so the files aren't totally empty
                    if filename.endswith(".py"):
                        f.write(f'"""\nModule: {filename}\nPart of the LCCN Harvester Project.\n"""\n')
                print(f"      📄 Created: {filename}")

    # Create requirements.txt if it doesn't exist
    if not os.path.exists("requirements.txt"):
        with open("requirements.txt", "w") as f:
            f.write("PyQt6>=6.4.0\nrequests>=2.28.0\npytest>=7.0.0\n")
        print("   📄 Created: requirements.txt")

    print("\n✅ Structure complete. You can now delete this script and push to GitHub.")

if __name__ == "__main__":
    create_project_structure()
