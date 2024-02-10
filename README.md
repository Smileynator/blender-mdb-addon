# Blender MDB Addon
Incomplete blender importer/exporter for Earth Defense Force 4.1 & 5's .mdb files.  
Supported versions of blender are 2.90 to 4.0.2, newer versions not guaranteed.

Importing should work for anything but the shader details.
All textures are imported, but only albedo and normal textures are connected to materials.

Exporting should work largely, but missing data causes the game to be unstable and models to be inconsistent.

## Download
https://github.com/Smileynator/blender-mdb-addon/archive/refs/heads/export.zip

## Extra Tools
https://github.com/wmltogether/CriPakTools/releases  
https://gitlab.com/kittopiacreator/edf-tools/-/raw/master/Release/EDF%20Tools.exe

## Usage
Use CriPakGUI to extract the game's CPK archives.  
Use EDF Tools.exe to extract the game's RAB/MRAB into models and textures.  
Install blender-mdb-addon-master.zip in Blender Preferences.  
Enable "Import-Export: MDB format" and save preferences.

Import .mdb under "File->Import->Earth Defense Force (.mdb)"
Export .mdb under "File->Export->Earth Defense Force (.mdb)"

EARTH DEFENSE FORCE is the registered trademark of SANDLOT and D3 PUBLISHER INC. This project is not affiliated with or endorsed by SANDLOT or D3 PUBLISHER INC in any way.
