import streamlit as st
from pathlib import Path

import zipfile, io

import sys

import cv2
import numpy as np
from PIL import Image

# image-statistics-matching repo helyi útvonala, állítsd be megfelelően
sys.path.append("image-statistics-matching")

from matching.operations.histogram_matching import HistogramMatching as HMBase
from matching.operations.feature_distribution_matching import FeatureDistributionMatching as FDMBase

from python_color_transfer.color_transfer import ColorTransfer
from utils.cs_conversion import ChannelRange

from color_transfer import color_transfer

# Kiegészítés: __call__ metódusok hozzáadása, hogy hívható legyen az objektum
class HistogramMatching(HMBase):
    def __call__(self, source, reference):
        return self._apply(source, reference)

class FeatureDistributionMatching(FDMBase):
    def __call__(self, source, reference):
        return self._apply(source, reference)


# A megfelelő channel ranges a repó ChannelRange osztályával
channel_ranges_example = (
    ChannelRange(0.0, 1.0),     # Pl. L csatorna tartomány (normált)
    ChannelRange(0.0, 255.0),   # a csatorna
    ChannelRange(-127.0, 127.0) # b csatorna
)



# Segédfüggvények
def load_image(file) -> np.ndarray:
    img = Image.open(file).convert('RGB')
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

def cv2_to_pil(img: np.ndarray) -> Image.Image:
    # Ha float típusú, akkor uint8-ra alakítjuk [0..255] skálán
    if img.dtype != np.uint8:
        img = np.clip(img, 0, 255)
        img = img.astype(np.uint8)

    # Ha képtömb formátuma például (1,1,3), akkor kis méret probléma nincs, de ellenőrizzük
    if img.ndim != 3 or img.shape[2] != 3:
        raise ValueError(f"A kép dimenziója nem megfelelő: {img.shape}")

    # OpenCV színformátum átváltás
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return Image.fromarray(img_rgb)

def convert_bgr_to_lab(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2Lab)

def convert_lab_to_bgr(img):
    return cv2.cvtColor(img, cv2.COLOR_Lab2BGR)

def scale_to_uint8(img: np.ndarray) -> np.ndarray:
    img_scaled = np.clip(img * 255.0, 0, 255)
    return img_scaled.astype(np.uint8)


def show_previews(input_img, ref_img):
    st.subheader("Pengbo-learn python-color-transfer eredmények")
    PT = ColorTransfer()

    img_pdf = PT.pdf_transfer(img_arr_in=input_img, img_arr_ref=ref_img, regrain=True)
    img_mt = PT.mean_std_transfer(img_arr_in=input_img, img_arr_ref=ref_img)
    img_lt = PT.lab_transfer(img_arr_in=input_img, img_arr_ref=ref_img)

    st.image([cv2_to_pil(img_pdf), cv2_to_pil(img_mt), cv2_to_pil(img_lt)],
             caption=["Pdf transfer + Regrain", "Mean std transfer", "Lab mean transfer"],
             width=250)

    st.subheader("Continental image-statistics-matching eredmények")
    hm = HistogramMatching(channels=(0,1,2))
    try:
        img_hm = hm(input_img.astype(np.float32), ref_img.astype(np.float32))
    except Exception as e:
        st.error(f"HistogramMatching hiba: {str(e)}")
        img_hm = input_img

    lab_input = convert_bgr_to_lab(input_img)
    lab_ref = convert_bgr_to_lab(ref_img)
    try:
        fdm = FeatureDistributionMatching(channels=(1,2), channel_ranges=channel_ranges_example)
        img_fdm_lab = fdm(lab_input.astype(np.float32), lab_ref.astype(np.float32))
        # Skálázás 0-255 és uint8 konverzió
        img_fdm_lab_uint8 = scale_to_uint8(img_fdm_lab)

        # Konvertálás BGR-be
        img_fdm = cv2.cvtColor(img_fdm_lab_uint8, cv2.COLOR_Lab2BGR)
        
        # st.write("FDM output min:", img_fdm.min(), "max:", img_fdm.max(), "dtype:", img_fdm.dtype, "shape:", img_fdm.shape)
        
    except Exception as e:
        st.error(f"FeatureDistributionMatching hiba: {str(e)}")
        img_fdm = input_img

    st.image([cv2_to_pil(img_hm), cv2_to_pil(img_fdm)],
             caption=["Histogram Matching RGB", "Feature Distribution Matching LAB AB"],
             width=250)

    st.subheader("jrosebr1 color_transfer eredmény")
    try:
        img_jrose = color_transfer(input_img.astype(np.uint8), ref_img.astype(np.uint8))
        st.image(cv2_to_pil(img_jrose), caption="jrosebr1 color_transfer", width=250)
    except Exception as e:
        st.error(f"jrosebr1 color_transfer hiba: {str(e)}")


def batch_process(files, ref_img, method_obj, output_dir, use_lab=False, use_jrosebr=False, method_name="output"):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for file in files:
        img = load_image(file)

        try:
            if use_jrosebr:
                out_img = color_transfer(img.astype(np.uint8), ref_img.astype(np.uint8))
            elif use_lab:
                lab_img = convert_bgr_to_lab(img)
                lab_ref = convert_bgr_to_lab(ref_img)
                out_lab = method_obj(lab_img.astype(np.float32), lab_ref.astype(np.float32))
                out_img = convert_lab_to_bgr(out_lab)
            else:
                out_img = method_obj(img.astype(np.float32), ref_img.astype(np.float32))
        except Exception as e:
            st.error(f"Hiba a {file.name} feldolgozásakor: {str(e)}")
            continue

        output_path = output_dir / f"{Path(file.name).stem}_{method_name}.png"
        cv2.imwrite(str(output_path), out_img)

    st.success(f"Batch feldolgozás kész! Kimenet mentve: {output_dir}")


def batch_process_zip(files, ref_img, method_obj, use_lab=False, use_jrosebr=False):
    zip_buffer = io.BytesIO()
    num_files = len(files)

    progress_bar = st.progress(0)
    progress_text = st.empty()

    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
        for idx, file in enumerate(files):
            img = load_image(file)

            try:
                if use_jrosebr:
                    out_img = color_transfer(img.astype(np.uint8), ref_img.astype(np.uint8))
                elif use_lab:
                    lab_img = convert_bgr_to_lab(img)
                    lab_ref = convert_bgr_to_lab(ref_img)
                    out_lab = method_obj(lab_img.astype(np.float32), lab_ref.astype(np.float32))
                    out_img = convert_lab_to_bgr(out_lab)
                else:
                    out_img = method_obj(img.astype(np.float32), ref_img.astype(np.float32))
            except Exception as e:
                st.error(f"Hiba a {file.name} feldolgozásakor: {str(e)}")
                continue

            is_success, buffer = cv2.imencode(".png", out_img)
            if not is_success:
                st.error(f"Hiba képtömörítéskor: {file.name}")
                continue

            zip_file.writestr(f"{Path(file.name).stem}.png", buffer.tobytes())

            progress = (idx + 1) / num_files
            progress_bar.progress(progress)
            progress_text.text(f"Feldolgozva: {idx + 1} / {num_files}")

    zip_buffer.seek(0)
    progress_bar.empty()
    progress_text.empty()

    return zip_buffer.getvalue()


def main():
    st.title("Color Transfer Batch Processor")

    st.sidebar.header("Referencia és Példa kép feltöltés")
    ref_file = st.sidebar.file_uploader("Referencia kép", type=['png', 'jpg', 'jpeg'])
    example_file = st.sidebar.file_uploader("Példa kép", type=['png', 'jpg', 'jpeg'])

    if ref_file and example_file:
        ref_img = load_image(ref_file)
        ex_img = load_image(example_file)

        st.image([cv2.cvtColor(ex_img, cv2.COLOR_BGR2RGB), cv2.cvtColor(ref_img, cv2.COLOR_BGR2RGB)],
                 caption=["Példa kép", "Referencia kép"],
                 width=300)

        show_previews(ex_img, ref_img)

        st.sidebar.header("Batch feldolgozás")
        batch_files = st.sidebar.file_uploader("Feldolgozandó képek", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

        method = st.sidebar.selectbox("Batch feldolgozási módszer kiválasztása",
                                      options=[
                                          "pdf_transfer (pengbo-learn)",
                                          "mean_std_transfer (pengbo-learn)",
                                          "lab_transfer (pengbo-learn)",
                                          "Histogram Matching (continental)",
                                          "Feature Dist Matching (continental)",
                                          "color_transfer (jrosebr1)"
                                      ])


        if st.sidebar.button("Batch feldolgozás indítása") and batch_files:
            PT = ColorTransfer()

            use_lab = False
            use_jrosebr = False

            if method == "pdf_transfer (pengbo-learn)":
                class MethodWrapper:
                    def __call__(self, img, ref):
                        return PT.pdf_transfer(img_arr_in=img, img_arr_ref=ref, regrain=True)

                method_obj = MethodWrapper()
                method_name = "pdf_transfer"

            elif method == "mean_std_transfer (pengbo-learn)":
                class MethodWrapper:
                    def __call__(self, img, ref):
                        return PT.mean_std_transfer(img_arr_in=img, img_arr_ref=ref)

                method_obj = MethodWrapper()
                method_name = "mean_std_transfer"

            elif method == "lab_transfer (pengbo-learn)":
                class MethodWrapper:
                    def __call__(self, img, ref):
                        return PT.lab_transfer(img_arr_in=img, img_arr_ref=ref)

                method_obj = MethodWrapper()
                method_name = "lab_transfer"

            elif method == "Histogram Matching (continental)":
                method_obj = HistogramMatching(channels=(0, 1, 2))
                method_name = "histogram_matching"

            elif method == "Feature Dist Matching (continental)":
                method_obj = FeatureDistributionMatching(channels=(1, 2), channel_ranges=channel_ranges_example)
                use_lab = True
                method_name = "feature_dist_matching"

            elif method == "color_transfer (jrosebr1)":
                method_obj = None
                use_jrosebr = True
                method_name = "color_transfer_jrosebr1"

            zip_bytes = batch_process_zip(batch_files, ref_img, method_obj, use_lab=use_lab, use_jrosebr=use_jrosebr)
            st.success(f"Batch feldolgozás kész! ZIP fájl generálva.")

            st.download_button(
                label="Letöltés ZIP fájl",
                data=zip_bytes,
                file_name="processed_images.zip",
                mime="application/zip"
            )


if __name__ == "__main__":
    main()