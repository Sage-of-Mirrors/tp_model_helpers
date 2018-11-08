
import sys
import os
from io import BytesIO
from subprocess import call
from collections import OrderedDict
from PIL import Image
import re
import json

sys.path.insert(0, "./wwrando")
from fs_helpers import *
from wwlib.rarc import RARC
from wwlib.texture_utils import *
from wwlib.bti import *

class ModelConversionError(Exception):
  pass

def convert_to_bdl(base_folder, file_base_name, superbmd_folder="SuperBMD"):
  in_dae_path      = os.path.join(base_folder, file_base_name + ".dae")
  out_bdl_path     = os.path.join(base_folder, file_base_name + ".bdl")
  tex_headers_path = os.path.join(base_folder, "tex_headers.json")
  materials_path   = os.path.join(base_folder, "materials.json")
  
  # Check through the .dae file to see if there are any instances of <v/>, which would cause the "Invalid contents in element "n"" error when SuperBMD tries to read the file.
  with open(in_dae_path) as f:
    dae_contents = f.read()
  matches = re.findall(
    r"<input semantic=\"WEIGHT\" source=\"#skeleton_root_([^\"]+?)-skin-weights\" offset=\"\d+\"/>\s*" + \
    r"<vcount>[^<]+</vcount>\s*" + \
    "<v/>",
    dae_contents,
    re.MULTILINE
  )
  if matches:
    raise ModelConversionError("Error: All of the vertices in the following meshes are unweighted: " + (", ".join(matches)))
  
  print("Converting %s to BDL" % in_dae_path)
  
  if os.path.isfile(out_bdl_path):
    os.remove(out_bdl_path)
  
  command = [
    os.path.join(superbmd_folder, "SuperBMD.exe"),
    "-i", in_dae_path,
    "-o", out_bdl_path,
    "-x", tex_headers_path,
    "-m", materials_path,
    "-t", "all",
    "--bdl",
  ]
  
  result = call(command)
  
  if result != 0:
    input()
    sys.exit(1)
  
  return out_bdl_path

def unpack_sections(bdl_path):
  with open(bdl_path, "rb") as f:
    data = BytesIO(f.read())
  
  return unpack_sections_by_data(data)
  
def unpack_sections_by_data(data):
  bdl_size = data_len(data)
  
  sections = OrderedDict()
  
  sections["header"] = BytesIO(read_bytes(data, 0, 0x20))
  
  offset = 0x20
  while offset < bdl_size:
    section_magic = read_str(data, offset, 4)
    section_size = read_u32(data, offset+4)
    sections[section_magic] = BytesIO(read_bytes(data, offset, section_size))
    
    offset += section_size
  
  return sections

def pack_sections(sections):
  data = BytesIO()
  for section_name, section_data in sections.items():
    section_data.seek(0)
    data.write(section_data.read())
  
  return data

def copy_original_sections(out_bdl_path, orig_bdl_path, sections_to_copy):
  sections = unpack_sections(out_bdl_path)
  orig_sections = unpack_sections(orig_bdl_path)
  
  for section_magic in sections_to_copy:
    sections[section_magic] = orig_sections[section_magic]
  
  data = pack_sections(sections)
  
  size = data_len(data)
  write_u32(data, 8, size)
  
  with open(out_bdl_path, "wb") as f:
    data.seek(0)
    f.write(data.read())
  
  return data



def convert_all_player_models(orig_link_folder, custom_player_folder, repack_hands_model=False):
  orig_link_arc_path = os.path.join(orig_link_folder, "Link.arc")
  with open(orig_link_arc_path, "rb") as f:
    rarc_data = BytesIO(f.read())
  link_arc = RARC(rarc_data)
  
  
  all_model_basenames = []
  all_texture_basenames = []
  for file_entry in link_arc.file_entries:
    if file_entry.is_dir:
      continue
    basename, file_ext = os.path.splitext(file_entry.name)
    if file_ext == ".bdl":
      all_model_basenames.append(basename)
    if file_ext == ".bti":
      all_texture_basenames.append(basename)
  
  
  for model_basename in all_model_basenames:
    if model_basename == "hands" and not repack_hands_model:
      continue
    
    new_model_folder = os.path.join(custom_player_folder, model_basename)
    if os.path.isdir(new_model_folder):
      out_bdl_path = convert_to_bdl(new_model_folder, model_basename)
      orig_bdl_path = os.path.join(orig_link_folder, model_basename, model_basename + ".bdl")
      
      sections_to_copy = []
      if model_basename == "cl":
        sections_to_copy.append("INF1")
        sections_to_copy.append("JNT1")
      
      link_arc.get_file_entry(model_basename + ".bdl").data = copy_original_sections(out_bdl_path, orig_bdl_path, sections_to_copy)
  
  for texture_basename in all_texture_basenames:
    # Create texture BTI from PNG
    casual_tex_png = os.path.join(custom_player_folder, texture_basename + ".png")
    if os.path.isfile(casual_tex_png):
      image = Image.open(casual_tex_png)
      texture = link_arc.get_file(texture_basename + ".bti")
      
      tex_header_json_path = os.path.join(custom_player_folder, texture_basename + "_tex_header.json")
      if os.path.isfile(tex_header_json_path):
        with open(tex_header_json_path) as f:
          tex_header = json.load(f)
        
        if "Format" in tex_header:
          texture.image_format = ImageFormat[tex_header["Format"]]
        if "PaletteFormat" in tex_header:
          texture.palette_format = PaletteFormat[tex_header["PaletteFormat"]]
        if "WrapS" in tex_header:
          texture.wrap_s = WrapMode[tex_header["WrapS"]]
        if "WrapT" in tex_header:
          texture.wrap_t = WrapMode[tex_header["WrapT"]]
        if "MagFilter" in tex_header:
          texture.mag_filter = FilterMode[tex_header["MagFilter"]]
        if "MinFilter" in tex_header:
          texture.min_filter = FilterMode[tex_header["MinFilter"]]
        if "AlphaSetting" in tex_header:
          texture.alpha_setting = tex_header["AlphaSetting"]
        if "LodBias" in tex_header:
          texture.lod_bias = tex_header["LodBias"]
        if "unknown2" in tex_header:
          texture.unknown_2 = tex_header["unknown2"]
        if "unknown3" in tex_header:
          texture.unknown_3 = tex_header["unknown3"]
      
      texture.replace_image(image)
      texture.save_changes()
      casual_tex_bti = os.path.join(custom_player_folder, texture_basename + ".bti")
      with open(casual_tex_bti, "wb") as f:
        texture.file_entry.data.seek(0)
        f.write(texture.file_entry.data.read())
    
    # Import texture BTI
    casual_tex_bti = os.path.join(custom_player_folder, texture_basename + ".bti")
    if os.path.isfile(casual_tex_bti):
      with open(casual_tex_bti, "rb") as f:
        data = BytesIO(f.read())
        link_arc.get_file_entry(texture_basename + ".bti").data = data
  
  if not repack_hands_model:
    # Import hands texture
    hands_tex_png = os.path.join(custom_player_folder, "hands", "handsS3TC.png")
    if os.path.isfile(hands_tex_png):
      image = Image.open(hands_tex_png)
      hands_model = link_arc.get_file("hands.bdl")
      textures = hands_model.tex1.textures_by_name["handsS3TC"]
      for texture in textures:
        texture.replace_image(image)
      hands_model.save_changes()
      link_arc.get_file_entry("hands.bdl").data = hands_model.file_entry.data
  
  
  # Print out changed file sizes
  with open(orig_link_arc_path, "rb") as f:
    rarc_data = BytesIO(f.read())
  orig_link_arc = RARC(rarc_data)
  for file_entry in link_arc.file_entries:
    orig_file_entry = orig_link_arc.get_file_entry(file_entry.name)
    if file_entry.is_dir:
      continue
    if data_len(orig_file_entry.data) == data_len(file_entry.data):
      continue
    print("File %s, orig size %X, new size %X" % (file_entry.name, data_len(orig_file_entry.data), data_len(file_entry.data)))
  
  link_arc.save_changes()
  link_arc_out_path = os.path.join(custom_player_folder, "Link.arc")
  with open(link_arc_out_path, "wb") as f:
    link_arc.data.seek(0)
    f.write(link_arc.data.read())

if __name__ == "__main__":
  args_valid = False
  repack_hands = False
  if len(sys.argv) == 5 and sys.argv[1] == "-link" and sys.argv[3] == "-custom":
    args_valid = True
  elif len(sys.argv) == 6 and sys.argv[1] == "-link" and sys.argv[3] == "-custom" and sys.argv[5] == "-repackhands":
    args_valid = True
    repack_hands = True
  
  if not args_valid:
    print("Invalid arguments. Proper format:")
    print("  pack_player -link \"Path/To/Clean/Link/Folder\" -custom \"Path/To/Custom/Model/Folder\"")
    print("Or, if you want to modify the hands.bdl model and not just its texture, include the -repackhands argument:")
    print("  pack_player -link \"Path/To/Clean/Link/Folder\" -custom \"Path/To/Custom/Model/Folder\" -repackhands")
    sys.exit(1)
  
  orig_link_folder = sys.argv[2]
  if not os.path.isdir(orig_link_folder):
    print("Clean link folder does not exist: %s" % orig_link_folder)
    sys.exit(1)
  
  custom_player_folder = sys.argv[4]
  if not os.path.isdir(custom_player_folder):
    print("Custom player folder does not exist: %s" % custom_player_folder)
    sys.exit(1)
  
  superbmd_path = os.path.join("SuperBMD", "SuperBMD.exe")
  if not os.path.isfile(superbmd_path):
    print("SuperBMD not found. SuperBMD.exe must be located in the SuperBMD folder.")
    sys.exit(1)
  
  try:
    convert_all_player_models(orig_link_folder, custom_player_folder, repack_hands_model=repack_hands)
  except ModelConversionError as e:
    print(e)
    sys.exit(1)
