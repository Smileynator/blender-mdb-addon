# Blender MDB Addon
Blender model importer/exporter for Earth Defense Force (4.1?) & 5's .mdb files.  
Supported versions of blender are 2.90 to 4.0.2, newer versions not guaranteed.

## Download
https://github.com/Smileynator/blender-mdb-addon/archive/refs/heads/master.zip

Please leave any problems as an Issue with logs and screenshots if possible.
Very little error catching has been implemented, so expect some problems.

## Features
- Importing of any .mdb Model
- Exporting of any .mdb Model
- Bone support
- Material variable support (Not material editing!)
- Mesh editing support
- Weight painting support
- UV Mapping support

## Usage Notes and Warnings
- Install blender-mdb-addon-master.zip in Blender Preferences.
- Enable "Import-Export: MDB format" and save preferences.
- Import .mdb under "File->Import->Earth Defense Force (.mdb)"
- Export .mdb under "File->Export->Earth Defense Force (.mdb)"

Shader details might be incomplete, but most of the visual aspects should be there.

Models make use of some extra data we either cannot support in Blender or do not know what they exactly do. For the time being those are stored as Custom Properties on the Bones and Materials.

Model animations and hitboxes are not stored in the model file, these have to be edited externally.

The game interally heavily relies on specific naming structures we have not defined yet. So renaming or removing of Bones, Materials and Objects is highly discouraged. Doing this anyway might result in incorrect dismemberment mechanics, crashes during gameplay, broken animations, missing hitboxes, etc.

Try keeping editing of the materials to a minimal, mostly they are for setting up textures as well as default variables the game uses, the rest is purely there to ensure blender renders it somewhat properly as a preview.

Custom Properties you should know about:
- Bones have 'unknown_ints[0]' that might be related to groupings. the value 3 seems to be assigned to all bones that actually need to hold meshes that have weight painting.
- Materials have 3 custom properties.
  - Render Priority is literral ordering. If 2 transparent objects exist, and one has higher render priority, it will show up in the front.
  - Render Layer is normally 0 for opaque objects, and 2 on transparent and UI elements.
  - Render Type is almost always 3, but seems to be set to 2 for objects which "update" their texture, like fill bars, or the shield bearer's shield.

## Extra Tools, Docs, and Links
Tools: https://github.com/KCreator/Earth-Defence-Force-Documentation/wiki/Tools

File format: https://github.com/KCreator/Earth-Defence-Force-Documentation/wiki/MDB-Format

Discord: https://discord.gg/edf

EARTH DEFENSE FORCE is the registered trademark of SANDLOT and D3 PUBLISHER INC. This project is not affiliated with or endorsed by SANDLOT or D3 PUBLISHER INC in any way.
