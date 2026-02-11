# Input Tab User Guide (V2)

The Input Tab (available as the **Input** view or within the **Harvest** tab of the V2 GUI) is the starting point for any harvesting operation. Its primary purpose is to allow you to select and validate a list of ISBNs to be processed.

## 1. Supported File Formats

The Harvester accepts plain text files where ISBNs are listed **line-by-line**.

| Format | Extension | Description |
| :--- | :--- | :--- |
| **TSV** | `.tsv` | **Most Recommended**. Tab-Separated Values. The Harvester reads the **first column**. |
| **Simple Text** | `.txt` | One ISBN per line. No extra columns. |
| **CSV** | `.csv` | Comma-Separated Values. The Harvester reads the **first column**. |

**Sample Valid Input:**
```text
ISBN
978-0-306-40615-7
0-306-40615-2
9780306406157
```
*(Note: Headers like "ISBN" are automatically detected and skipped.)*

---

## 2. Selection Methods

### A. Drag & Drop
Simply drag a supported file from your File Explorer anywhere onto the **Blue Dashed Drop Zone**.

### B. Browse Button
Click the **"Browse..."** button to open a system file dialog. The filter default shows `*.txt *.tsv *.csv` files.

---

## 3. Validation Logic

Once a file is selected, the Harvester performs **Instant Validation**:

1.  **Extension Check**: Rejects invalid file types immediately.
2.  **Content Analysis**: Reads the file, skipping headers and blank lines.
3.  **ISBN Validation**: Uses strict normalization logic to count valid ISBNs.

### Status Indicators

| Badge | Meaning | Action Required |
| :--- | :--- | :--- |
| <span style="color:#a6da95">✅ Valid input</span> | File contains **valid ISBNs** and no critical errors. | Ready to start! |
| <span style="color:#eed49f">⚠️ X invalid lines</span> | File has valid ISBNs but some lines were skipped (garbage/headers). | **Warning**: You can proceed, but check the count. |
| <span style="color:#ed8796">❌ Error</span> | File format is wrong or contains **0 valid ISBNs**. | **Critical**: You must fix the file to proceed. |

---

## 4. Controls & Actions

### **Clear Selection (✕)**
Click the small "✕" button on the **File Pill** (the dark bar showing the filename) to:
*   Remove the current file.
*   Reset the validation state.
*   Bring back the Drop Zone.

### **Start Harvest**
The "Start Harvest" button is **Disabled logic-gated**. It will only enable if:
1.  **File is Valid** (Green or Yellow badge).
2.  **Targets are Selected** (At least one target checked in the **Targets Tab**).

**Dynamic Label:** The button text updates to show count: *"Start Harvest (150 ISBNs)"*.

### **Stop Harvest**
Available only while running. Click the **Red Stop Button** to safely interrupt processing.
*   **Result**: The process stops after the current ISBN completes.
*   **Safety**: Partial results are saved to the database.

---

## 5. Troubleshooting Common Issues

**Q: Why is "Start Harvest" disabled even with a green checkmark?**
A: Check the **Targets Tab**. You must have at least one target (e.g., Library of Congress) selected. The Harvester needs to know *where* to search.

**Q: My CSV has 100 lines but it says "Loaded: 0 ISBNs".**
A: Ensure the ISBNs are in the **first column**. If your CSV has complex quoting or mixed delimiters, try saving it as a clean TSV.

**Q: It says "Invalid file format".**
A: Ensure the file extension is strictly `.txt`, `.tsv`, or `.csv`. Excel files (`.xlsx`) must be exported to CSV/TSV first.
