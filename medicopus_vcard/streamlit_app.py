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
    company_logo = Image.open("./assets/medicopus_logo.png").convert("RGBA")
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

st.title("Medicopus vCARD 3.0 generátor")

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
if img_choice == "Saját kép feltöltése":
    uploaded_file = st.file_uploader("Válassz egy profilképet", type=["jpg", "jpeg", "png"])
    if uploaded_file:
        img = Image.open(uploaded_file)
        cropped_img = st_cropper(img, aspect_ratio=[1.0,1.0], return_type="image", box_color='blue')
        st.image(cropped_img, caption='Kivágott kép', use_column_width=True)
elif img_choice == "Logó használata":
    if company_logo:
        cropped_img = company_logo
        st.image(company_logo, caption="Cég logója", use_column_width=True)
    else:
        st.warning("A cég logó nem található vagy nincs feltöltve.")

# Hátterszín választó
bg_color = st.color_picker("Válassz hátterszínt a fényképhez", "#FFFFFF")

qr_style = st.radio("Válaszd ki a QR kód stílusát", [
    "Négyzet",
    "Kör",
    "Szaggatott négyzet",
    "Függőleges vonal",
    "Vízszintes vonal",],index = 1)

# Alkalmazzuk a hátterszínt a képhez, ha van kép vagy logó
if cropped_img:
    cropped_img = apply_background_color(cropped_img, bg_color)


design = st.radio("Válaszd ki a dizájnt!", [
    "Csak QR",
    "QR, közepén körkép",
    "QR, középen körkép, felül adatok"
])

def build_vcard(fields):
    vcard_lines = ["BEGIN:VCARD", "VERSION:3.0"]
    for f in fields:
        val = active_fields.get(f['key'], "")
        if val:
            vcard_lines.append(f"{f['key']}:{val}")
    vcard_lines.append("END:VCARD")
    return "\n".join(vcard_lines)

vcard_str = build_vcard(fields)

def generate_qr_styled(data, center_img=None, style="Négyzet"):
    style_map = {
        "Négyzet": SquareModuleDrawer(),
        "Kör": CircleModuleDrawer(),
        "Szaggatott négyzet": GappedSquareModuleDrawer(),
        "Függőleges vonal": VerticalBarsDrawer(),
        "Vízszintes vonal": HorizontalBarsDrawer()
    }
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H)
    qr.add_data(data)
    qr.make(fit=True)
    drawer = style_map.get(style, SquareModuleDrawer())
    qr_img = qr.make_image(image_factory=StyledPilImage, module_drawer=drawer, fill_color="black", back_color="white").convert("RGBA")

    if center_img:
        center = (qr_img.width // 2, qr_img.height // 2)
        radius = qr_img.width // 5
        mask = Image.new("L", qr_img.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius), fill=255)
        qr_img.paste((255,255,255,255), mask=mask)
        profile = center_img.resize((radius * 2, radius * 2))
        photomask = Image.new("L", (radius * 2, radius * 2), 0)
        ImageDraw.Draw(photomask).ellipse((0, 0, radius * 2, radius * 2), fill=255)
        profile.putalpha(photomask)
        qr_img.paste(profile, (center[0] - radius, center[1] - radius), mask=profile.split()[3])

    return qr_img

final_img = None
if st.button("Névjegykártya generálása"):
    if design == "Csak QR":
        qr_final = generate_qr_styled(vcard_str,style=qr_style)
        st.image(qr_final, caption="QR kód")
    elif design == "QR, közepén körkép":
        if img_choice == "Kép nélkül":
            st.error("Válassz képet vagy logót ehhez a dizájnhoz!")
        else:
            qr_final = generate_qr_styled(vcard_str, center_img=cropped_img,style=qr_style)
            
            st.image(qr_final, caption="QR kód kör közepén képpel")
    elif design == "QR, középen körkép, felül adatok":
        if img_choice == "Kép nélkül":
            st.error("Válassz képet vagy logót ehhez a dizájnhoz!")
        else:
            qr_final = generate_qr_styled(vcard_str, center_img=cropped_img, style=qr_style)    

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