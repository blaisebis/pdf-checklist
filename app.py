from flask import Flask, render_template, request, redirect, url_for, send_from_directory
import os
import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont
import io
import re

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
OUTPUT_FILE = "P-253_FILLED.pdf"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ✅ PDF FILLING CODE (merged in)
def get_section_type(page_text):
    text = page_text.upper()
    if "BUILDING AUTOMATION" in text:
        return "BUILDING_AUTOMATION"
    elif "ELECTRICAL" in text:
        return "ELECTRICAL"
    elif "FENESTRATION" in text:
        return "FENESTRATION"
    else:
        return "HVAC_PLUMBING"

def get_check_columns(section_type):
    if section_type == "BUILDING_AUTOMATION":
        return [0, 1, 4, 2]
    elif section_type == "ELECTRICAL":
        return [0, 1, 3]
    elif section_type == "FENESTRATION":
        return [0, 1]  # ✅ Only QCR & CxA
    else:
        return [0, 1, 2]

def find_table_rows_and_columns(page):
    text_dict = page.get_text("dict")
    numbered_items = []
    column_headers = []

    for block in text_dict["blocks"]:
        if "lines" not in block:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                text = span["text"].strip()
                bbox = span["bbox"]
                if re.match(r'^\d+\.$', text) and bbox[1] > 100:
                    numbered_items.append({
                        'number': int(text[:-1]),
                        'y': bbox[1],
                        'x': bbox[0],
                        'bbox': bbox
                    })
                if text in ["QCR", "CxA", "MC", "EC", "CC", "TABC", "MD", "ED"]:
                    column_headers.append({
                        'name': text,
                        'x': bbox[0] + (bbox[2] - bbox[0]) / 2,
                        'y': bbox[1],
                        'bbox': bbox
                    })

    numbered_items.sort(key=lambda x: (x['y'], x['number']))
    column_headers.sort(key=lambda x: x['x'])
    return numbered_items, column_headers

def is_cell_empty(page, row_y, col_x, tolerance=20):
    cell_rect = fitz.Rect(col_x - tolerance, row_y - 10, col_x + tolerance, row_y + 10)
    cell_text = page.get_text("text", clip=cell_rect).strip()
    return len(cell_text) == 0 or cell_text in [" ", "\n", "\t"]

def process_page(page, font_check, font_na):
    page_text = page.get_text()
    section_type = get_section_type(page_text)
    check_columns = get_check_columns(section_type)

    table_rows, column_headers = find_table_rows_and_columns(page)

    pix = page.get_pixmap(dpi=150)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    draw = ImageDraw.Draw(img)

    for row in table_rows:
        row_y_pdf = row['y']
        row_y_img = row_y_pdf * (150/72)
        for col_idx, col_header in enumerate(column_headers):
            col_x_pdf = col_header['x']
            col_x_img = col_x_pdf * (150/72)

            if not is_cell_empty(page, row_y_pdf, col_x_pdf):
                continue

            text_x = col_x_img - 10
            text_y = row_y_img - 5

            if col_idx in check_columns:
                draw.text((text_x, text_y), u"\u2713", font=font_check, fill="black")  # Unicode checkmark
            else:
                draw.text((text_x, text_y), "N/A", font=font_na, fill="black")

    return img

def fill_pdf(input_pdf, output_pdf):
    try:
        # Load fonts (seguiemj.ttf has ✓ on Windows)
        font_check = ImageFont.truetype("seguiemj.ttf", 22)
        font_na = ImageFont.truetype("arial.ttf", 16)
    except:
        font_check = ImageFont.load_default()
        font_na = ImageFont.load_default()

    doc = fitz.open(input_pdf)
    processed_pages = []

    for page_num in range(len(doc)):
        processed_img = process_page(doc[page_num], font_check, font_na)
        processed_pages.append(processed_img)

    if processed_pages:
        processed_pages[0].save(output_pdf, "PDF", save_all=True, append_images=processed_pages[1:])

    doc.close()

# ✅ FLASK ROUTES
@app.route("/", methods=["GET"])
def index():
    filename = request.args.get("filename")
    return render_template("index.html", filename=filename)

@app.route("/upload", methods=["POST"])
def upload():
    if "pdf" not in request.files:
        return redirect(url_for("index"))
    file = request.files["pdf"]
    if file.filename == "":
        return redirect(url_for("index"))

    filepath = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
    file.save(filepath)

    fill_pdf(filepath, OUTPUT_FILE)
    return redirect(url_for("index", filename=OUTPUT_FILE))

@app.route("/uploads/<filename>")
def download(filename):
    return send_from_directory(".", filename, as_attachment=True)


