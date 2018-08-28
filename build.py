
from zipfile import ZipFile

with ZipFile("./dist/WW_Model_Helpers.zip", "w") as zip:
  zip.write("./dist/extract_models.exe", arcname="extract_models.exe")
  zip.write("./dist/pack_player.exe", arcname="pack_player.exe")
  zip.write("README.md", arcname="README.txt")
