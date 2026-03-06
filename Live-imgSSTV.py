import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import time
import subprocess
import platform
import serial
import re
from datetime import datetime
import shutil

# =========================================================================================

# User Settings

Save_Original_Image = 0 # 0 = The original image is not saved - 1 = The original image is saved in the ‘originalimg’ directory


User_Text = "IU0XXX"    # Enter the callsign or text you want to display in the final image.


Image_Verification = 1  # 0 = Do not check whether the image is the same as the previous one.  - 1 = Check whether the image is the same as the previous one. 

# RS41-SDE Configuration

Save_File = 0           # 0 = Weather data is not saved in a .txt file - 1 = Weather data is saved in a .txt file
File_Path = "File_Path" # Specify the file path where you want to save the .txt file with the weather data. 

PORT = ''
BAUD = 9600
TIMEOUT = 1
DELAY_AFTER_CMD = 1.5
P0_HPA = 1013.25


directory_input = ""    # Enter the file path from which to retrieve the image
directory = Path(directory_input)

# =========================================================================================


if not directory.is_dir():
    print("Error: the directory does not exist.")
    exit()



estensioni = (".jpg", ".jpeg", ".png")

immagini = [
    f for f in directory.iterdir()
    if f.suffix.lower() in estensioni and f.is_file()
]

if len(immagini) == 0:
    print("Error: no images found in the directory.")
    exit()

if len(immagini) > 1:
    print("Error: there must be only one image in the directory.")
    exit()

image_path = immagini[0]
print(f"Img found {image_path}")



# Check image update

if Image_Verification == 1:

    timestamp_file = directory / ".last_timestamp"
    current_timestamp = int(image_path.stat().st_mtime)

    if timestamp_file.exists():
        try:
            previous_timestamp = int(timestamp_file.read_text().strip())
        except ValueError:
            previous_timestamp = 0
    else:
        previous_timestamp = 0

    if current_timestamp != previous_timestamp:
        risultato_img = "0"
    else:
        risultato_img = "1"

    timestamp_file.write_text(str(current_timestamp))

else:

    risultato_img = "0"



# Save original image

script_dir = Path(__file__).resolve().parent

if Save_Original_Image == 1:

    original_folder = script_dir / "originalimg"
    original_folder.mkdir(exist_ok=True)

    save_original_path = original_folder / image_path.name

    if save_original_path.exists():

        base_name = image_path.stem
        extension = image_path.suffix
        counter = 1

        while True:

            new_name = f"{base_name}_{counter}{extension}"
            save_original_path = original_folder / new_name

            if not save_original_path.exists():
                break

            counter += 1

    shutil.copy2(image_path, save_original_path)

    print(f"Original image saved in: {save_original_path}")



# Format conversion 

img = Image.open(image_path)

width, height = img.size

target_ratio = 2 / 1
current_ratio = width / height

if current_ratio > target_ratio:

    new_width = int(height * target_ratio)
    left = (width - new_width) // 2
    box = (left, 0, left + new_width, height)

else:

    new_height = int(width / target_ratio)
    top = (height - new_height) // 2
    box = (0, top, width, top + new_height)

cropped = img.crop(box)



cropped_folder = script_dir / "Cropped"
cropped_folder.mkdir(exist_ok=True)

output_path = cropped_folder / f"cropped_{image_path.name}"
cropped.save(output_path)

print(f"Adapted image saved in:  {output_path}")

time.sleep(2)



# RS41-SDE

RE_TEMP = re.compile(r'\bT:\s*([-+]?[0-9]+\.[0-9]+)')
RE_UMID = re.compile(r'\bRH:\s*([0-9]+\.[0-9]+)')
RE_PRES = re.compile(r'\bPressure:\s*([0-9]+\.[0-9]+)')

def send_command(ser, cmd, newline=True, delay=DELAY_AFTER_CMD):

    if newline:
        ser.write((cmd + '\r\n').encode())
    else:
        ser.write(cmd.encode())

    time.sleep(delay)

    return ser.read_all().decode(errors='ignore')

def estrai_dati(text):

    dati = {}

    m1 = RE_TEMP.search(text)
    m2 = RE_UMID.search(text)
    m3 = RE_PRES.search(text)

    if m1:
        dati['Temperature'] = float(m1.group(1))

    if m2:
        dati['Humidity'] = float(m2.group(1))

    if m3:
        dati['Atm_Pressure'] = float(m3.group(1))

    return dati

def pressione_to_altitudine(p_hpa, p0_hpa=P0_HPA):

    if p_hpa is None or p_hpa <= 0:
        return None

    altitudine = 44330.0 * (1.0 - (p_hpa / p0_hpa) ** (1.0 / 5.255))
    return round(altitudine + 60.0, 2)



# RS41 data reading

out = ""
ser = None

try:

    ser = serial.Serial(PORT, baudrate=BAUD, timeout=TIMEOUT)

    ser.reset_input_buffer()

    ser.write(b'S')
    time.sleep(DELAY_AFTER_CMD)

    out = ser.read_all().decode(errors='ignore')

    if "RH:" not in out:

        ser.write(b'Twsv\r\n')
        time.sleep(3)

        out = send_command(ser, "S")

except serial.SerialException as e:

    print(f"Serial port error {e}")
    out = ""

finally:

    if ser is not None:
        ser.close()



# Data Extraction 

dati = estrai_dati(out)

altitudine = pressione_to_altitudine(dati.get('Atm_Pressure')) if 'Atm_Pressure' in dati else None
temperatura = dati.get('Temperature')
umidita = dati.get('Humidity')
pressione = dati.get('Atm_Pressure')


altitudine_img = altitudine if altitudine is not None else "OUT"
temperatura_img = temperatura if temperatura is not None else "OUT"
umidita_img = umidita if umidita is not None else "OUT"
pressione_img = pressione if pressione is not None else "OUT"

if all(v == "OUT" for v in [altitudine_img, temperatura_img, umidita_img, pressione_img]):
    risultato_RS41 = "1"
else:
    risultato_RS41 = "0"



# Generating images from text

bg_color = "#272727"
text_color = "#FFFFFF"

output_folder = script_dir / "imgdata"
output_folder.mkdir(exist_ok=True)

font_path = script_dir / "font" / "Montserrat-Bold.ttf"

def crea_immagine_testo(testo, larghezza, altezza, nome_file):
    testo = str(testo)
    max_font_size = 60

    for font_size in range(max_font_size, 5, -1):
        font = ImageFont.truetype(str(font_path), font_size)
        dummy = Image.new("RGB", (1, 1))
        draw_dummy = ImageDraw.Draw(dummy)
        bbox = draw_dummy.textbbox((0, 0), testo, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        if text_width <= larghezza - 4 and text_height <= altezza - 4:
            break

    img = Image.new("RGB", (larghezza, altezza), color=bg_color)
    draw = ImageDraw.Draw(img)
    x = (larghezza - text_width) // 2
    y = (altezza - text_height) // 2 - bbox[1]
    draw.text((x, y), testo, font=font, fill=text_color)
    img.save(output_folder / nome_file)


crea_immagine_testo(altitudine_img, 136, 48, "altitudine.png")
crea_immagine_testo(temperatura_img, 94, 48, "temperatura.png")
crea_immagine_testo(umidita_img, 136, 48, "umidita.png")
crea_immagine_testo(pressione_img, 140, 48, "pressione.png")
crea_immagine_testo(User_Text, 630, 48, "callsign.png")



# Template Selection

template_folder = script_dir / "template"


if risultato_img == "0" and risultato_RS41 == "0":
    template_file = template_folder / "1.png"

elif risultato_img == "0" and risultato_RS41 == "1":
    template_file = template_folder / "2.png"

elif risultato_img == "1" and risultato_RS41 == "0":
    template_file = template_folder / "3.png"
else:
    
    backup_path = template_folder / "backup.png"
    if backup_path.exists():
        template = Image.open(backup_path)
        final_folder = script_dir / "final"
        final_folder.mkdir(exist_ok=True)
        final_path = final_folder / "final.png"
        template.save(final_path)
        print(f"No data or images available.  {final_path}")
        exit()
    else:
        print("Backup not found")
        exit()


if 'template' not in locals():
    template = Image.open(template_file)

template_width, template_height = template.size



# Overlap

if risultato_img == "1" and risultato_RS41 == "0":
    img_top_path = template_folder / "img.png"
    if img_top_path.exists():
        img_top = Image.open(img_top_path)
        template.paste(img_top, (0, 0))


callsign = Image.open(output_folder / "callsign.png")
template.paste(callsign, (5, template_height - 118 - callsign.height))


if risultato_RS41 == "0":
    posizioni = {
        "altitudine.png": (114, 50),
        "umidita.png": (114, 2),
        "temperatura.png": (459, 50),
        "pressione.png": (378, 2)
    }
    for nome, (left, bottom) in posizioni.items():
        img_path = output_folder / nome
        if img_path.exists():
            img_data = Image.open(img_path)
            x = left
            y = template_height - bottom - img_data.height
            template.paste(img_data, (x, y))


if risultato_img == "0":
    img_camera = Image.open(output_path)
    width, height = img_camera.size
    new_width = 640
    new_height = int((new_width / width) * height)
    img_camera = img_camera.resize((new_width, new_height))
    template.paste(img_camera, (0, 0))



# Saving the final image

final_folder = script_dir / "final"
final_folder.mkdir(exist_ok=True)
final_path = final_folder / "final.png"
template.save(final_path)
print(f"Final img saved {final_path}")

# Detect OS
sistema = platform.system()  # 'Windows', 'Linux'

script_dir = Path(__file__).resolve().parent

if sistema == "Windows":
    sstv_script = script_dir / "sstv.bat"
else:
    sstv_script = script_dir / "sstv.sh"

if not sstv_script.exists():
    raise FileNotFoundError(f"SSTV script not found {sstv_script}")

try:
    subprocess.run(str(sstv_script), check=True)
    print(f"{sstv_script.name}")
except subprocess.CalledProcessError as e:
    print(f"Error while executing the script {e}")