# Blender MDB Addon
Blender model importer/exporter for Earth Defense Force 4.1 & 5's .mdb files.  
Supported versions of blender are 2.90 to 4.0.2, newer versions not guaranteed.

## Download
https://github.com/Smileynator/blender-mdb-addon/archive/refs/heads/master.zip

## Features
- Importing of any .mdb Model
- Exporting of any .mdb Model
- Bone support
- Material support
- Mesh editing support
- Weight painting support
- UV Mapping support

## Usage Notes and Warnings
Install blender-mdb-addon-master.zip in Blender Preferences.  
Enable "Import-Export: MDB format" and save preferences.
Import .mdb under "File->Import->Earth Defense Force (.mdb)"
Export .mdb under "File->Export->Earth Defense Force (.mdb)"

Shader details might be incomplete, but most of the visual aspects should be there.
Models make use of some extra data we either cannot support in Blender or do not know what they exactly do. For the time being those are stored as Custom Properties on the Bones and Materials.
Model animations and hitboxes are not stored in the model file, these have to be edited externally.
The game interally heavily relies on specific naming structures we have not defined yet. So renaming or removing of Bones and Objects is highly discouraged. Doing this any way might result in incorrect dismemberment mechanics, crashes during gameplay, broken animations, missing hitboxes, etc.

## Extra Tools, Docs, and Links
Tools: https://github.com/KCreator/Earth-Defence-Force-Documentation/wiki/Tools
File format: https://github.com/KCreator/Earth-Defence-Force-Documentation/wiki/MDB-Format
Discord: https://discord.gg/edf

EARTH DEFENSE FORCE is the registered trademark of SANDLOT and D3 PUBLISHER INC. This project is not affiliated with or endorsed by SANDLOT or D3 PUBLISHER INC in any way.
