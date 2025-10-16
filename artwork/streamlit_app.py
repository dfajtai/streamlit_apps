import os
import streamlit as st
import pymupdf
from PIL import Image, ImageOps
from PIL import ImageDraw, ImageFont
import qrcode
from streamlit_cropper import st_cropper
from dataclasses import dataclass
import io

ROOT_FOLDER = "artwork"
# ROOT_FOLDER = ""


# --- DATA CLASS ---

@dataclass
class Crop:
    box: tuple                  # (left, upper, right, lower)
    crop_img_orig: Image.Image
    add_border: bool
    border_thickness: int       # új mező, pl alapértelmezett 3
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


# --- PAGE SELECTOR CLASS ---

class PageSelector:
    def __init__(self, key_prefix: str, images: list[Image.Image], label: str):
        self.key_prefix = key_prefix
        self.images = images
        self.label = label
        self.num_pages = len(images)

    def render(self) -> int:
        st.markdown(f"### {self.label}")

        if self.num_pages == 1:
            # Csak egy oldal van, nem jelenítünk meg semmit, csak visszatérünk 0-val
            st.text(f"Only one page available: {self.label} Page 1")
            st.session_state[f"{self.key_prefix}_page"] = 1
            return 0

        # Ellenkező esetben a slider UI jelenik meg
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

        st.image(
            self.images[selected_page - 1],
            width=250,
            caption=f"{self.label}: Page {selected_page}",
            use_container_width=False
        )

        st.session_state[f"{self.key_prefix}_page"] = selected_page

        return selected_page - 1

# --- UTILS ---

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

def generate_qr_code(text, dim):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4)
    qr.add_data(text)
    qr.make(fit=True)
    img_qr = qr.make_image(fill='black', back_color='white').convert('RGBA')
    img_qr = img_qr.resize((dim, dim))
    return img_qr


def generate_qr_code_with_border(text, target_height, border_size=10):
    # QR kód generálása alapból 100x100
    base_dim = 100
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4)
    qr.add_data(text)
    qr.make(fit=True)
    img_qr = qr.make_image(fill='black', back_color='white').convert('RGBA')

    # Átméretezés a kézben adott target magasságra - border nélkül
    qr_size = target_height - 2*border_size

    # Átméretezem
    img_qr = img_qr.resize((qr_size, qr_size), Image.LANCZOS)

    # Fehér border hozzáadása körbe
    img_qr_with_border = ImageOps.expand(img_qr, border=border_size, fill='white')
    return img_qr_with_border


def add_black_border(img, border_size=5):
    return ImageOps.expand(img, border=border_size, fill='black')

def scale_image(image, target_width, target_height):
    scale_w = target_width / image.width
    scale_h = target_height / image.height
    scale = min(scale_w, scale_h)
    new_w = int(image.width * scale)
    new_h = int(image.height * scale)
    return image.resize((new_w, new_h), Image.LANCZOS)

def place_crop_on_page(page_img, crop: Crop):
    crop_w = int(crop.width * crop.scale)
    crop_h = int(crop.height * crop.scale)

    cropped = crop.crop_img_orig.crop(crop.box)
    cropped_resized = cropped.resize((crop_w, crop_h), Image.LANCZOS)

    if crop.add_border:
        cropped_resized = ImageOps.expand(cropped_resized, border=crop.border_thickness, fill='black')

    # Ha remove_bg True vagy opacity < 100, eltávolítjuk a fehér hátteret és állítjuk az alfát
    if crop.remove_bg or crop.opacity < 100:
        if cropped_resized.mode != 'RGBA':
            cropped_resized = cropped_resized.convert('RGBA')

        datas = cropped_resized.getdata()
        newData = []
        threshold = 250
        for item in datas:
            r, g, b, a = item
            if r > threshold and g > threshold and b > threshold:
                # Fehér pixel -> teljesen átlátszó
                newData.append((r, g, b, 0))
            else:
                # Nem fehér pixel - alfa opacity szerint korrigálva
                effective_opacity = crop.opacity if not crop.remove_bg else 100
                new_alpha = int(a * effective_opacity / 100)
                newData.append((r, g, b, new_alpha))
        cropped_resized.putdata(newData)

    overlay = Image.new('RGBA', page_img.size, (0, 0, 0, 0))
    pos_x = int((page_img.width - cropped_resized.width) / 2 + crop.offset_x)
    pos_y = int((page_img.height - cropped_resized.height) / 2 + crop.offset_y)
    overlay.paste(cropped_resized, (pos_x, pos_y), cropped_resized)

    composed = Image.alpha_composite(page_img.convert('RGBA'), overlay)

    return composed



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

def manage_main_page_selection(images):
    selector = PageSelector("main", images, "Main Page Selection")
    selected_idx = selector.render()
    st.session_state["main_page"] = selected_idx + 1  # 1-based display
    st.info(f"Selected page {selected_idx + 1} as main page")

def crop_creation_ui(images):
    st.subheader("Define Crop (choose source page + free crop area)")

    # --- page selector for crop source ---
    crop_source_selector = PageSelector("crop_source", images, "Crop Source Page")
    crop_src_idx = crop_source_selector.render()
    crop_source_img = images[crop_src_idx]

    # --- cropper ---
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

    if st.button("Add crop",use_container_width=True):
        if not crop_name.strip():
            st.warning("Please enter a crop name before adding crop.")
            return

        width = crop_box[2] - crop_box[0]
        height = crop_box[3] - crop_box[1]
        if width <= 0 or height <= 0:
            st.error("Invalid crop area. Please reselect.")
            return

        aspect_ratio = width / height
        new_crop = Crop(
            box=crop_box,
            crop_img_orig=crop_source_img,
            add_border=False,
            border_thickness=1,
            name=crop_name.strip(),
            width=width,
            height=height,
            aspect_ratio=aspect_ratio,
            visible=True,
            remove_bg= True,
            opacity=100
        )

        if 'crops' not in st.session_state:
            st.session_state['crops'] = []


        existing_index = next((i for i, c in enumerate(st.session_state['crops']) if c.name == new_crop.name), None)
        if existing_index is not None:
            c = st.session_state['crops'][existing_index]
            try:
                c.box = new_crop.box
                c.crop_img_orig = new_crop.crop_img_orig
                st.success(f"Updated crop '{new_crop.name}' from page {crop_src_idx + 1}!")
            except Exception as e:
                st.error(f"Unable to update parameters of crop '{new_crop.name}' from page {crop_src_idx + 1}! Reseting parameters instead.")
                st.session_state['crops'][existing_index] = new_crop

            
        else:
            st.session_state['crops'].append(new_crop)
            st.success(f"Added crop '{new_crop.name}' from page {crop_src_idx + 1}!")

        st.rerun()


def crops_placement_ui(page_img, crop_preview_width = 600, placement_preview_width = 400, slider_step_percentage = 2.0):
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


        # Első táblázat: Offset és scale csúszkák
        col1, col2 = st.columns(2)

        with col1:
            crop.offset_x = st.slider(
                f"Horizontal offset ({crop.name})",
                -page_img.width // 2, page_img.width // 2,
                crop.offset_x,
                step=int(slider_step_percentage*page_img.width / 100.0),
                key=f"offset_x_{idx}"
            )
            crop.offset_y = st.slider(
                f"Vertical offset ({crop.name})",
                -page_img.height // 2, page_img.height // 2,
                crop.offset_y,
                step=int(slider_step_percentage*page_img.height / 100.0),
                key=f"offset_y_{idx}"
            )
            crop.scale = st.slider(
                f"Scale ({crop.name})",
                0.1, 5.0,
                crop.scale,
                step=0.1,
                key=f"scale_{idx}"
            )

            o1, o2 = st.columns(2)
            
            crop.opacity = st.slider("Opacity", 0, 100, getattr(crop, 'opacity', 100), step = 5, key=f"opacity_{idx}")
            crop.remove_bg = o1.checkbox("Remove background", value=getattr(crop, 'visible', True), key=f"remove_bg_{idx}")
            crop.visible = o2.checkbox("Visible", value=getattr(crop, 'visible', True), key=f"visible_{idx}")
            

            b1,b2 = st.columns(2)
            crop.add_border = b1.checkbox("Add black border", value=crop.add_border, key=f"border_{idx}")
            crop.border_thickness = b2.number_input(
                "Border thickness", 1, 20,
                getattr(crop, 'border_thickness', 3),
                key=f"border_thickness_{idx}"
            )

            d1, d2 = st.columns(2)
            delete_clicked = d1.button("Delete", key=f"delete_{idx}", use_container_width=True)
            confirm = d2.checkbox("Confirm delete", key=f"confirm_{idx}",width="stretch")

            if delete_clicked and confirm:
                del st.session_state['crops'][idx]
                st.success(f"Crop '{crop.name}' deleted.")
                st.rerun()
                return

        with col2:
            # Teljes oldalkép preview piros kerettel
            preview_max_width = placement_preview_width
            aspect_ratio = page_img.width / page_img.height
            preview_w = preview_max_width
            preview_h = int(preview_w / aspect_ratio)
            preview_img = page_img.resize((preview_w, preview_h), Image.LANCZOS).copy()

            draw = ImageDraw.Draw(preview_img)

            # Méretezett crop pozíciója a preview-n
            scaled_crop_w = int(crop.width * crop.scale * (preview_w / page_img.width))
            scaled_crop_h = int(crop.height * crop.scale * (preview_h / page_img.height))
            center_x = preview_w // 2 + int(crop.offset_x * (preview_w / page_img.width))
            center_y = preview_h // 2 + int(crop.offset_y * (preview_h / page_img.height))
            left = center_x - scaled_crop_w // 2
            top = center_y - scaled_crop_h // 2
            right = center_x + scaled_crop_w // 2
            bottom = center_y + scaled_crop_h // 2

            border_thickness = max(1, getattr(crop, 'border_thickness', 3))
            for i in range(border_thickness):
                rect = [left - i, top - i, right + i, bottom + i]
                draw.rectangle(rect, outline="red")

            st.image(preview_img, caption=f"Full page preview with crop: {crop.name}", width=preview_max_width)

        
        if not crop.visible:
            continue

        composed = place_crop_on_page(composed, Crop(
            box=crop.box,
            crop_img_orig=crop.crop_img_orig,
            add_border=crop.add_border,
            border_thickness=crop.border_thickness,
            name=crop.name,
            width=crop.width,
            height=crop.height,
            aspect_ratio=crop.aspect_ratio,
            offset_x=crop.offset_x,
            offset_y=crop.offset_y,
            scale=crop.scale,
            visible=crop.visible,
            opacity=crop.opacity,
            remove_bg= crop.remove_bg
        ))

    st.markdown("## 🖼️ Final Composition (All Crops Placed)")
    st.image(composed, use_container_width =True)

    if st.button("Reset all crop positions & scales"):
        for c in st.session_state['crops']:
            c.offset_x = 0
            c.offset_y = 0
            c.scale = 1.0
            c.add_border = False
            c.visible = True
            c.opacity = 100
            c.border_thickness = 3
        st.rerun()

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
    qr_padding: int = 0,
    qr_position: str = "bottom-right",
) -> Image.Image:
    img = base_img.copy()

    # Ha nincs cím, csak térj vissza a sima képpel esetleg QR-rel
    if not title_text.strip():
        # QR kód hozzáadása, ha meg van adva
        if qr_text.strip():
            qr_img = generate_qr_code_with_border(qr_text.strip(), qr_size,border_size=qr_padding)
            if qr_position == "top-left":
                pos = (0, 0)
            elif qr_position == "top-right":
                pos = (img.width - qr_img.width, 0)
            elif qr_position == "bottom-left":
                pos = (0, img.height - qr_img.height)
            else:
                pos = (img.width - qr_img.width, img.height - qr_img.height)
            img.paste(qr_img, pos, qr_img)
        return img

    # 1. Betöltjük a fontot és kiszámoljuk a cím magasságát
    font, success = load_custom_font(font_path, font_size)
    dummy_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bbox = dummy_draw.textbbox((0, 0), title_text, font=font)
    title_height = bbox[3] - bbox[1]
    margin = int(img.height * 0.03)
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
        qr_img = generate_qr_code_with_border(qr_text.strip(), qr_size,border_size=qr_padding)
        if qr_position == "top-left":
            pos = (0, 0)
        elif qr_position == "top-right":
            pos = (target_width - qr_img.width, 0)
        elif qr_position == "bottom-left":
            pos = (0, target_height - qr_img.height)
        else:
            pos = (target_width - qr_img.width, target_height - qr_img.height)
        new_canvas.paste(qr_img, pos, qr_img)

    return new_canvas

# --- MAIN APP ---

def app():
    st.set_page_config(page_title="ArtWork")
    st.title("Artwork - an article preview creator")

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
    main_idx = st.session_state.get("main_page", 1) - 1
    page_img = images[main_idx].convert("RGBA")
        
    page_height_px = int(page_sizes_mm[page_size][1] * output_dpi / 25.4)
    page_size_px = tuple(int(dim * output_dpi / 25.4) for dim in page_sizes_mm[page_size])

    st.session_state['page_height_px'] = page_height_px
    scaled_page_img = scale_image(page_img, *page_size_px)



    # --- Add title and QR last ---
    title_text = st.sidebar.text_input("Optional Title", "")
    
    f_min, f_max, f_def, f_step = adjust_vals(12, 72, 24, 1, min_ratio=0.01,max_ratio=0.05)
    font_size_pt = st.sidebar.slider("Title Font Size (pt)", f_min, f_max,  f_def, f_step)
    
    font_path = "montserrat.ttf"

    
    stroke_width = st.sidebar.slider("Title Stroke Width", 1, 10, 1, 1)
    with_underline = st.sidebar.checkbox("Underline Title", value=False)

    st.sidebar.divider()


    qr_text = st.sidebar.text_area("QR Code Text (max 200 chars)", max_chars=200)
    qr_position = st.sidebar.selectbox("QR Code position", ["top-left", "top-right", "bottom-left", "bottom-right"], index = 1)

    qr_min, qr_max, qr_default, qr_step = adjust_vals(100, 500, 200, 25,min_ratio=0.1,max_ratio=0.5)
    qr_size = st.sidebar.slider("QR Code size",qr_min, qr_max, qr_default, qr_step)
    
    qr_p_min, qr_p_max, qr_p_default, qr_p_step = adjust_vals(50, 250, 50, 10,min_ratio=0.01,max_ratio=0.2)
    qr_padding = st.sidebar.slider("QR Code padding", qr_p_min, qr_p_max, qr_p_default, qr_p_step)
    

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
        qr_position=qr_position
    )

    st.markdown("## 🧾 Final Output with QR")
    st.image(final_img, use_container_width =True)


    # --- Export final image ---
    st.subheader("💾 Export Final Image")
    png_bytes = export_image_to_png(final_img, output_dpi)
    st.download_button(
        "Download Final PNG",
        data=png_bytes,
        file_name="final_output.png",
        mime="image/png"
    )

if __name__ == "__main__":
    app()
