import os

import io
import json
from zipfile import ZipFile

import pandas as pd
from PIL import Image

import streamlit as st
from streamlit_drawable_canvas import st_canvas


ASSETS_DIR = "streamlit-label-annote/assets"

LOOKUP_CSV = os.path.join(ASSETS_DIR,"tubular-bone-lookup.csv")
LOOKUP_COLS = ["sample","measurement","left-label","right-label"]
LOOKUP_DF = None

COLORS = {"left-label":(255,0,0),"right-label":(0,255,0)}

st.title("Streamlit label annote")

def validate_assets()->bool:
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

if not validate_assets():
    st.error("Unable to initialize assets.")
    st.stop()
    
st.write(LOOKUP_DF)

