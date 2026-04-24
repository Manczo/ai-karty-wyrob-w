import os
import tempfile
import pandas as pd
import streamlit as st
from io import BytesIO
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# Narzędzia Docling
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend

# ==========================================
# 1. KONFIGURACJA STRONY I INTERFEJSU
# ==========================================
st.set_page_config(page_title="AI Ekstraktor Dokumentów", page_icon="📄", layout="wide")

# CSS ukrywający domyślne elementy Streamlita i poprawiający wygląd
ukryj_menu_style = """
    <style>
    /* Ukrywa menu w prawym górnym rogu */
    #MainMenu {visibility: hidden;}
    
    /* Ukrywa stopkę Streamlit na dole */
    footer {visibility: hidden;}
    
    /* Ukrywa domyślny, pusty nagłówek na samej górze */
    header {visibility: hidden;}
    
    /* Delikatne zaokrąglenie przycisków głównego wyboru */
    .stButton>button {
        border-radius: 6px;
        font-weight: 600;
        transition: all 0.2s ease-in-out;
    }
    
    /* Dodanie delikatnego cienia po najechaniu na przycisk */
    .stButton>button:hover {
        box-shadow: 0px 4px 10px rgba(0, 75, 135, 0.2);
    }
    </style>
    """
st.markdown(ukryj_menu_style, unsafe_allow_html=True)

st.title("🤖 AI Ekstraktor Kart Wyrobu")
st.markdown("Wgraj pliki PDF, a sztuczna inteligencja automatycznie wyciągnie z nich dane i przygotuje plik Excel.")

# Pasek boczny na klucz API
st.sidebar.header("🔑 Konfiguracja")
st.sidebar.markdown("Aby korzystać z aplikacji, musisz podać swój darmowy klucz Google API.")
api_key_input = st.sidebar.text_input("Wklej klucz Google API:", type="password")
st.sidebar.markdown("[Kliknij tutaj, aby wygenerować darmowy klucz](https://aistudio.google.com/app/apikey)")

# ==========================================
# 2. INICJALIZACJA DOCLING (Cache'owanie)
# ==========================================
@st.cache_resource
def laduj_konwerter():
    opcje = PdfPipelineOptions()
    opcje.do_ocr = False 
    opcje.do_table_structure = True
    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=opcje,
                backend=PyPdfiumDocumentBackend
            )
        }
    )

konwerter = laduj_konwerter()

# ==========================================
# 3. PEŁNA STRUKTURA DANYCH
# ==========================================
class KartaWyrobu(BaseModel):
    producent: str = Field(description="Producent, np. Folnet")
    numer_kartoteki: str = Field(description="Numer kartoteki produktu")
    nazwa_wyrobu: str = Field(description="Pełna nazwa wyrobu")
    surowiec: str = Field(description="Z jakiego surowca wykonano produkt")
    ciezar_wyrobu_netto: str = Field(description="Ciężar pojedynczego wyrobu (wraz z jednostką)")
    dodatkowe_informacje_wymiary: str = Field(description="Dodatkowe informacje z sekcji specyfikacji")
    rodzaj_wymiary_opakowania: str = Field(description="Rodzaj i wymiary opakowania, gramatura kartonu")
    ilosc_w_opakowaniu: str = Field(description="Ilość sztuk w opakowaniu jednostkowym")
    ciezar_opakowania_brutto: str = Field(description="Ciężar opakowania jednostkowego brutto")
    etykieta_glowna: str = Field(description="Etykieta główna")
    etykieta_dodatkowa: str = Field(description="Etykieta dodatkowa (lub 'brak')")
    instrukcja_montazu: str = Field(description="Instrukcja montażu (lub 'brak')")
    informacje_o_etykiecie: str = Field(description="Informacje gdzie naklejana jest etykieta na opakowaniu")
    rodzaj_wymiary_palety: str = Field(description="Rodzaj palety i jej wymiary (np. paleta przemysłowa)")
    ilosc_opakowan_warstwa: str = Field(description="Ilość opakowań na jednej warstwie")
    maksymalna_ilosc_warstw: str = Field(description="Maksymalna ilość warstw")
    ilosc_opakowan_na_palecie: str = Field(description="Ilość opakowań na palecie")
    ilosc_sztuk_na_palecie: str = Field(description="Całkowita ilość sztuk na palecie")
    wysokosc_palety_z_zaladunkiem: str = Field(description="Wysokość palety z załadunkiem")
    ciezar_palety_brutto: str = Field(description="Ciężar palety brutto")
    mozliwosc_pietrowania: str = Field(description="Możliwość piętrowania palet (tak/nie)")
    dodatkowe_informacje_paleta: str = Field(description="Dodatkowe informacje dot. paletowania (lub 'brak')")
    inne_informacje_koncowe: str = Field(description="Wszelkie dodatkowe informacje na samym końcu dokumentu")

# ==========================================
# 4. GŁÓWNA LOGIKA APLIKACJI
# ==========================================
# Blokujemy interfejs, jeśli użytkownik nie podał klucza
if not api_key_input:
    st.warning("👈 Proszę wprowadzić klucz Google API w panelu bocznym po lewej stronie, aby odblokować aplikację.")
    st.stop()

# Inicjalizacja AI z kluczem podanym przez użytkownika
try:
    client = genai.Client(api_key=api_key_input)
except Exception as e:
    st.error("Wystąpił problem z konfiguracją klucza API. Upewnij się, że jest poprawny.")
    st.stop()

wgrane_pliki = st.file_uploader("Wybierz pliki PDF do przetworzenia", type=["pdf"], accept_multiple_files=True)

if st.button("🚀 Rozpocznij ekstrakcję danych", type="primary") and wgrane_pliki:
    wszystkie_dane = []
    pasek_postepu = st.progress(0)
    okno_statusu = st.empty()
    
    for i, plik in enumerate(wgrane_pliki):
        okno_statusu.info(f"Przetwarzanie: {plik.name}...")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(plik.getvalue())
            sciezka_tmp = tmp.name
            
        try:
            # Konwersja PDF
            result = konwerter.convert(sciezka_tmp)
            tekst = result.document.export_to_markdown()
            
            # Wysłanie do modelu Gemini
            response = client.models.generate_content(
                model='gemini-2.5-flash-lite',
                contents=tekst,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=KartaWyrobu,
                    temperature=0.1
                )
            )
            dane = KartaWyrobu.model_validate_json(response.text)
            
            rekord = dane.model_dump()
            rekord["plik_zrodlowy"] = plik.name
            wszystkie_dane.append(rekord)
            
        except Exception as e:
            st.error(f"❌ Błąd przy pliku {plik.name}. Treść błędu: {e}")
        finally:
            os.remove(sciezka_tmp)
            
        pasek_postepu.progress((i + 1) / len(wgrane_pliki))
        
    okno_statusu.success("✅ Przetwarzanie zakończone!")
    
    # Generowanie pliku Excel
    if wszystkie_dane:
        df = pd.DataFrame(wszystkie_dane)
        kolumny = ["plik_zrodlowy"] + [col for col in df.columns if col != "plik_zrodlowy"]
        df = df[kolumny]
        
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Baza Wyrobów')
        
        st.dataframe(df)
        
        st.download_button(
            label="📥 Pobierz plik Excel",
            data=output.getvalue(),
            file_name="baza_produktow.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
