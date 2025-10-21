from typing import Union, Tuple, List, Dict

import os
import json
from pathlib import Path

import streamlit as st
import pymupdf

import numpy as np 
import pandas as pd

from PIL import Image, ImageOps
from PIL import ImageDraw, ImageFont
from PIL import ImageEnhance, ImageChops
import qrcode
from streamlit_cropper import st_cropper
from dataclasses import dataclass
import io

ROOT_FOLDER = "artwork"
# ROOT_FOLDER = ""


# --- DATA CLASS ---

@dataclass
class Crop:
    canvas_width: int
    canvas_height: int
    box: tuple                  # (left, upper, right, lower)
    crop_img_orig: Image.Image
    add_border: bool
    border_thickness: int  
    name: str
    width: int
    height: int
    aspect_ratio: float
    offset_x: int = 0
    offset_y: int = 0
    scale: float = 1.0
    visible: bool = True
    opacity: int = 100
    remove_bg: bool = True
    margin: int = 0
    
    offset_step = 5.0

    def __post_init__(self):
        print(f"Crop '{self.name}' created with size of {self.width} x {self.height}")
    
    @property
    def offset_x_pct(self) -> float:
        w = self.canvas_width
        if w == 0:
            return 0.0
        return  round_to_step((self.offset_x / w) * 100.0, self.offset_step)

    @offset_x_pct.setter
    def offset_x_pct(self, pct: float):
        w = self.canvas_width
        self.offset_x = int((pct / 100.0) * w)

    @property
    def offset_y_pct(self) -> float:
        h = self.canvas_height
        if h == 0:
            return 0.0
        return round_to_step((self.offset_y / h) * 100.0 , self.offset_step)

    @offset_y_pct.setter
    def offset_y_pct(self, pct: float):
        h = self.canvas_height
        self.offset_y = int((pct / 100.0) * h)
        
    
    def copy_params_from(self, other_crop):
        """
        Create a new Crop instance copying all parameters from other_crop except
        'crop_img_orig' and 'box' which remain as in the current instance.
        """
        return Crop(
            canvas_width= self.canvas_width,
            canvas_height= self.canvas_height,
            box=self.box,
            crop_img_orig=self.crop_img_orig,
            add_border=other_crop.add_border,
            border_thickness=other_crop.border_thickness,
            name=other_crop.name,
            width=self.width,
            height=self.height,
            aspect_ratio=self.aspect_ratio,
            offset_x=other_crop.offset_x,
            offset_y=other_crop.offset_y,
            scale=other_crop.scale,
            visible=other_crop.visible,
            opacity=other_crop.opacity,
            remove_bg=other_crop.remove_bg,
            margin=other_crop.margin
        )

# --- PAGE SELECTOR CLASS ---

class PageSelector:
    def __init__(self, key_prefix: str, images: list[Image.Image], label: str):
        self.key_prefix = key_prefix
        self.images = images
        self.label = label
        self.num_pages = len(images)

    def render(self, show_image:bool = True) -> int:
        st.markdown(f"### {self.label}")

        if self.num_pages == 1:
            st.text(f"Only one page available: {self.label} Page 1")
            st.session_state[f"{self.key_prefix}_page"] = 1
            return 0

        selected_page = st.session_state.get(f"{self.key_prefix}_page", 1)

        selected_page = st.number_input(
            f"Select {self.label} (1-{self.num_pages})",
            1,
            self.num_pages,
            selected_page,
            step=1,
            key=f"{self.key_prefix}_slider",
            width = "stretch"
        )
        if show_image:
            st.image(
                self.images[selected_page - 1],
                width=250,
                caption=f"{self.label}: Page {selected_page}",
            )

        st.session_state[f"{self.key_prefix}_page"] = selected_page

        return selected_page - 1

# --- UTILS ---

def round_to_step(value, step=5.0, floor = False):
    if floor:
        return np.floor(value / step) * step
    else:
        return np.round(value / step) * step

def load_custom_font(font_path: str, font_size: int):
    font_path = os.path.join(ROOT_FOLDER, "assets",font_path)
    try:
        font = ImageFont.truetype(font_path, font_size)
        success = True
        print(f"✅ Loaded custom font from {font_path}")

    except Exception as e:
        print(f"⚠️ Could not load custom font '{font_path}': {e}")
        font = ImageFont.load_default(size=font_size)
        success = False
    return font, success 


def pdf_to_images(pdf_bytes, dpi=72):
    doc = pymupdf.open(stream=pdf_bytes, filetype='pdf')
    zoom = dpi / 72
    mat = pymupdf.Matrix(zoom, zoom)
    images = []
    for page in doc:
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img.convert("RGBA"))
    return images

def load_pdf_and_convert(pdf_file, dpi):
    return pdf_to_images(pdf_file.read(), dpi=dpi)



def shrink_to_content(img: Image.Image, mode="top_bottom") -> Union[Tuple[int, int], Tuple[int, int, int, int]]:
    """
    Returns displacement bounding box of non-white content relative to the image size.

    - mode 'top_bottom': returns (top_displacement, bottom_displacement)
        top_displacement >= 0
        bottom_displacement <= 0 (negatív vagy 0)

    - mode 'all': returns (left_displacement, top_displacement, right_displacement, bottom_displacement)
        left_displacement >= 0
        top_displacement >= 0
        right_displacement <= 0
        bottom_displacement <= 0

    Considers white pixels as RGB >= 240 and alpha != 0.
    """

    img_rgba = img.convert('RGBA')
    arr = np.array(img_rgba)

    white_threshold = 240

    # Maszk, ahol nem-fehér pixelek vannak True-n
    mask = ~(
        (arr[..., 0] >= white_threshold) &
        (arr[..., 1] >= white_threshold) &
        (arr[..., 2] >= white_threshold) &
        (arr[..., 3] != 0)
    )
    coords = np.argwhere(mask)

    if coords.size == 0:
        # Nincs nem-fehér pixel, nincs crop, nincs displacement
        if mode == "top_bottom":
            return (0, 0)
        else:
            return (0, 0, 0, 0)

    # Pixel koordináták szélső értékei
    top = coords[:, 0].min()
    bottom = coords[:, 0].max()
    left = coords[:, 1].min()
    right = coords[:, 1].max()

    img_h, img_w = arr.shape[:2]

    # Számoljuk a displacementeket
    top_disp = top  # 0 vagy pozitív
    bottom_disp = bottom - img_h  # 0 vagy negatív
    left_disp = left  # 0 vagy pozitív
    right_disp = right - img_w  # 0 vagy negatív

    if mode == "top_bottom":
        return (top_disp, bottom_disp)

    else:
        return (left_disp, top_disp, right_disp, bottom_disp)
    

def update_bbox(orig_bbox: Tuple[int,int,int,int], 
                displace: Union[Tuple[int,int], Tuple[int,int,int,int]],
                mode="top_bottom") -> Tuple[int,int,int,int]:
    """
    Update the original bounding box coords using displacement values.

    orig_bbox: (left, top, right, bottom)
    displace:
      - mode 'top_bottom' -> (top_disp, bottom_disp)
      - mode 'all' -> (left_disp, top_disp, right_disp, bottom_disp)
      
    Displacement:
      top_disp, left_disp >= 0,
      bottom_disp, right_disp <= 0 (negatív vagy 0)

    Returns updated bounding box: (left, top, right, bottom)
    """

    left, top, right, bottom = orig_bbox

    if mode == "top_bottom":
        top_disp, bottom_disp = displace
        # bottom_disp negatív, ezért összeadjuk
        new_top = top + top_disp
        new_bottom = bottom + bottom_disp
        return (left, new_top, right, new_bottom)

    else:
        left_disp, top_disp, right_disp, bottom_disp = displace
        new_left = left + left_disp
        new_top = top + top_disp
        new_right = right + right_disp
        new_bottom = bottom + bottom_disp
        return (new_left, new_top, new_right, new_bottom)


def generate_qr_code_with_border(text, qr_size = None, box_size = 10, border_size=10):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=box_size,
        border=border_size)
    
    qr.add_data(text)
    qr.make(fit=True)
    
    img_qr = qr.make_image(fill='black', back_color='white').convert('RGBA')
    
    if qr_size is not None:
        img_qr = img_qr.resize((qr_size, qr_size), Image.LANCZOS)
        enhancer = ImageEnhance.Sharpness(img_qr)
        img_qr = enhancer.enhance(2)

    return img_qr


def add_black_border(img, border_size=5):
    return ImageOps.expand(img, border=border_size, fill='black')

def scale_image(image, target_width, target_height):
    scale_w = target_width / image.width
    scale_h = target_height / image.height
    scale = min(scale_w, scale_h)
    new_w = int(image.width * scale)
    new_h = int(image.height * scale)
    return image.resize((new_w, new_h), Image.LANCZOS)


def export_image_to_png(img: Image.Image, dpi: int) -> bytes:
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG', dpi=(dpi, dpi))
    return img_byte_arr.getvalue()


def adjust_vals(
    base_min: int,
    base_max: int,
    base_value: int,
    step: int,
    min_ratio=0.1,
    max_ratio=0.25,
    session_key_page_height='page_height_px'
):
    """
    A session_state-ből lekéri a page_height_px-et és aszerint visszaadja
    a csúszka értékeit (min, max, step, value).

    Az alap min és max értékeket is figyelembe veszi, de a page_height_px arányában
    dinamikusan számol.
    min_ratio és max_ratio az arányok a page_height_px-hez.

    Visszatérési érték: (min, max, step, value)
    """

    page_height_px = st.session_state.get(session_key_page_height, None)
    if page_height_px is None:
        # Ha nincs session állapotban, alap értékeket ad vissza
        return base_min, base_max, step, base_value

    qr_min = max(base_min, int(page_height_px * min_ratio))
    qr_max = max(qr_min + 50, int(page_height_px * max_ratio))
    qr_default = int((qr_min + qr_max) / 2)

    # A visszatérési érték marad Streamlit slider kompatibilis
    return qr_min, qr_max, qr_default, step


# --- LOGIC ---

def place_crop_on_page(page_img, crop: Crop):
    # Számoljuk a scale faktort a canvas és a page_img méretei alapján
    scale_w = page_img.width / crop.canvas_width
    scale_h = page_img.height / crop.canvas_height

    # Margin pixelben, canvas alapú margó százalék skálázva page_img-re
    margin_x = int(crop.canvas_width * crop.margin / 100.0 * scale_w)
    margin_y = int(crop.canvas_height * crop.margin / 100.0 * scale_h)

    # Kivágjuk az eredeti crop területet a crop_img_orig-ból
    cropped = crop.crop_img_orig.crop(crop.box)

    # Számoljuk az átméretezett crop méretét a scale faktorokat is figyelembe véve
    crop_w = int(crop.width * crop.scale * scale_w)
    crop_h = int(crop.height * crop.scale * scale_h)

    # Átméretezzük a crop-ot
    cropped_resized = cropped.resize((crop_w, crop_h), Image.LANCZOS)

    # Adjunk hozzá margint, mint padding, margint a szélekre
    if margin_x > 0 or margin_y > 0:
        new_w = crop_w + 2 * margin_x
        new_h = crop_h + 2 * margin_y
        expanded = Image.new("RGBA", (new_w, new_h), (255, 255, 255, 255))
        expanded.paste(cropped_resized, (margin_x, margin_y), cropped_resized)
        cropped_resized = expanded

    # Ha szükséges, adjunk hozzá fekete border-t
    if crop.add_border:
        cropped_resized = ImageOps.expand(cropped_resized, border=crop.border_thickness, fill='black')

    # Ha háttér eltávolítása kell vagy átlátszóság módosítás
    if crop.remove_bg or crop.opacity < 100:
        if cropped_resized.mode != 'RGBA':
            cropped_resized = cropped_resized.convert('RGBA')

        datas = cropped_resized.getdata()
        newData = []
        threshold = 250
        for item in datas:
            r, g, b, a = item
            effective_opacity = crop.opacity
            new_alpha = int(a * effective_opacity / 100)

            if r > threshold and g > threshold and b > threshold:
                if crop.remove_bg:
                    newData.append((r, g, b, 0))
                else:
                    newData.append((r, g, b, new_alpha))
            else:
                newData.append((r, g, b, new_alpha))
        cropped_resized.putdata(newData)

    # Hozzunk létre üres overlay képet a page_img méretével
    overlay = Image.new('RGBA', page_img.size, (0, 0, 0, 0))

    # Számoljuk ki a crop végleges pozícióját page_img koordinátarendszerben
    pos_x = int((page_img.width - cropped_resized.width) / 2 + crop.offset_x * scale_w)
    pos_y = int((page_img.height - cropped_resized.height) / 2 + crop.offset_y * scale_h)

    overlay.paste(cropped_resized, (pos_x, pos_y), cropped_resized)

    # Keverjük össze az overlayt az eredeti page_img-pel
    composed = Image.alpha_composite(page_img.convert('RGBA'), overlay)

    return composed


def add_title_and_qr_code(
    base_img: Image.Image,
    font_path: str,
    font_size: int,
    title_text: str = "",
    stroke_width: int = 2,
    with_underline: bool = False,
    qr_text: str = "",
    qr_size: int = 100,
    qr_box_size: int = 10,
    qr_padding: int = 0,
    qr_position: str = "bottom-right",
    qr_margin_factor: float = 0,
    qr_w_displace: float = 0,
    qr_h_displace:float = 0
) -> Image.Image:
    img = base_img.copy()
    
    margin = int(img.height * 0.03)

    
    # Ha nincs cím, csak térj vissza a sima képpel esetleg QR-rel
    
    def get_qr_pos(pos_string, img, qr_img, qr_margin_factor, qr_w_displace, qr_h_displace):
        x_margin = int(img.width * qr_margin_factor /100.0)
        y_margin  = int(img.height * qr_margin_factor/100.0)
        
        x_displace = int(img.width * qr_w_displace  / 100.0)
        y_displace = int(img.height * qr_h_displace / 100.0)

        if pos_string == "top-left":
            pos = (x_margin + x_displace, y_margin + y_displace)
        elif pos_string == "top-right":
            pos = (img.width - x_margin - x_displace - qr_img.width, y_margin + y_displace)
        elif pos_string == "bottom-left":
            pos = (x_margin + x_displace, img.height - qr_img.height - y_margin - y_displace)
        elif pos_string == "bottom-right":
            pos = (img.width - qr_img.width - x_margin - x_displace, img.height - qr_img.height - y_margin - y_displace)
        else:
            pos = (int(x_displace - (qr_img.width/2.0)), int(y_displace - (qr_img.height/2.0)))
        return pos
        
    if not title_text.strip():
        # QR kód hozzáadása, ha meg van adva
        if qr_text.strip():
            qr_img = generate_qr_code_with_border(qr_text.strip(), qr_size= qr_size, box_size=qr_box_size, border_size=qr_padding)
            pos = get_qr_pos(pos_string= qr_position, img=img, qr_img=qr_img, qr_margin_factor=qr_margin_factor,  
                             qr_w_displace =qr_w_displace, qr_h_displace= qr_h_displace)
            img.paste(qr_img, pos, qr_img)
        return img

    # 1. Betöltjük a fontot és kiszámoljuk a cím magasságát
    font, success = load_custom_font(font_path, font_size)
    dummy_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bbox = dummy_draw.textbbox((0, 0), title_text, font=font)
    title_height = bbox[3] - bbox[1]
    
    title_block_height = title_height + 2 * margin

    # 2. Új kép magasság, ami a kép + cím sáv
    total_height = img.height + title_block_height
    total_width = img.width

    # 3. Az új magas kép arányosítása úgy, hogy a teljes magasság változzon, a kép zsugorodjon
    base_aspect = img.width / img.height

    target_width = total_width
    target_height = total_height

    # Átméretezendő a kép úgy, hogy megfeleljen a title_block magasságának is
    # A kép magasságát úgy méretezzük, hogy a teljes magasságból levonjuk a cím sáv magasságát
    max_content_height = target_height - title_block_height
    scale_ratio = max_content_height / img.height

    new_img_width = int(img.width * scale_ratio)
    new_img_height = int(img.height * scale_ratio)
    resized_img = img.resize((new_img_width, new_img_height), Image.LANCZOS)

    # 4. Készítünk egy üres, teljes méretű új képet, fehér háttérrel
    new_canvas = Image.new("RGBA", (target_width, target_height), (255, 255, 255, 255))

    # 5. A lezsugorított képet függőlegesen középre igazítjuk a cím sav alatt
    content_top = title_block_height + (max_content_height - new_img_height) // 2
    content_left = (target_width - new_img_width) // 2
    new_canvas.paste(resized_img, (content_left, content_top), resized_img)

    # 6. Rajzolunk a cím sávra a cím szöveget, stroke-val, alul vonallal (ha kell)
    draw = ImageDraw.Draw(new_canvas)
    x = (target_width - (bbox[2] - bbox[0])) // 2
    y = margin
    draw.text(
        (x, y),
        title_text,
        font=font,
        fill=(0, 0, 0, 255),
        stroke_width=stroke_width,
        stroke_fill=(0, 0, 0, 255),
    )

    if with_underline:
        line_y = y + title_height + margin // 2
        line_thickness = max(1, stroke_width)
        draw.line([(0, line_y), (target_width, line_y)], fill=(0, 0, 0, 255), width=line_thickness)

    # 7. QR kód hozzáadás
    if qr_text.strip():
        qr_img =  generate_qr_code_with_border(qr_text.strip(), qr_size= qr_size, box_size=qr_box_size, border_size=qr_padding)
        pos = get_qr_pos(pos_string= qr_position, img=new_canvas, qr_img=qr_img, qr_margin_factor=qr_margin_factor, 
                         qr_w_displace = qr_w_displace, qr_h_displace = qr_h_displace)
        new_canvas.paste(qr_img, pos, qr_img)

    return new_canvas

# --- GUI ---
def manage_main_page_selection(images):
    selector = PageSelector("main", images, "Main Page Selection")
    selected_idx = selector.render()
    st.session_state["main_page"] = selected_idx + 1  # 1-based display
    st.info(f"Selected page {selected_idx + 1} as main page")
    

def crop_main_page_fullwidth(images):
    """
    Full-width crop duplacsúszkás vezérléssel + auto shrink + margin.
    Két oszlopos elrendezés: bal oldalt beállítások, jobb oldalt preview.
    """
    st.subheader("✂️ Main page crop")

    main_idx = st.session_state.get("main_page", 1) - 1
    img = images[main_idx].convert("RGBA")

    col1, col2 = st.columns([0.4, 0.6])

    
    
    with col1:
        st.markdown("### Settings")

        st.session_state["main_atuo_crop"] =  st.checkbox(
        "🧩 Fit to content",
        value=True,
        key=f"main_crop_fit_cb"
        )
        
        # --- crop range sliders ---
        top_default = st.session_state.get("main_crop_top_pct", 10)
        top_pct = st.number_input(
            "Cut from top (%)",
            0, 99, top_default, step=1, key="main_crop_top_pct_slider"
        )

        bottom_max = max(0, 99 - top_pct)
        bottom_default = st.session_state.get("main_crop_bottom_pct", 10)
        bottom_default = min(bottom_default, bottom_max)
        bottom_pct = st.number_input(
            "Cut from bottom (%)",
            0, bottom_max, bottom_default, step=1, key="main_crop_bottom_pct_slider"
        )

        # store state
        st.session_state['main_crop_top_pct'] = top_pct
        st.session_state['main_crop_bottom_pct'] = bottom_pct

        # --- add top/bottom margins ---
        st.markdown("#### Add vertical margins")
        top_margin_pct = st.slider("Top margin (%)", 0, 10, 0, step=1, key="main_crop_margin_top")
        bottom_margin_pct = st.slider("Bottom margin (%)", 0, 10, 0, step=1, key="main_crop_margin_bottom")

        # --- alignment choice ---
        align = st.radio(
            "Vertical alignment:",
            ["Top", "Center", "Bottom"],
            horizontal=True,
            index=1,
            key="main_crop_align"
        )

    # --- crop image by sliders ---
    h = img.height
    top_px = int(round(top_pct / 100.0 * h))
    bottom_px = int(round(bottom_pct / 100.0 * h))
    cropped_h = max(1, h - top_px - bottom_px)
    forced_box = (0, top_px, img.width, top_px + cropped_h)
    cropped = img.crop(forced_box)

    if st.session_state.get("main_atuo_crop", False):
        top_rel, bottom_rel = shrink_to_content(cropped, mode="top_bottom")
        new_bbox = update_bbox((0, top_px, img.width, top_px + cropped_h), (top_rel, bottom_rel), mode="top_bottom")
        new_top, new_bottom = new_bbox[1], new_bbox[3]

        cropped = img.crop((0, new_top, img.width, new_bottom))

        top_margin_px = int(round(top_margin_pct / 100.0 * img.height))
        bottom_margin_px = int(round(bottom_margin_pct / 100.0 * img.height))
        expanded_h = cropped.height + top_margin_px + bottom_margin_px
        expanded = Image.new("RGBA", (img.width, expanded_h), (255, 255, 255, 255))
        expanded.paste(cropped, (0, top_margin_px), cropped)
    else:
        new_top, new_bottom = top_px, top_px + cropped_h
        expanded = Image.new("RGBA", (img.width, new_bottom - new_top), (255, 255, 255, 255))
        expanded.paste(cropped, (0, 0), cropped)
    
    # --- add top/bottom margins ---
    top_margin_px = int(round(top_margin_pct / 100.0 * img.height))
    bottom_margin_px = int(round(bottom_margin_pct / 100.0 * img.height))

    expanded_h = cropped.height + top_margin_px + bottom_margin_px
    expanded = Image.new("RGBA", (img.width, expanded_h), (255, 255, 255, 255))
    expanded.paste(cropped, (0, top_margin_px), cropped)

    # --- alignment on full-size canvas ---
    canvas = Image.new("RGBA", img.size, (255, 255, 255, 255))

    if align == "Top":
        y_pos = 0
    elif align == "Center":
        y_pos = (img.height - expanded.height) // 2
    else:
        y_pos = img.height - expanded.height

    y_pos = max(0, min(y_pos, img.height - expanded.height))
    canvas.paste(expanded, (0, y_pos), expanded)

    with col2:
        st.markdown("### Preview")

        # Teljes oldal előnézeti képe, az eredeti képből méretezve (illeszkedik a kol1 szélességéhez)
        preview_width = 400
        aspect_ratio = img.width / img.height
        preview_height = int(preview_width / aspect_ratio)
        preview_img = img.resize((preview_width, preview_height), Image.LANCZOS).copy()

        draw = ImageDraw.Draw(preview_img)

        # Számoljuk át a top és bottom pozíciókat a preview mérethez
        scale_preview = preview_img.height / img.height
        top_line_y = int((new_top) * scale_preview)
        bottom_line_y = int((new_bottom) * scale_preview)

        # Rajzoljunk két piros vízszintes vonalat a preview-ra
        line_color = (255, 0, 0)
        line_thickness = 1

        draw.line([(0, top_line_y), (preview_img.width, top_line_y)], fill=line_color, width=line_thickness)
        draw.line([(0, bottom_line_y), (preview_img.width, bottom_line_y)], fill=line_color, width=line_thickness)

        st.image(preview_img, caption=f"Page preview with crop boundaries", width="stretch")


    return canvas


def crop_creation_ui(images):
    st.subheader("✂️ Define Crop (choose source page + free crop area)")

    # --- page selector for crop source ---
    crop_source_selector = PageSelector("crop_source", images, "Crop Source Page")
    crop_src_idx = crop_source_selector.render(show_image=False)
    crop_source_img = images[crop_src_idx]

    # --- Cropper ---
    crop_box = st_cropper(
        crop_source_img,
        aspect_ratio=None,
        realtime_update=True,
        box_color="red",
        return_type="box",
        key=f"cropper_{crop_src_idx}"
    )

    if crop_box is None:
        st.info("Select an area above to define crop.")
        return

    if isinstance(crop_box, dict):
        crop_box = (
            crop_box["left"],
            crop_box["top"],
            crop_box["left"] + crop_box["width"],
            crop_box["top"] + crop_box["height"]
        )

    crop_name = st.text_input("Crop name")

    fit_to_content = st.checkbox(
        "🧩 Fit to content",
        value=True,
        key=f"crop_fit_cb"
    )

    if st.button("Add crop", width="stretch"):
        if not crop_name.strip():
            st.warning("Please enter a crop name before adding crop.")
            return

        left, top, right, bottom = map(int, crop_box)
        width = right - left
        height = bottom - top
        if width <= 0 or height <= 0:
            st.error("Invalid crop area. Please reselect.")
            return

        cropped = crop_source_img.crop((left, top, right, bottom)).convert("RGBA")

        if fit_to_content:
            # Új shrink_to_content - bbox displace logika (mode="all")
            displace = shrink_to_content(cropped, mode="all")  # (left_disp, top_disp, right_disp, bottom_disp)
            # Eredeti crop box az oldalon:
            orig_bbox = (0, 0, cropped.width, cropped.height)
            # Frissített bbox relatív eltolások alapján:
            updated_bbox = update_bbox(orig_bbox, displace, mode="all")
            # bbox koordináták helyileg a cropped képre vonatkoznak
            l, t, r, b = updated_bbox
            # Ellenőrzés (ha nem érvényes, szimplán vissza az eredeti cropped)
            if r <= l or b <= t:
                print("empty after crop")
            else:
                cropped = cropped.crop((l, t, r, b))

        aspect_ratio = cropped.width / cropped.height if cropped.height > 0 else 1.0
        
        new_crop = Crop(
            canvas_width = crop_source_img.width,
            canvas_height = crop_source_img.height,
            box=(0, 0, cropped.width, cropped.height),
            crop_img_orig=cropped,
            add_border=False,
            border_thickness=1,
            name=crop_name.strip(),
            width=cropped.width,
            height=cropped.height,
            aspect_ratio=aspect_ratio,
            visible=True,
            remove_bg=True,
            opacity=100,
            scale= 1.0
        )
        
        
        
        if 'crops' not in st.session_state:
            st.session_state['crops'] = []

        existing_index = next(
            (i for i, c in enumerate(st.session_state['crops']) if c.name == new_crop.name),
            None
        )
        if existing_index is not None:
            try:
                st.session_state['crops'][existing_index] = new_crop.copy_params_from(st.session_state['crops'][existing_index])
            except:
                st.session_state['crops'][existing_index] = new_crop               
                
            st.success(f"Updated crop '{new_crop.name}' from page {crop_src_idx + 1}!")
        else:
            st.session_state['crops'].append(new_crop)
            st.success(f"Added crop '{new_crop.name}' from page {crop_src_idx + 1}!")

        st.rerun()


def crops_placement_ui(page_img, crop_preview_width=600, placement_preview_width=400):
    import streamlit as st
    from PIL import ImageDraw

    st.subheader("Position & Scale Crops on Page")

    if 'crops' not in st.session_state or not st.session_state['crops']:
        st.info("No crops added yet.")
        return page_img.copy()

    composed = page_img.copy()

    for idx, crop in enumerate(st.session_state['crops']):
        st.markdown(f"### ✂️ Crop #{idx + 1}: {crop.name}")

        preview_width = crop_preview_width
        cropped_preview = crop.crop_img_orig.crop(crop.box)
        aspect_ratio = crop.width / crop.height
        preview_height = int(preview_width / aspect_ratio)
        cropped_preview_resized = cropped_preview.resize((preview_width, preview_height), Image.LANCZOS)
        st.image(cropped_preview_resized, caption=f"Crop preview: {crop.name}", width=preview_width)

        col1, col2 = st.columns(2)
        with col1:
            new_offset_x_pct = st.slider(
                f"Horizontal offset (%) – {crop.name}",
                -50.0, 50.0,
                crop.offset_x_pct,
                step=crop.offset_step,
                key=f"offset_x_pct_{idx}"
            )
            crop.offset_x_pct = round_to_step(new_offset_x_pct, step=crop.offset_step)

            new_offset_y_pct = st.slider(
                f"Vertical offset (%) – {crop.name}",
                -50.0, 50.0,
                crop.offset_y_pct,
                step=crop.offset_step,
                key=f"offset_y_pct_{idx}"
            )
            crop.offset_y_pct = round_to_step(new_offset_y_pct, step=crop.offset_step)

            crop.scale = st.slider(
                f"Scale ({crop.name})",
                0.1, 2.0,
                crop.scale,
                step=0.1,
                key=f"scale_{idx}"
            )

            crop.margin = st.slider(
                f"Margin (%) – {crop.name}",
                0, 10,
                crop.margin,
                step=1,
                key=f"margin_{idx}"
            )

            o1, o2 = st.columns(2)
            crop.opacity = o1.slider("Opacity", 0, 100, crop.opacity, step=5, key=f"opacity_{idx}")
            crop.remove_bg = o1.checkbox("Remove background", crop.remove_bg, key=f"remove_bg_{idx}")
            crop.visible = o2.checkbox("Visible", crop.visible, key=f"visible_{idx}")

            b1, b2 = st.columns(2)
            crop.add_border = b1.checkbox("Add black border", crop.add_border, key=f"border_{idx}")
            crop.border_thickness = b2.number_input("Border thickness", 1, 20, crop.border_thickness, key=f"border_thickness_{idx}")

            d1, d2 = st.columns(2)
            delete_clicked = d1.button("Delete", key=f"delete_{idx}", width="stretch")
            confirm = d2.checkbox("Confirm delete", value=False, key=f"confirm_{idx}")

            if delete_clicked and confirm:
                del st.session_state["crops"][idx]
                st.success(f"Crop '{crop.name}' deleted.")
                st.experimental_rerun()
                return

        with col2:
            preview_max_width = placement_preview_width
            aspect_ratio = page_img.width / page_img.height
            preview_w = preview_max_width
            preview_h = int(preview_w / aspect_ratio)
            preview_img = page_img.resize((preview_w, preview_h), Image.LANCZOS).copy()

            draw = ImageDraw.Draw(preview_img)

            # Belső scale a canvas és a page_img mérete között
            scale_w = page_img.width / crop.canvas_width
            scale_h = page_img.height / crop.canvas_height

            # Margin átszámolva canvas méretből, majd skálázva preview mérethez
            margin_x = int(crop.canvas_width * crop.margin / 100.0 * (preview_w / crop.canvas_width))
            margin_y = int(crop.canvas_height * crop.margin / 100.0 * (preview_h / crop.canvas_height))

            # Scaled crop size + margin, tovább arányosítva preview mérethez
            scaled_crop_w = int(crop.width * crop.scale * (preview_w / crop.canvas_width)) + 2 * margin_x
            scaled_crop_h = int(crop.height * crop.scale * (preview_h / crop.canvas_height)) + 2 * margin_y

            # Offset pixelek arányosítva preview mérethez
            offset_x_px = int(crop.offset_x * (preview_w / crop.canvas_width))
            offset_y_px = int(crop.offset_y * (preview_h / crop.canvas_height))

            center_x = preview_w // 2 + offset_x_px
            center_y = preview_h // 2 + offset_y_px

            left = center_x - scaled_crop_w // 2
            top = center_y - scaled_crop_h // 2
            right = center_x + scaled_crop_w // 2
            bottom = center_y + scaled_crop_h // 2

            draw.rectangle([left, top, right, bottom], outline="red", width=3)

            st.image(preview_img, caption=f"Full page preview with crop: {crop.name}", width=preview_max_width)


        if not crop.visible:
            continue

        composed = place_crop_on_page(composed, crop)

    st.markdown("## 🖼️ Final Composition (All Crops Placed)")
    st.image(composed, width="stretch")

    if st.button("Reset all crop positions & scales"):
        for c in st.session_state["crops"]:
            c.offset_x = 0
            c.offset_y = 0
            c.scale = 1.0
            c.add_border = False
            c.visible = True
            c.opacity = 100
            c.border_thickness = 3
        st.experimental_rerun()

    return composed



# --- MAIN APP ---

def app():
    st.set_page_config(page_title="ArtWork")
    st.title("Artwork - an article preview creator")

    if 'qr_size' not in st.session_state:
        st.session_state['qr_size' ] = 0
   
    if 'font' not in st.session_state:
        font_path = "montserrat.ttf"
        font_size_default = 24
        st.session_state['font'], success = load_custom_font(font_path, font_size_default)
        if not success:
            st.warning(f"⚠️ The custom font at '{font_path}' could not be loaded. Using default font instead.")

    pdf_file = st.file_uploader("Upload PDF file", type=["pdf"])
    if not pdf_file:
        st.info("Please upload a PDF file first.")
        return


    input_dpi, output_dpi, page_size, page_sizes_mm = None, None, None, None
    with st.sidebar.expander("Resolution settings"):
        input_dpi = st.select_slider("Input DPI", value=150, options = [72, 96, 100, 150, 300, 600, 1200])
        output_dpi = st.select_slider("Output DPI", value=150, options = [72, 96, 100, 150, 300, 600, 1200])
        
        # Ellenőrzés, hogy új PDF vagy input DPI változás történt-e
        if ('pdf_name' not in st.session_state) or (st.session_state['pdf_name'] != pdf_file.name) or (st.session_state.get('input_dpi') != input_dpi):
            st.session_state['images'] = load_pdf_and_convert(pdf_file, dpi=input_dpi)
            st.session_state['pdf_name'] = pdf_file.name
            st.session_state['input_dpi'] = input_dpi
            st.session_state['crops'] = []
            st.session_state['main_page'] = 1

        # --- Base page scaling ---
        page_sizes_mm = {"A5": (148, 210), "A4": (210, 297), "A3": (297, 420)}
        page_size = st.selectbox("Output page size", list(page_sizes_mm.keys()), index=2)

        st.info(
        """
        DPI guideline:
        - 72 DPI: Web, screen view
        - 150 DPI: Office printing
        - 300 DPI: Professional print quality
        - 600 DPI+: High-resolution
        
        WARNING: Changing these values on-fligt can ruin your work.
        """
        )


    images = st.session_state['images']
    manage_main_page_selection(images)
    
    crop_main_page = st.checkbox("Crop main page")
    main_idx = st.session_state.get("main_page", 1) - 1
    
    if crop_main_page:
        page_img = crop_main_page_fullwidth(images)
    else:
        page_img = images[main_idx].convert("RGBA")
    

    page_height_px = int(page_sizes_mm[page_size][1] * output_dpi / 25.4)
    page_size_px = tuple(int(dim * output_dpi / 25.4) for dim in page_sizes_mm[page_size])

    point_per_mm = page_size_px[0] / page_sizes_mm[page_size][0]
    
    st.session_state['page_height_px'] = page_height_px
    scaled_page_img = scale_image(page_img, *page_size_px)


    # --- Add title and QR last ---
    title_text = st.sidebar.text_input("Title (Optional)", "")
    
    font_size_c, font_stroke_c = st.sidebar.columns(2)
    
    f_min, f_max, f_def, f_step = adjust_vals(12, 72, 24, 1, min_ratio=0.01,max_ratio=0.05)
    font_size_pt = font_size_c.slider("Title Font Size (pt)", f_min, f_max,  f_def, f_step)
    
    font_path = "montserrat.ttf"
    
    stroke_width = font_stroke_c.slider("Title Stroke Width", 1, 10, 1, 1)
    with_underline = st.sidebar.checkbox("Underline Title", value=False)


    qr_text = st.sidebar.text_area("QR Code Text (max 200 chars)", max_chars=200)
    qr_position = st.sidebar.selectbox("QR Code position", ["top-left", "top-right", "bottom-left", "bottom-right", "custom"], index = 1)
    
    qr_m, qr_p = st.sidebar.columns(2)
    qr_margin = qr_m.slider("QR Code page margin (%)", 0.0, 5.0,0.0,0.5) 
    qr_padding = qr_p.slider("QR Code padding (%)", 2.5,20.0,5.0,2.5)

    qr_h_d, qr_v_d = st.sidebar.columns(2)    

    qr_box_mm =  st.sidebar.slider("Approx. QR Code symbol size (mm)", 2.0,8.0,3.0,0.5)
    
    min_size = 10.0
    optimal_size = 20.0
    if str(qr_text) != "":
        dummy_qr = generate_qr_code_with_border(qr_text,None,border_size=qr_padding)
        min_size = 100.0 * (0.8 * qr_box_mm * (dummy_qr.width / point_per_mm)) /  page_size_px[0]
        optimal_size = 100.0 * (1.2 * qr_box_mm  * (dummy_qr.width / point_per_mm)) /  page_size_px[0]
        
        min_size = round_to_step(min_size,2.5)
        optimal_size = round_to_step(optimal_size,2.5)
        
        st.sidebar.info(f"Approx. Optimal size: {optimal_size:.1f}%")
        optimal_size = max(float(st.session_state['qr_size']), optimal_size)
        
        st.session_state["qr_text"] = str(qr_text)
    
    qr_w_percent = st.sidebar.slider("QR Code size (page width %)",min_size,50.0,optimal_size,2.5)
    st.session_state['qr_size' ] = qr_w_percent
    qr_size = int(qr_w_percent / 100.0 * page_size_px[0])

    qr_h_percent = int(qr_size / page_size_px[1]*100.0)

    min_w_displace = round_to_step(qr_w_percent/2.0,2.5, floor=False) if qr_position == "custom" else 0.0
    max_w_displace =round_to_step(100.0 - (qr_w_percent/2.0) ,2.5, floor=True) if qr_position == "custom" else round_to_step(50.0 - qr_w_percent,2.5, floor=True)

    min_h_displace = round_to_step(qr_h_percent/2.0,2.5, floor=False)  if qr_position == "custom" else 0.0
    max_h_displace = round_to_step(100.0 - (qr_h_percent/2.0) ,2.5, floor=True) if qr_position == "custom" else round_to_step(50.0 - qr_h_percent,2.5, floor=True)

    qr_w_displace = qr_h_d.slider("Horizontal displacement (%)", min_w_displace, max_w_displace, min_w_displace, 2.5)
    qr_h_displace = qr_v_d.slider("Vertical displacement (%)", min_h_displace, max_h_displace, min_h_displace, 2.5)


    

    st.markdown("### Define and Manage Crops")
    add_crops = st.checkbox("Add crops to the page")

    if add_crops:
        crop_creation_ui(images)
        composed_after_crops = crops_placement_ui(scaled_page_img)
    else:
        composed_after_crops = scaled_page_img.copy()

    # Cím és QR kód hozzáadása mindig a komponált képhez
    final_img = add_title_and_qr_code(
        composed_after_crops.copy(),
        font_path=font_path,
        font_size=font_size_pt,
        title_text=title_text,
        stroke_width=stroke_width,
        with_underline=with_underline,
        qr_text=qr_text,
        qr_size=qr_size,
        qr_padding = qr_padding, 
        qr_position=qr_position,
        qr_box_size= 10,
        qr_margin_factor= qr_margin,
        qr_w_displace = qr_w_displace,
        qr_h_displace = qr_h_displace
    )

    st.markdown("## 🧾 Final Output with QR")
    st.image(final_img, width="stretch")


    # --- Export final image ---
    st.subheader("💾 Export Final Image")
    png_bytes = export_image_to_png(final_img, output_dpi)
    st.download_button(
        "Download Final PNG",
        data=png_bytes,
        file_name="final_output.png",
        mime="image/png"
    )

# HEADLESS
PAGE_SIZES_MM = {
    "A3": (297, 420),
    "A4": (210, 297),
    "A5": (148, 210)
}

def mm_to_px(mm, dpi):
    """Millimétert konvertál pixelre."""
    return int(mm / 25.4 * dpi)

def get_page_size_px(size_name, dpi):
    """A megadott szabványos oldal méretét adja vissza pixelben."""
    if size_name.upper() not in PAGE_SIZES_MM:
        raise ValueError(f"Ismeretlen oldal méret: {size_name}")
    w_mm, h_mm = PAGE_SIZES_MM[size_name.upper()]
    return mm_to_px(w_mm, dpi), mm_to_px(h_mm, dpi)


def headless_qr(df: pd.DataFrame, preset_path: str, out_dir: str) -> None:
    """
    Headless PDF processing to generate images with optional title and QR code.

    Iterates over a pandas DataFrame containing PDF paths, QR code text, and output file names,
    renders the first page (or a specified start page) of each PDF to an image at the specified
    input DPI, rescales it to a standard page size at the output DPI, and applies a title and QR code.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing the following columns:
        - 'pdf_path': path to the input PDF file.
        - 'qr_text': text to encode in the QR code.
        - 'out_name': output file name (without extension).

    preset_path : str
        Path to a JSON file containing processing settings:
        - input_dpi : int, default 150
        - output_dpi : int, default 300
        - start_page : int, default 0
        - page_size : str, one of "A3", "A4", "A5"
        - font_path : str
        - font_size : int
        - title_text : str
        - stroke_width : int
        - with_underline : bool
        - qr_params : dict containing QR code parameters
            (qr_size, qr_box_size, qr_padding, qr_position, qr_margin_factor,
             qr_w_displace, qr_h_displace)

    out_dir : str
        Directory where output images will be saved. Created if it does not exist.

    Returns
    -------
    None
        Saves processed images as PNG files in `out_dir`.
    """
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    with open(preset_path, "r", encoding="utf-8") as f:
        preset = json.load(f)

    input_dpi = preset.get("input_dpi", 150)
    output_dpi = preset.get("output_dpi", 300)
    start_page = preset.get("start_page", 0)
    page_size_name = preset.get("page_size", "A3")
    page_width, page_height = get_page_size_px(page_size_name, output_dpi)

    font_path = preset.get("font_path", "")
    font_size = preset.get("font_size", 48)
    title_text = preset.get("title_text", "")
    stroke_width = preset.get("stroke_width", 2)
    with_underline = preset.get("with_underline", False)
    qr_params = preset.get("qr_params", {})

    print(f"📄 Page size: {page_size_name} ({page_width}x{page_height}px @ {output_dpi} DPI)")
    print(f"🔍 Input DPI: {input_dpi} → Output DPI: {output_dpi}")
    out_path = Path(out_dir)

    for i, row in df.iterrows():
        pdf_path = Path(row["pdf_path"])
        qr_text = str(row["qr_text"])
        out_name = Path(row["out_name"])

        if not pdf_path.exists():
            print(f"⚠️ {pdf_path} not found, skipping.")
            continue

        print(f"[{i+1}/{len(df)}] Processing: {pdf_path.name}")

        # --- Load PDF and render specified page ---
        doc = pymupdf.open(pdf_path)
        if start_page >= len(doc):
            print(f"⚠️ start_page {start_page} out of range, skipping.")
            continue

        page = doc[start_page]
        zoom = input_dpi / 72.0
        mat = pymupdf.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        base_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        # --- Resize to standard page size using Lanczos filter ---
        base_img = base_img.resize((page_width, page_height), Image.LANCZOS)

        # --- Apply title and QR code ---
        composed = add_title_and_qr_code(
            base_img=base_img,
            font_path=font_path,
            font_size=font_size,
            title_text=title_text,
            stroke_width=stroke_width,
            with_underline=with_underline,
            qr_text=qr_text,
            qr_size=qr_params.get("qr_size", 100),
            qr_box_size=qr_params.get("qr_box_size", 10),
            qr_padding=qr_params.get("qr_padding", 0),
            qr_position=qr_params.get("qr_position", "bottom-right"),
            qr_margin_factor=qr_params.get("qr_margin_factor", 0),
            qr_w_displace=qr_params.get("qr_w_displace", 0),
            qr_h_displace=qr_params.get("qr_h_displace", 0)
        )

        # --- Save output image ---
        composed.save(out_path / out_name.with_suffix(".png"))
        print(f"✅ Saved: {out_path / out_name.with_suffix('.png')}")

    print("🎯 Headless processing completed.")


if __name__ == "__main__":
    app()
