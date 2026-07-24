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
- Importing and exporting EDF5/EDF6 .mdb models
- Importing and exporting EDF5/EDF6 .canm animations
- Bone support
- Editable MDB material parameters with lossless material-data preservation
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
- Export .canm under the separate EDF5 and EDF6 animation entries in "File->Export"

# MDB Notes
MDB export requires every face to be triangulated. Export is cancelled before writing if any quad or n-gon remains.

Legacy triangle-strip topology is recognized but not yet verified against a
real MDB sample. The importer cancels before creating scene data when it finds
a strip mesh, rather than interpreting its indices as an incorrect triangle
list. Please include the source MDB when reporting this error.

The exporter enforces the game's four-influence vertex limit. When a vertex has more than four positive bone weights, the four strongest are retained and normalized. Meshes with an Armature modifier but no actual positive weights are exported without unnecessary blend-index and blend-weight channels.

Blender stores UVs and split normals per face corner while MDB stores them per vertex. Export therefore splits vertices where UVs, normals, or tangent-space data differ so seams remain intact.

Bone bounding boxes are always recomputed from the geometry being exported. Weighted vertices supply deform-bone bounds; matching same-named objects supply bounds for the unskinned bone groups observed to use rigid geometry. This is mandatory because preserved import-time bounds become invalid after geometry or rig edits.

Shader details might be incomplete, but most of the visual aspects should be there.

Models make use of some extra data we either cannot support in Blender or do not know what they exactly do. For the time being those are stored as Custom Properties on the Bones and Materials.

Scenes imported with add-on versions before the MDB metadata cleanup must be
re-imported from their source MDB before export. Older imports did not preserve
enough information for a reliable round trip, so the exporter deliberately
cancels instead of guessing missing values.

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
- Unknown shaders can still be imported and exported. They receive a generic editable preview containing the parameters and texture-slot names found in the MDB.

Each imported material includes an `MDB Editing Notes` frame in the Shader Editor containing a short version of these rules.

Shader previews are built from the capabilities present in each MDB material. 
Recognized parameter and slot names drive base colour, normals, transparency, packed texture channels, colour masks, damage overlays, emission, and facing-angle falloff. 
New shader names therefore receive the same treatment automatically when they use known material fields.

MDB does not store which UV set a shader samples. Numbered texture-slot names are handled automatically, while a small exception list preserves known UV selections for shaders whose slot names do not carry enough information. The retired shader table remains in the source tree only as a test oracle and is not imported by production code.

Model animations and hitboxes are not stored in the model file, these have to be edited externally.

The game internally heavily relies on specific naming structures we have not defined yet. So renaming or removing of Bones, Materials and Objects is highly discouraged. Doing this anyway might result in incorrect dismemberment mechanics, crashes during gameplay, broken animations, missing hitboxes, etc.

Try keeping editing of the materials to a minimal, mostly they are for setting up textures as well as default variables the game uses, the rest is purely there to ensure blender renders it somewhat properly as a preview.

Custom Properties you should know about:
- Bones preserve `participation_metadata`, signed `semantic_role`, and
  `normalized_bone_flag` custom properties. The exact authoring meaning of the
  first and runtime consumer of the last remain unconfirmed.
- Bone `bounds_half_size` and `bounds_center` custom properties contain the two
  bounding float4s. Export recomputes them from the edited geometry.
- Materials retain MDB identity and material-table metadata in addition to the following render properties.
  - `draw_priority` is literal ordering within render-queue class 2. A higher
    value is submitted later.
  - `render_queue_class` is normally 0, while class 2 is used by transparent
    and UI elements.
  - `render_participation_flags` is normally 3. Bit 0 enables shadow casting;
    value 2 is observed on transparent UI and barrier materials.
 
# CANM Notes
CANM import detects EDF5 (`512`) and EDF6 (`768`) automatically. Export provides separate EDF5 and EDF6 entries. EDF6 rotation channels use absolute quaternions and their keyframe block is written with 16-byte alignment.

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
