import streamlit as st
import os
from PIL import Image
from streamlit_drawable_canvas import st_canvas
import io
import json
from zipfile import ZipFile

st.title("Streamlit label annote")

try:
    st.info(os.getcwd())
    folders = os.listdir("streamlit-label-annote/assets")
    st.info(f"Folders: {','.join(folders)}")
    
except Exception as ex:
    st.info(ex)

