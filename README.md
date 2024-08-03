# Blender MDB & CANM Addon
Blender model/animation importer/exporter for Earth Defense Force 5 and 6 .mdb and .canm files. 
Blender version supported: 3.6
No guarantees on other versions, but also tested and working on 4.0 and 4.1.1
If you post your issues in other versions or any other problems you run into, i will see what i can do, reach out to me on the EDF discord.

## Download
https://github.com/Smileynator/blender-mdb-addon/archive/refs/heads/master.zip

Please leave any problems as an Issue with logs and screenshots if possible.
Very little error catching has been implemented, so expect some problems.

## Features
- Importing of any .mdb Model (EDF6 might have shader issues!)
- Exporting of any .mdb Model (EDF6 might have shader issues!)
- Importing of any .canm Animations on top of a model (EDF5 only)
- Exporting of any .canm Animations from a model (EDF5 only)
- Bone support
- Material variable support (Not material editing!)
- Mesh editing support
- Weight painting support
- UV Mapping support
- Animation Support

## Usage Notes
![image](https://github.com/Smileynator/blender-mdb-addon/assets/3433068/376663dc-c9ad-4190-a082-b8511b399f11)
- Install blender-mdb-addon-master.zip in Blender Preferences.
- Enable "Import-Export: Earth Defeense Force Formats" and save preferences.
- Import .mdb under "File->Import->Earth Defense Force Model (.mdb)"
- Export .mdb under "File->Export->Earth Defense Force Model (.mdb)"
- Import .canm under "File->Import->Earth Defense Force Animation (.canm)"
- Export .canm under "File->Export->Earth Defense Force Animation (.canm)"

# MDB Notes
Exporting will fail if the model contains N-gons. (Tangent space can only be computed for tris/quads)

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
 
# CANM Notes
Animations can only be imported for the skeleton they are means to go with. So match the CANM file with the MDB file it belongs with, and import the MDB first.

To get a CANM file, you need to extract them, and later re-add them to a CAS file. Use my packing tool for this: https://github.com/Smileynator/CAS-Processor

Animations only support Quaternion rotations, any other rotations will be ignored during export.

Animations have Scale support in theory, but the game rarely uses it, so it is largely untested.

Animations during export are optimized to minimize filesize and prevent channel overflow. To not run into the channel limitation, any bone that does not need pos/rot/scale, should delete those curves entirely. If you only need a starting value, stick to 1 keyframe at frame 1. This allows them to be optimized further. Values are rounded to the closest 2e-06, though this should not be practically visible to anyone.

The export will sample an Fcurve per increment of 1, until it reached the amount of keyframes the animation is supposed to have.
Importing creates 1 keyframe per frame. however this is not required for export, so you can safely delete a few frames to make animation easier.

Keep in mind that animations are being interpolated between by the game's CAS file. This means that unless CAS files are properly edited, removing entire animations or adding completely new animations instead of replacing existing ones, will likely cause problems.

If after modding the new CAS into the game, the character T-poses, something went wrong and needs to be looked into.

Custom Properties you should know about:
- The Armature object houses "missing bones" which is a list of bones that are in the CANM file but not present in the MDB. Scene Root is always there. These must be preserved for export to work.
- Every Animation has custom properties the CANM export requires
  - Duration - The actual duration in frames that playback takes in engine
  - Loop - Intention for the animation to be able to loop or not
  - Keyframes - Amount of keyframes in the animation (regardless if they actually exist or not, cannot be below 2)


## Extra Tools, Docs, and Links
Other Tools: https://github.com/KCreator/Earth-Defence-Force-Documentation/wiki/Tools

File formats:
- [MDB Format](https://github.com/KCreator/Earth-Defence-Force-Documentation/wiki/MDB-Format)
- [CANM Format](https://github.com/KCreator/Earth-Defence-Force-Documentation/wiki/CANM-Format)

Discord: https://discord.gg/edf

## License
EARTH DEFENSE FORCE is the registered trademark of SANDLOT and D3 PUBLISHER INC. This project is not affiliated with or endorsed by SANDLOT or D3 PUBLISHER INC in any way.

This work is licensed under a [Creative Commons Attribution-NonCommercial 4.0 International License](https://creativecommons.org/licenses/by-nc/4.0/) (CC BY-NC 4.0).
