import streamlit as st
from PIL import Image

st.title("🖼️ Bildanzeige-App")

uploaded_file = st.file_uploader("Lade ein Bild hoch", type=["png", "jpg", "jpeg"])
if uploaded_file:
    image = Image.open(uploaded_file)
    st.image(image, caption="Hochgeladenes Bild", use_column_width=True)
