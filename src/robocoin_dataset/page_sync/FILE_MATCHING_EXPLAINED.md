# How HTML Pages Find YAML and MP4 Files

## Simple Answer

The system uses **file naming convention** - all related files share the same base name:

```
dataset_name.yml    ← metadata
dataset_name.mp4    ← video
dataset_name.jpg    ← thumbnail
```

## How It Works

### Step 1: Load Dataset List

The app loads dataset information in one of two modes:

**JSON Mode (Fast):**
- Loads `consolidated_datasets.json` (single file with all metadata)
- Each entry has a key that is the dataset base name

**YAML Mode (Fallback):**
- Loads `data_index.json` (list of YAML files)
- Loads each `.yml` file individually
- Removes `.yml` extension to get base name

### Step 2: Construct File Paths

For each dataset, the app constructs URLs using the base name:

```javascript
const path = "dataset_name";  // base name extracted from YAML filename

// Construct URLs:
video_url = `./assets/videos/${path}.mp4`
thumbnail_url = `./assets/thumbnails/${path}.jpg`
yaml_url = `./assets/dataset_info/${path}.yml`
```

### Step 3: Display Content

The HTML uses these URLs to:
- Display video previews
- Show thumbnail images
- Access metadata for filters

## Example

For dataset: `unitree_g1_five_finger_hand_basket_storage_apple`

```
docs/
  assets/
    dataset_info/
      unitree_g1_five_finger_hand_basket_storage_apple.yml  ← metadata
    videos/
      unitree_g1_five_finger_hand_basket_storage_apple.mp4  ← video
    thumbnails/
      unitree_g1_five_finger_hand_basket_storage_apple.jpg  ← thumbnail
```

## Key Points

✅ **No database needed** - just consistent file names
✅ **Simple convention** - same base name + different extensions
✅ **Automatic matching** - JavaScript constructs paths programmatically
✅ **Works in both modes** - JSON (fast) or YAML (fallback)

## File Structure

```
docs/assets/
├── dataset_info/
│   ├── data_index.json           # List of all YAML files
│   ├── consolidated_datasets.json # [Optional] All metadata in one file
│   └── *.yml                      # Individual metadata files
├── videos/
│   └── *.mp4                      # Video files (same name as YAML)
└── thumbnails/
    └── *.jpg                      # Thumbnail images (same name as YAML)
```

## Code Reference

See `docs/js/app.js` lines 191-195 (JSON mode) and 310-315 (YAML mode) for the path construction logic.
