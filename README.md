# Blender MDB & CANM Addon
Blender model/animation importer/exporter for Earth Defense Force 5 and 6 .mdb and .canm files. 
Blender version supported: 3.6
No guarantees on other versions, but also tested and working on 4.0 and 4.1.1
If you post your issues in other versions or any other problems you run into, i will see what i can do, reach out to me on the EDF discord.
<img width="1495" height="783" alt="image" src="https://github.com/user-attachments/assets/5c73239b-4ae8-416a-889c-83685a706b1e" />


## How to mod
I assume the main use of this tool is to "get something into EDF 5 or 6". So here is a short list of pointers on how to achieve that.
 - Begin with a model closest to what you need from the game. 
   - Need a new playable character in EDF5? Import the ranger from EDF5.
   - Need a new gun for EDF6? Import a rifle from EDF6.
 - Alter/Replace the original meshes or animations
   - Do not rename anything, try to not introduce new shaders, do not touch the skeleton at all
   - Removing or introducing something completely new besides meshes, is usually not a good idea!
   - The game is very picky. It uses specific name lookups, and special values that i have to persist through blender
   - Losing those special values or the exact naming the game expects, can cause things to behave in unexpected ways, or usually just break
 - Do a quick export with minimal changes to check if nothing broke immediately
 - Finally, re-skin/weight paint and UV map the altered mesh to the existing skeleton bones if necessary
 - Do a final export and enjoy your modded content in the game!

For more details you can read into the many notes I provide below, in theory we can edit a lot, including the bones.
The problem is that editing the bones also means editing the animations, and certain bones are mandatory, but you will never know which ones until they are gone and the game breaks.
We are actively working on more and more support on the topic, but for now enjoy what we have, and push the envelope!

## Download
https://github.com/Smileynator/blender-mdb-addon/archive/refs/heads/master.zip

Please leave any problems as an Issue with logs and screenshots if possible.
Very little error catching has been implemented, so expect some problems.

## Features
- Importing and exporting EDF5/EDF6 .mdb models
- Importing and exporting EDF5/EDF6 .canm animations
- Bone support
- Editable MDB material parameters with lossless material-data preservation
- Mesh editing support
- Weight painting support
- UV Mapping support
- Animation Support & Additive Animation Support

## Usage Notes
![image](https://github.com/Smileynator/blender-mdb-addon/assets/3433068/376663dc-c9ad-4190-a082-b8511b399f11)
- Install blender-mdb-addon-master.zip in Blender Preferences.
- Enable "Import-Export: Earth Defense Force Formats" and save preferences.
- Import .mdb under "File->Import->Earth Defense Force Model (.mdb)"
- Export .mdb under "File->Export->Earth Defense Force Model (.mdb)"
- Import .canm under "File->Import->Earth Defense Force Animation (.canm)"
- Export .canm under "File->Export->Earth Defense Force Animation (.canm)"

# MDB Notes
MDB export requires every face to be triangulated. Export is canceled before writing if any quad or n-gon remains.

Each exported mesh must have exactly one non-empty material slot. MDB mesh
records reference one material, so meshes with no material or multiple Blender
material slots are rejected instead of guessed.

Legacy triangle-strip topology is recognized but not yet verified against a
real MDB sample. The importer cancels before creating scene data when it finds
a strip mesh, rather than interpreting its indices as an incorrect triangle
list. Please include the source MDB when reporting this error.

The exporter enforces the game's four-influence vertex limit. When a vertex has more than four positive bone weights, the four strongest are retained and normalized. Meshes with an Armature modifier but no actual positive weights are exported without unnecessary blend-index and blend-weight channels.
Weighted vertex groups are matched to MDB bones by name rather than Blender
group order. Export is canceled when a positively weighted group has no
matching bone. The bone table can contain more than 256 entries, but the
format's 8-bit blend indices can only weight vertices to bones at indices
0-255; export is canceled if a mesh weights a later bone.

Blender stores UVs and split normals per face corner while MDB stores them per vertex. Export therefore splits vertices where UVs, normals, or tangent-space data differ so seams remain intact.
The resulting exported vertex indices are 16-bit. A mesh that exceeds 65,536
vertices after seam splitting is rejected with an error.

Bone bounding boxes are always recomputed from the geometry being exported. Weighted vertices supply deform-bone bounds; matching same-named objects supply bounds for the unskinned bone groups observed to use rigid geometry. This is mandatory because preserved import-time bounds become invalid after geometry or rig edits.

Shader visuals in the Blender Editor do not reflect the in-game assets. No worries though, the game-visuals are preserved, and you can tweak default settings regardless!

Models make use of some extra data we cannot support in Blender. Those are stored as Custom Properties on the Bones, Animation strips and Materials to be used for export later.

Scenes imported with an older add-on version, should always start with a new fresh import. Keeping versions of the add-on backwards compatible was nearly impossible, and as of writing for 1.9.0 we largely expect the formatting to be stable and lossless. Older imports did not preserve
enough information for a reliable round trip, so the exporter deliberately cancels instead of guessing missing values.

## Editing MDB materials

The shader group in Blender has two related but distinct jobs:

1. Its unlinked numeric and color inputs expose parameters that actually exist in the imported MDB material. Edit these input values to change what is exported.
2. Its texture, normal, and other node connections produce a useful Blender preview. These connections are not themselves the MDB material record.

A connected Blender socket ignores its displayed fallback value. For example, `damage_normal` is an MDB texture binding rather than a stored vector. If its normal-map connection is removed, Blender displays the socket fallback `(0, 0, 0)`. That fallback is not an MDB value and does not overwrite the texture binding.

For lossless round trips:

- Disconnecting a texture node does not remove that texture from MDB export. Texture bindings are preserved independently of preview links.
- Connecting a Blender Value or RGB node to a numeric parameter does not export the evaluated connection. Edit the shader-group input's own value instead.
- Parameters and defaults that exist only in the shader preview lookup are never added to the exported MDB.
- Parameter order, declared type and component count, unused float slots, shader name, texture-table identity, and sampler overrides are retained separately when Blender has no native socket representation for them.
- Unknown shaders can still be imported and exported. They receive a generic editable preview containing the parameters and texture-slot names found in the MDB. Those might make bad assumptions or look aweful, but it does not affect the ingame look.

Shader previews are built from the capabilities present in each MDB material. 
Recognized parameter and slot names drive base colour, normals, transparency, packed texture channels, colour masks, damage overlays, emission, and facing-angle falloff. 
New shader names therefore receive the same treatment automatically when they use known material fields.

MDB does not store which UV set a shader samples. Numbered texture-slot names are handled automatically, while a small exception list preserves known UV selections for shaders whose slot names do not carry enough information. The retired shader table remains in the source tree only as a test oracle and is not imported by production code.

## Good things to know
Character hitboxes are not stored in the model nor animation file, these have to be edited externally (Havoc)

The game internally heavily relies on specific naming structures and layouts. Renaming or removing Bones, Materials and Entire Meshes is highly discouraged. Doing this will most likely result in incorrect functionality in game to some degree, or even cause crashing of the game.

Custom Properties you should know about:
- Bones preserve `participation_metadata`, signed `semantic_role`, and
  `normalized_bone_flag` custom properties. The exact authoring meaning of the
  first and runtime consumer of the last remain unconfirmed.
- Bone `bounds_half_size` and `bounds_center` custom properties contain the two
  bounding float4s. Export recomputes them from the edited geometry, they are just there in case you wanted to see them.
- Materials retain MDB identity and material-table metadata as well as some extra properties regarding rendering priority.
 
# CANM Notes
CANM import detects EDF5 (`512`) and EDF6 (`768`) automatically. Export provides separate EDF5 and EDF6 entries.

Animations can only be imported for the skeleton they are means to go with. So match the CANM file with the MDB file it belongs with, and import the MDB first.

To get a CANM file, you need to extract them, and later re-add them to a CAS file. Use my packing tool for this: 
https://github.com/Smileynator/CAS-Processor
Note that removing or adding whole animation clips away from the defaults, causes issues with the CAS format as it expects certain clips at certain indexes. It is not advised to do this for the time being.

Animations only support Blender Quaternion rotations, any other rotations will be ignored during export.

Animations during export are optimized to minimize filesize and prevent channel overflow. To not run into the channel limitation, any bone that does not need pos/rot/scale, should delete those curves entirely. If you only need a starting value, stick to 1 keyframe at frame 1. This allows them to be optimized further. Beyond that we try to merge curves where possible. The maximum limit is 65k curves over all animations.

The export will sample a Fcurve per increment of 1, until it reached the amount of keyframes the animation is supposed to have.
Importing creates 1 keyframe per frame. however this is not required for export, so you can safely delete a few frames to make animation easier.

Custom Properties you should know about:
- The Armature object houses "missing bones" which is a list of bones that are in the CANM file but not present in the MDB. Scene Root is always there. These must be preserved for export to work.
- Every Animation has custom properties the CANM export requires
  - Duration - The actual duration in frames that playback takes in engine
  - Loop - Intention for the animation to be able to loop or not
  - Keyframes - Amount of keyframes in the animation (regardless if they actually exist or not, cannot be below 2)

### Editing additive animations

CAS decides whether a CANM clip is composed on top of another pose. Imported additive clips therefore round-trip
correctly but usually look distorted when Blender displays them as ordinary standalone actions. (usually curls the model into a messy ball)

To start Additive animation editing select the armature and go into Pose mode.

Open **3D Viewport > Sidebar > Animation > EDF Additive
Animation**:

1. Choose **Start Additive Editing**.
2. Select the imported additive Action and a normal base Action.
3. Choose **Animated Action** to sample the base in CANM engine time, or
   **Fixed Frame** to hold one base sample for the whole edit.
4. Edit the generated `[Additive Edit]` Action as an ordinary pose animation.
5. Choose **Save Additive Editing** to convert the edited curves back into the
   original additive Action. **Cancel Additive Editing** discards the preview.
<img width="1277" height="661" alt="image" src="https://github.com/user-attachments/assets/5cfcc5ef-d62e-4e1d-9b74-b036f851288d" />
The source Action and all NLA tracks are left untouched until Save is chosen.
Their previous mute state is restored afterward. Only translation and
quaternion-rotation channels already present in the source additive Action are
written back; this prevents an accidental pose or keyframe from introducing
new CANM bone channels (Auto keying is a sin). Save stops with a clear error if the preview changed a
base-only, new, or scale channel, rather than silently discarding that edit.
Undo that channel edit or cancel the session. Additive scale curves are
preserved unchanged because CAS tag `0x08` takes scale from the base pose
rather than the additive operand, it is simply unsupported in additive animation.

Do not rename or delete the source, base, or preview Action during an editing
session, or edit the source/base Action through another editor. Save detects
those changes and stops rather than combining incompatible data. Complete or
cancel the session before exporting. The exporter rejects temporary additive
previews if one has manually been placed in an NLA track.

## Extra Tools, Docs, and Links
Other Tools: https://github.com/KCreator/Earth-Defence-Force-Documentation/wiki/Tools

File formats:
- [MDB Format](https://github.com/KCreator/Earth-Defence-Force-Documentation/wiki/MDB-Format)
- [CANM Format](https://github.com/KCreator/Earth-Defence-Force-Documentation/wiki/CANM-Format)

Discord: https://discord.gg/edf

## License
EARTH DEFENSE FORCE is the registered trademark of SANDLOT and D3 PUBLISHER INC. This project is not affiliated with or endorsed by SANDLOT or D3 PUBLISHER INC in any way.

This work is licensed under a [Creative Commons Attribution-NonCommercial 4.0 International License](https://creativecommons.org/licenses/by-nc/4.0/) (CC BY-NC 4.0).
