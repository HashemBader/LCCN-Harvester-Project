# ⚙️ Configuration Profile System

## Overview

The LCCN Harvester uses a **Profile System** to manage different configuration setups. This allows you to create, save, and switch between multiple configuration profiles easily.

---

## 🎯 What Are Profiles?

Profiles are **named collections of settings** that you can create, save, and reuse. Instead of reconfiguring settings every time, you can create profiles for different scenarios and switch between them instantly.

### Example Use Cases:

1. **"Academic Books"** - Optimized for scholarly material with longer retry periods
2. **"Quick Harvest"** - Fast harvesting with no retries
3. **"Medical Books"** - Collect both LCCN and NLMCN call numbers
4. **"Weekend Full Harvest"** - Full configuration for overnight batch jobs

---

## 📁 How Profiles Are Stored

All profiles are stored **locally within the app directory** - fully portable!

```
LCCN-Harvester-Project/
└── config/
    ├── default_profile.json        # Built-in, cannot be modified
    ├── active_profile.txt          # Currently active profile name
    └── profiles/
        ├── academic_books.json
        ├── quick_harvest.json
        ├── medical_books.json
        └── weekend_full.json
```

**Portable Design:**
- Everything stays in the app directory
- No system-wide settings
- Works from USB stick
- Easy backup (just copy the folder!)

---

## 🎨 Using the Profile System

### **Configuration Tab Interface:**

```
┌──────────────────────────────────────────────────────┐
│ Configuration Profile                                │
├──────────────────────────────────────────────────────┤
│ Active: [Academic Books ▾]         ● Unsaved changes│
│                                                      │
│ [💾 Save] [Save As...] [Use Session Only] [⚙️ Manage]│
└──────────────────────────────────────────────────────┘
```

---

## 🔄 Profile Operations

### **1. Switch Profiles**

Click the dropdown and select a profile:
- **Default Settings** - Built-in factory defaults
- **Academic Books** - Your custom profile
- **Quick Harvest** - Another custom profile

The settings automatically update to match the selected profile.

### **2. Create New Profile**

1. Configure your desired settings
2. Click **"Save As..."**
3. Enter a name: e.g., "Medical Books"
4. Click OK

The new profile is created and becomes active.

### **3. Save Changes to Current Profile**

1. Make changes to settings
2. Notice the **● Unsaved changes** indicator
3. Click **💾 Save** to update the current profile

**Note:** You cannot modify the "Default Settings" profile. Use "Save As..." to create a new profile instead.

### **4. Use Session Only**

Want to try settings without saving?

1. Make your changes
2. Click **"Use Session Only"**
3. Changes are used for this session only
4. Profile remains unchanged

Perfect for testing or one-time harvests!

### **5. Manage Profiles**

Click **⚙️ Manage** to access:

- **✏️ Rename Profile** - Change profile name
- **🗑️ Delete Profile** - Remove unwanted profile
- **🔄 Reset to Default Settings** - Load factory defaults

---

## 💡 Profile Settings

Each profile stores:

### **Call Number Collection:**
- ☑ Collect Library of Congress Call Numbers (LCCN)
- ☐ Collect NLM Call Numbers (NLMCN)

### **Retry Settings:**
- Days before retrying failed ISBNs: `7 days`

### **Output Settings:**
- ☑ Generate TSV output file
- ☑ Generate invalid ISBN file

---

## 🚀 Example Workflows

### **Workflow 1: Academic Research**

```
1. Select "Default Settings"
2. Adjust:
   - Retry days: 14
   - Both LCCN and NLMCN enabled
3. Click "Save As..." → "Academic Books"
4. Profile saved!
```

### **Workflow 2: Quick Test**

```
1. Select "Academic Books"
2. Change retry days to 0
3. Click "Use Session Only"
4. Run harvest
5. Profile unchanged for next time
```

### **Workflow 3: Multiple Projects**

```
Morning:   Load "Medical Books" → Harvest medical texts
Afternoon: Load "Academic Books" → Harvest research papers
Evening:   Load "Quick Harvest" → Fast batch processing
```

---

## 🔐 Profile Protection

### **Default Settings Profile:**
- **Cannot be modified** - Read-only
- **Cannot be deleted** - Always available
- **Cannot be renamed** - Fixed name
- **Always accessible** - Factory reset option

### **User Profiles:**
- Can be modified freely
- Can be deleted
- Can be renamed
- Fully customizable

---

## 📊 Profile JSON Format

If you want to manually create or edit profiles:

```json
{
  "profile_name": "Academic Books",
  "created_at": "2026-01-29T10:30:00",
  "description": "Optimized for academic and scholarly books",
  "settings": {
    "collect_lccn": true,
    "collect_nlmcn": false,
    "retry_days": 14,
    "output_tsv": true,
    "output_invalid_isbn_file": true
  }
}
```

Save to: `config/profiles/academic_books.json`

---

## 🔧 Advanced Features

### **Unsaved Changes Detection**

The system automatically detects when you modify settings:
- **● Unsaved changes** indicator appears
- **💾 Save** button becomes enabled
- Warning when switching profiles with unsaved changes

### **Active Profile Persistence**

Your last-used profile is remembered:
- Stored in `config/active_profile.txt`
- Automatically loaded on app restart
- Survives app crashes

### **Profile Validation**

Profiles are validated on load:
- Corrupted profiles are skipped
- Invalid settings use defaults
- Error messages guide you to fix issues

---

## 📝 Best Practices

### **1. Naming Conventions**

Use descriptive names:
- ✅ "Medical Books - Full Harvest"
- ✅ "Quick Test - No Retries"
- ❌ "Profile1"
- ❌ "Test"

### **2. Profile Organization**

Create profiles for:
- Different subject areas
- Different retry strategies
- Different output formats
- Different performance needs

### **3. Backup Important Profiles**

Profiles are just JSON files:
```bash
# Backup all profiles
cp -r config/profiles/ backup/profiles_2026-01-29/

# Restore a profile
cp backup/profiles_2026-01-29/academic_books.json config/profiles/
```

### **4. Share Profiles**

Send profile files to colleagues:
```bash
# Export
zip academic_setup.zip config/profiles/academic_books.json

# Import (on their machine)
unzip academic_setup.zip -d LCCN-Harvester-Project/
```

---

## 🐛 Troubleshooting

### **Q: Profile dropdown is empty?**
**A:** Check if `config/profiles/` directory exists and has read permissions.

### **Q: Changes not saving?**
**A:** Make sure you're not trying to modify "Default Settings". Use "Save As..." instead.

### **Q: Profile disappeared?**
**A:** Check `config/profiles/` folder. The JSON file should still exist.

### **Q: Settings reverting on restart?**
**A:** Make sure to click **💾 Save** before closing the app.

---

## 🎓 Client Requirements Met

### ✅ **Multiple Named Profiles**
Instead of just 3 settings (factory/last/session), you can now create **unlimited named profiles**.

### ✅ **Meaningful Names**
Profiles have descriptive names like "Academic Books" instead of generic labels.

### ✅ **Quick Loading**
Switch between profiles instantly with the dropdown.

### ✅ **Session-Only Mode**
"Use Session Only" allows temporary changes without saving.

### ✅ **Fully Portable**
Everything stored in app directory - works from USB stick!

---

## 🚀 Future Enhancements

Potential improvements:
- Import/Export profiles via GUI
- Profile templates marketplace
- Profile metadata (notes, tags)
- Profile comparison tool
- Batch profile operations

---

**Created by:** Ahmed
**Version:** 1.0
**Date:** 2026-01-29
