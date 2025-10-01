import re

from PIL import ImageFont
from PIL import Image, ImageDraw

import streamlit as st
from streamlit_cropper import st_cropper

import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import (
    SquareModuleDrawer,
    CircleModuleDrawer,
    GappedSquareModuleDrawer
)
from qrcode.image.styles.moduledrawers import VerticalBarsDrawer, HorizontalBarsDrawer

import requests

import base64
from io import BytesIO

def hex_to_rgba(hex_color, alpha=0):
    hex_color = hex_color.lstrip('#')
    lv = len(hex_color)
    rgb = tuple(int(hex_color[i:i + lv // 3], 16) for i in range(0, lv, lv // 3))
    return rgb + (alpha,)

def apply_background_color(im, color_hex):
    bg_rgba = hex_to_rgba(color_hex, alpha=255)
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    background = Image.new("RGBA", im.size, bg_rgba)
    alpha = im.split()[3]
    background.paste(im, mask=alpha)
    return background

def to_base64(img, img_format="PNG"):
    buffered = BytesIO()
    if img_format == "JPEG" and img.mode in ("RGBA", "LA"):
        img = img.convert("RGB")
    img.save(buffered, format=img_format)
    b64_str = base64.b64encode(buffered.getvalue()).decode()
    return b64_str

def fold_base64_string(b64_str: str, line_length=75):
    return '\n '.join(b64_str[i:i+line_length] for i in range(0, len(b64_str), line_length))


def make_circle_avatar_with_inner_border(img, diameter, border):
    # A végleges átmérő: diameter (külső kör)
    # Belső kép átmérője: diameter - 2*border
    img_size = diameter - 2 * border
    img_cropped = img.resize((img_size, img_size))

    # Körmaszk képhez
    inner_mask = Image.new("L", (img_size, img_size), 0)
    draw = ImageDraw.Draw(inner_mask)
    draw.ellipse((0, 0, img_size, img_size), fill=255)

    # Körbe vágott kép
    circle_img = Image.new("RGBA", (img_size, img_size), (0, 0, 0, 0))
    circle_img.paste(img_cropped, (0, 0), mask=inner_mask)

    # Border + kép kompozíció
    final_img = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    draw_final = ImageDraw.Draw(final_img)
    draw_final.ellipse((0, 0, diameter, diameter), fill=(255, 255, 255, 255))  # Fehér kör
    final_img.paste(circle_img, (border, border), mask=inner_mask)
    return final_img

def make_square_avatar_with_inner_border(img, diameter, border, corner_radius=0):
    """
    Négyzet alakú avatar belső kerettel és opcionális lekerekített sarkokkal.
    - img: input kép (PIL Image)
    - diameter: a kész kép kívánt külső mérete (szélesség és magasság)
    - border: a belső fehér keret vastagsága pixelben
    - corner_radius: a sarkok lekerekítési sugara pixelben (0 = éles sarkok)
    """
    img_size = diameter - 2 * border
    img_cropped = img.resize((img_size, img_size))


    # Maszk lekerekített négyzethez
    mask = Image.new("L", (img_size, img_size), 0)
    draw = ImageDraw.Draw(mask)
    if corner_radius > 0:
        draw.rounded_rectangle((0, 0, img_size, img_size), radius=corner_radius, fill=255)
    else:
        draw.rectangle((0, 0, img_size, img_size), fill=255)


    # Körbe vágott vagy lekerekített kép
    square_img = Image.new("RGBA", (img_size, img_size), (0, 0, 0, 0))
    square_img.paste(img_cropped, (0, 0), mask=mask)


    # Border + kép kompozíció (fehér háttér, lekerekített sarokkal, ha corner_radius > 0)
    final_img = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    draw_final = ImageDraw.Draw(final_img)
    if corner_radius > 0:
        draw_final.rounded_rectangle((0, 0, diameter, diameter), radius=corner_radius, fill=(255, 255, 255, 255))
    else:
        draw_final.rectangle((0, 0, diameter, diameter), fill=(255, 255, 255, 255))


    final_img.paste(square_img, (border, border), mask=mask)
    return final_img


# Fejlett szöveg rajzoló fix magassággal és sorok közti távolsággal
def draw_multiline_text_fixed_height(text_lines, width, height, font, line_spacing=12, text_color=(0, 0, 0)):
    text_img = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(text_img)

    total_text_height = sum([font.getbbox(line)[3] - font.getbbox(line)[1] for line in text_lines]) + line_spacing * (len(text_lines) - 1)
    y_offset = max((height - total_text_height) // 2, 0)

    for line in text_lines:
        bbox = font.getbbox(line)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (width - w) // 2  # horizontálisan középre igazítás
        draw.text((x, y_offset), line, font=font, fill=text_color)
        y_offset += h + line_spacing

    return text_img

font = ImageFont.load_default()  # vagy adj meg egy saját ttf fájlt

# Alap céglogó betöltése
try:
    logo_url = "https://raw.githubusercontent.com/dfajtai/streamlit_apps/main/medicopus_vcard/assets/medicopus_logo.png"
    response = requests.get(logo_url)
    company_logo = Image.open(BytesIO(response.content)).convert("RGBA")
except Exception:
    company_logo = None

# vCard mező konfiguráció default értékekkel
fields = [
    {"label": "Név", "key": "FN", "valid": r'^[\w\söüóőúéáí]+$', "enabled": True, "default": ""},
    {"label": "Munkahely", "key": "ORG", "valid": r'^.*$', "enabled": True, "default": "Medicopus Nonprofit Ltd."},
    {"label": "Beosztás", "key": "TITLE", "valid": r'^.*$', "enabled": True, "default": ""},
    {"label": "Email cím", "key": "EMAIL", "valid": r'^[\w\.-]+@[\w\.-]+\.\w+$', "enabled": True, "default": "info@medicopus.hu"},
    {"label": "Telefonszám", "key": "TEL", "valid": r'^\+?\d{8,15}$', "enabled": True, "default": "+3682502081"},
    {"label": "Weboldal", "key": "URL", "valid": r'^https?:\/\/.*', "enabled": True, "default": "https://medicopus.hu"},
    {"label": "Munkahelyi cím", "key": "ADR", "valid": r'^.*$', "enabled": True, "default": ";;Guba Sándor utca 40;Kaposvár;Somogy;7400;HUNGARY"},
    {"label": "GPS koordináták (latitúdó; hosszúság)", "key": "GEO", "valid": r'^-?\d+(\.\d+)?;-?\d+(\.\d+)?$', "enabled": True, "default": "46.381597197125714;17.82524855165998"},
]

st.title("Medicopus vCarc 3.0 generátor")

with st.sidebar.expander("Help / Súgó"):
    st.markdown("""
### Használati útmutató

Ez az alkalmazás QR-kódos névjegykártyát készít, amelyből vCard adat generálódik.

**Főbb funkciók:**  
- Adatok megadása és validálása (név, email, telefon, cím stb.)  
- QR-kód stílus és elrendezés választása  
- Kép vagy logó feltöltése, kör vagy lekerekített négyzet formában
- Állítható a keret vastagság, transzpanens képek háttere
- Profilkép forgatható (-90°, 0°, 90°)  
- Négyzet crop esetén állítható sarok lekerekítés 

**Tippek:**  
- A szelfi kamera feltöltése nem támogatott, ezért előzetesen készítsd el a képet!  
- A crop képarány 1:1, így a képet ehhez érdemes igazítani.  
- A kép kerete csak a végleges QR képben látható, a szerkesztőben nem feltétlen.

Használd szabadon, az elkészült névjegyek PNG vagy vCard formátumban tölthetők le.

""")

# Aktiválható mezők kiválasztó oldalsáv
active_fields = {}
with st.sidebar:
    st.header("Mezők kiválasztása")
    for field in fields:
        field["enabled"] = st.checkbox(field["label"], value=field["enabled"])
    st.markdown("---")

# Adatok kitöltése validációval és alapértékkel
st.header("Adatok kitöltése")
for field in fields:
    if field["enabled"]:
        value = st.text_input(field["label"], key=field["key"], value=field["default"])
        if value and not re.match(field["valid"], value):
            st.error(f"Hibás {field['label']} formátum.")
        active_fields[field["key"]] = value

# Profilkép kiválasztási mód
st.header("Profilkép opció")
img_choice = st.radio("Profilkép vagy logó választás:", ["Kép nélkül", "Logó használata", "Saját kép feltöltése"])

cropped_img = None

crop_shape = None
corner_radius = 0

if img_choice != "Kép nélkül":
    crop_shape = st.radio("Crop forma választás:", ["Kör crop", "Négyzet crop"])
    if crop_shape == "Négyzet crop":
        corner_radius = st.slider("Sarok lekerekítése (pixelben)", min_value=5, max_value=200, value=5, step=5)
    border_size = st.slider("Belső keret vastagsága (%)", min_value=0, max_value=10, value=3)
else:
    border_size = 0
    corner_radius = 0
    crop_shape = None


if img_choice == "Saját kép feltöltése":
    uploaded_file = st.file_uploader("Válassz egy profilképet", type=["jpg", "jpeg", "png"])
    if uploaded_file:
        img = Image.open(uploaded_file)
        cropped_img = st_cropper(img, aspect_ratio=[1.0, 1.0], return_type="image", box_color='blue')
        
        if crop_shape == "Kör crop":
            # Kör crop: ez nem méretezi át korábban, csak itt a QR középen lesz körvágva
            pass
        elif crop_shape == "Négyzet crop":
            cropped_img = make_square_avatar_with_inner_border(cropped_img, max(cropped_img.size), border=5, corner_radius=corner_radius)
        st.image(cropped_img, caption='Kivágott kép', width=200)

elif img_choice == "Logó használata":
    if company_logo:
        cropped_img = company_logo
        if crop_shape == "Négyzet crop":
            cropped_img = make_square_avatar_with_inner_border(cropped_img, max(cropped_img.size), border=5, corner_radius=corner_radius)
        st.image(cropped_img, caption="Cég logója", width=200)
    else:
        st.warning("A cég logó nem található vagy nincs feltöltve.")


# QR generáláskor a center_img paraméterhez a crop shape szerint kell avatar készítést használni:
def prepare_center_img_for_qr(img, qr_width, crop_shape, corner_radius=0):
    diameter = int(qr_width * 0.40)
    border = int(qr_width * 0.03)
    if crop_shape == "Kör crop":
        return make_circle_avatar_with_inner_border(img, diameter, border)
    elif crop_shape == "Négyzet crop":
        # Négyzet alakú, lekerekített sarkokkal a qr középen
        return make_square_avatar_with_inner_border(img, diameter, border, corner_radius)
    else:
        return None


# Hátterszín választó
bg_color = st.color_picker("Válassz hátterszínt a fényképhez", "#FFFFFF")

rotate_option = st.radio("Profilkép forgatása:", ["Nincs forgatás", "Óramutató járásával megegyező", "Óramutató járásával ellentétes"])
rotate_placeholder = st.empty()

embed_base64_photo = st.checkbox("Kép beágyazása base64 kóddal a vCard-ba (nem működik)", disabled=True, value=False)

qr_style = st.radio("Válaszd ki a QR kód stílusát", [
    "Négyzet",
    "Kör",
    "Szaggatott négyzet",
    "Függőleges vonal",
    "Vízszintes vonal",],index = 1)

# Alkalmazzuk a hátterszínt a képhez, ha van kép vagy logó
if cropped_img:
    cropped_img = apply_background_color(cropped_img, bg_color)

    rotate = False
    if rotate_option == "Óramutató járásával megegyező":
        rotate = True
        cropped_img = cropped_img.rotate(-90, expand=True)
    elif rotate_option == "Óramutató járásával ellentétes":
        rotate = True
        cropped_img = cropped_img.rotate(90, expand=True)
    else:
        rotate = False

    if rotate:
        rotate_placeholder.image(cropped_img, caption="Kép forgatás után", width = 200)
    else:
        rotate_placeholder.empty()



design = st.radio("Válaszd ki a dizájnt!", [
    "Csak QR",
    "QR, középen logó/kép",
    "QR, középen logó/kép, felül adatok"
])

def build_vcard(fields, img_format = "JPEG"):
    vcard_lines = ["BEGIN:VCARD", "VERSION:3.0"]
    for f in fields:
        val = active_fields.get(f['key'], "")
        if val:
            vcard_lines.append(f"{f['key']}:{val}")

    if embed_base64_photo and cropped_img:
        qr_img_resized = cropped_img.resize((32, 32), Image.Resampling.LANCZOS)
        photo_b64 = to_base64(qr_img_resized, img_format=img_format)
        photo_field = f'PHOTO;ENCODING=b;TYPE={img_format}:\n {fold_base64_string(photo_b64)}'
        vcard_lines.append(photo_field)

    vcard_lines.append("END:VCARD")
    return "\n".join(vcard_lines)

vcard_str = build_vcard(fields)

def generate_qr_styled(data, center_img=None, style="Négyzet", crop_shape="Kör crop", corner_radius=0):
    style_map = {
        "Négyzet": SquareModuleDrawer(),
        "Kör": CircleModuleDrawer(),
        "Szaggatott négyzet": GappedSquareModuleDrawer(),
        "Függőleges vonal": VerticalBarsDrawer(),
        "Vízszintes vonal": HorizontalBarsDrawer()
    }
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    drawer = style_map.get(style, SquareModuleDrawer())
    qr_img = qr.make_image(image_factory=StyledPilImage, module_drawer=drawer, fill_color="black", back_color="white").convert("RGBA")

    if center_img:
        qr_w = qr_img.width
        diameter = int(qr_w * 0.40)
        border = int(qr_w * float(border_size)/100.0)
    
        if crop_shape == "Kör crop":
            avatar_img = make_circle_avatar_with_inner_border(center_img, diameter, border)
        elif crop_shape == "Négyzet crop":
            avatar_img = make_square_avatar_with_inner_border(center_img, diameter, border, corner_radius)
        else:
            avatar_img = None

        if avatar_img is not None:
            center = (qr_w // 2 - diameter // 2, qr_w // 2 - diameter // 2)
            qr_img.paste(avatar_img, center, mask=avatar_img.split()[3])

    return qr_img

final_img = None
if st.button("Névjegykártya generálása"):
    if design == "Csak QR":
        qr_final = generate_qr_styled(vcard_str,style=qr_style)
        st.image(qr_final, caption="QR kód")
    elif design == "QR, középen logó/kép":
        if img_choice == "Kép nélkül":
            st.error("Válassz képet vagy logót ehhez a dizájnhoz!")
        else:
            qr_final = generate_qr_styled(vcard_str, center_img=cropped_img,style=qr_style, crop_shape=crop_shape, corner_radius=corner_radius)
            
            st.image(qr_final, caption="QR kód kör középen képpel")
    elif design == "QR, középen logó/kép, felül adatok":
        if img_choice == "Kép nélkül":
            st.error("Válassz képet vagy logót ehhez a dizájnhoz!")
        else:
            qr_final = generate_qr_styled(vcard_str, center_img=cropped_img, style=qr_style,  crop_shape=crop_shape, corner_radius=corner_radius)    

            # Előkészítjük a szöveges blokkot
            name = active_fields.get("FN", "").strip()
            org = active_fields.get("ORG", "").strip()
            title = active_fields.get("TITLE", "").strip()
            text_lines = [line for line in [name, org, title] if line]

            try:
                font_path = "DejaVuSans.ttf"  # vagy "NotoSans-Regular.ttf"
                font_size = 48
                font = ImageFont.truetype(font_path, font_size)
            except Exception:
                font = ImageFont.load_default()

            text_img = draw_multiline_text_fixed_height(text_lines, qr_final.width, 240, font, line_spacing=12, text_color=(0, 0, 0))

            # Egy új kép, amely tartalmazza a szöveget fent és a QR kódot alul
            final_height = qr_final.height + 240
            final_img = Image.new("RGBA", (qr_final.width, final_height), (255, 255, 255, 255))
            final_img.paste(text_img, (0, 0))
            final_img.paste(qr_final, (0, 240), mask=qr_final)

            st.image(final_img, caption="Névjegykártya: szöveg és QR közép képpel")


st.download_button("vCard letöltése (.vcf)", vcard_str, file_name="contact.vcf")

if final_img is not None:
    final_img.save("vCard.png")
    with open("vCard.png", "rb") as file:
        st.download_button("QR letöltése (PNG)", file.read(), "vCard.png", mime="image/png")
elif 'qr_final' in locals():
    qr_final.save("vCard.png")
    with open("vCard.png", "rb") as file:
        st.download_button("QR letöltése (PNG)", file.read(), "vCard.png", mime="image/png")