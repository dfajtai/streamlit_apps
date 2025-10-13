import os
from typing import Optional,Tuple

import io
import json
from zipfile import ZipFile

import pandas as pd
from PIL import Image

import base64
from io import BytesIO

import streamlit as st
from streamlit_drawable_canvas import st_canvas


# ASSETS_DIR = "streamlit-label-annote/assets"
ASSETS_DIR = "assets"

LOOKUP_CSV = os.path.join(ASSETS_DIR,"tubular-bone-lookup.csv")
LOOKUP_COLS = ["sample","measurement","left-label","right-label"]
LOOKUP_DF = None

COLORS = {"left-label":(255,0,0),"right-label":(0,255,0)}
CROP_PREVIEW_HEIGHT = 160  # px
CROP_PREVIEW_WIDTH = 160   # px


# Init session state keys
if 'current_idx' not in st.session_state:
    st.session_state['current_idx'] = 0
if 'case_loaded' not in st.session_state:
    st.session_state['case_loaded'] = False
if 'loaded_case' not in st.session_state:
    st.session_state['loaded_case'] = None


# ---- VALIDATION ----
def validate_assets()->bool:
    global LOOKUP_DF
    
    if not os.path.exists(ASSETS_DIR):
        st.error(f"ASSETS_DIR={ASSETS_DIR} not exits.")
        return False
    if not os.path.exists(LOOKUP_CSV):
        st.error(f"LOOKUP_CSV={LOOKUP_CSV} not exits.")
        return False
    
    try:
        df = pd.read_csv(LOOKUP_CSV)
        if not all([col in df.columns for col in LOOKUP_COLS]):
            raise ValueError("Missing column")
        
        LOOKUP_DF = df
        return True
                
    except Exception as e:
        st.error(f"Error during processing LOOKUP_CSV:\n{e}")

    return False


def get_all_cases(df: pd.DataFrame) -> list[Tuple[int,int]]:
    """
    Returns sorted list of unique (sample, measurement) tuples.
    Here assuming sample and measurement are integers.
    """
    unique = df[['sample', 'measurement']].drop_duplicates()
    # Convert to tuple list of ints (assumes convertible)
    unique_tuples = [(int(row['sample']), int(row['measurement'])) for _, row in unique.iterrows()]
    return sorted(unique_tuples)


def show_simple_navigator(cases: list[Tuple[int, int]]) -> Tuple[int, int]:
    if 'current_idx' not in st.session_state:
        st.session_state['current_idx'] = 0
    
    total = len(cases)
    
    disable_prev = st.session_state['current_idx'] <= 0
    disable_next = st.session_state['current_idx'] >= total - 1
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        if st.button("Previous", disabled=disable_prev):
            if st.session_state['current_idx'] > 0:
                st.session_state['current_idx'] -= 1
                st.session_state['case_loaded'] = False
    
    with col2:
        if st.button("Next", disabled=disable_next):
            if st.session_state['current_idx'] < total - 1:
                st.session_state['current_idx'] += 1
                st.session_state['case_loaded'] = False
    
    return cases[st.session_state['current_idx']]



def find_case_images(sample: int, measurement: int) -> dict:
    """
    Find images for the given case in assets/{sample}/.
    Returns dict: ct, labelmap, crops (list)
    """
    folder = os.path.join(ASSETS_DIR, f"{sample}-{measurement:02d}")
    files = [] if not os.path.exists(folder) else sorted(os.listdir(folder))
    
    images = {"ct": None, "labelmap": None, "crops": []}
    for f in files:
        fp = os.path.join(folder, f)
        if f.endswith("-ct.png"):
            images["ct"] = fp
        elif f.endswith("-labelmap.png"):
            images["labelmap"] = fp
        elif f.endswith(".png") and "-" in f and not f.endswith("-ct.png") and not f.endswith("-labelmap.png"):
            images["crops"].append(fp)
    
    return images

def resize_and_pad_to_box(im: Image.Image, target_height: int, target_width: int, pad_color=(0,0,0)) -> Image.Image:
    """
    Resize image arányosan a target_height-re, majd pad/crop, hogy pontosan target_width legyen.
    Középre igazítás!
    """
    w, h = im.size
    scale = target_height / h
    new_w = int(w * scale)
    im_resized = im.resize((new_w, target_height))
    # Ha szükséges, bal/jobb oldalt háttér kitöltés
    if new_w < target_width:
        pad_left = (target_width - new_w) // 2
        pad_right = target_width - new_w - pad_left
        new_im = Image.new("RGB", (target_width, target_height), pad_color)
        new_im.paste(im_resized, (pad_left, 0))
        return new_im
    elif new_w > target_width:
        # Ha túl nagy, középről crop
        left = (new_w - target_width) // 2
        right = left + target_width
        return im_resized.crop((left, 0, right, target_height))
    else:
        return im_resized


def pil_image_to_data_url(img: Image.Image) -> str:
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_bytes = buffered.getvalue()
    img_b64 = base64.b64encode(img_bytes).decode()
    return f"data:image/png;base64,{img_b64}"

# PIPELINE
if not validate_assets():
    st.error("Unable to initialize assets.")
    st.stop()

st.title("Streamlit label annote")
st.info(f"Loaded {len(LOOKUP_DF)} rows")

all_cases = get_all_cases(LOOKUP_DF)
selected_sample, selected_measurement = show_simple_navigator(all_cases)

st.write(f"Selected case: Sample={selected_sample}, Measurement={selected_measurement}")

# Filter the DF for the selected case
filtered_df = LOOKUP_DF[
    (LOOKUP_DF['sample'].astype(int) == selected_sample) & 
    (LOOKUP_DF['measurement'].astype(int) == selected_measurement)
]
st.write(filtered_df)

case_key = f"{selected_sample}-{selected_measurement}"

# Load case button
if st.button("Load case"):
    st.session_state['case_loaded'] = True
    st.session_state['loaded_case'] = (selected_sample, selected_measurement)  # Store which case was loaded

# Show loaded case content ONLY if the currently selected case matches the loaded case
if st.session_state['case_loaded'] and st.session_state['loaded_case'] == (selected_sample, selected_measurement):
    images = find_case_images(selected_sample, selected_measurement)
    
    ct_col, label_col = st.columns([1, 1])
    with ct_col:
        if images["ct"] and os.path.exists(images["ct"]):
            st.image(Image.open(images["ct"]), caption="CT", use_container_width=True)
        else:
            st.warning("CT image not found.")

    with label_col:
        if images["labelmap"] and os.path.exists(images["labelmap"]):
            st.image(Image.open(images["labelmap"]), caption="Labelmap", use_container_width=True)
        else:
            st.warning("Labelmap image not found.")

    st.subheader("Cropped label images")
    crops = images.get("crops", [])
    if crops:
        num_cols = 4
        cols = st.columns(num_cols)
        
        label_options = [None]
        for i, crop_path in enumerate(crops):
            col_idx = i % num_cols
            with cols[col_idx]:
                orig_img = Image.open(crop_path)
                img = resize_and_pad_to_box(orig_img, CROP_PREVIEW_HEIGHT, CROP_PREVIEW_WIDTH)
                st.image(img, caption=str(i+1).zfill(2))
                label_options.append(str(i+1).zfill(2))
        
        left_col, right_col = st.columns([1, 1])
        with left_col:
            st.subheader("Left label")
            left_label = st.radio("", label_options, index=0, horizontal=True, key=f"left_label_{case_key}")

        with right_col:
            st.subheader("Right label")
            right_label = st.radio("", label_options, index=0, horizontal=True, key=f"right_label_{case_key}")

        # Show Save button only if both selected and not None
        if left_label is not None and right_label is not None:
            if left_label == right_label:
                if st.button("Draw overlay"):
                    crop_idx = int(left_label) - 1
                    if 0 <= crop_idx < len(crops):
                        crop_path = crops[crop_idx]
                        img = Image.open(crop_path)
                                                
                        st.write(f"Drawing overlay on label: {left_label}")
                        
                        

                        canvas_result = st_canvas(
                            background_image=img,
                            fill_color="rgba(255, 0, 0, 0.3)",
                            stroke_width=3,
                            stroke_color="#FF0000",
                            update_streamlit=True,
                            height=CROP_PREVIEW_HEIGHT,
                            width=CROP_PREVIEW_WIDTH,
                            drawing_mode="freedraw",
                            key=f"canvas_{case_key}_{left_label}",
                        )

                        # if canvas_result.json_data is not None:
                        #     # Itt kimentheted vagy feldolgozhatod a rajzolt adatokat
                        #     st.json(canvas_result.json_data)
            else:
                if st.button("Save"):
                    st.success(f"Saved - Left: {left_label}, Right: {right_label}")
    else:
        st.warning("No cropped label images found.")

# Ha más case van kiválasztva mint a betöltött, jelezd
elif st.session_state['case_loaded'] and st.session_state['loaded_case'] != (selected_sample, selected_measurement):
    st.info("Different case selected. Click 'Load case' to load the current case.")
