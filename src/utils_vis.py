import io
import logging
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

def render_matrix_to_png(df):
    """
    Renders a status matrix dataframe to a PNG image using Pillow.
    """
    # Constants
    CELL_WIDTH = 180
    CELL_HEIGHT = 40
    HEADER_HEIGHT = 50
    INDEX_WIDTH = 300
    
    # Colors
    COLOR_SUCCESS = (209, 247, 209)  # #d1f7d1
    COLOR_PROGRESS = (255, 244, 209)  # #fff4d1
    COLOR_MISSING = (247, 209, 209)   # #f7d1d1
    COLOR_GRID = (210, 210, 210)
    COLOR_TEXT = (40, 40, 40)
    COLOR_HEADER = (245, 245, 245)

    rows = len(df)
    cols = len(df.columns)
    
    width = INDEX_WIDTH + (cols * CELL_WIDTH)
    height = HEADER_HEIGHT + (rows * CELL_HEIGHT)
    
    # Create canvas
    img = Image.new('RGB', (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    # Font loading
    try:
        # macOS Arial
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 16)
        font_bold = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 18)
    except:
        try:
            # Linux typical paths
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
            font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        except:
            font = ImageFont.load_default()
            font_bold = font
    
    # Draw Background for Headers
    draw.rectangle([0, 0, width, HEADER_HEIGHT], fill=COLOR_HEADER)
    
    # Participants Header
    draw.text((15, (HEADER_HEIGHT-20)//2), "Teilnehmer (Name, Vorname)", fill=(0,0,0), font=font_bold)
    
    # Column Headers
    for i, col_name in enumerate(df.columns):
        x = INDEX_WIDTH + i * CELL_WIDTH
        draw.line([x, 0, x, height], fill=COLOR_GRID, width=1)
        draw.text((x + 10, (HEADER_HEIGHT-20)//2), str(col_name), fill=(0,0,0), font=font_bold)

    # Header line
    draw.line([0, HEADER_HEIGHT, width, HEADER_HEIGHT], fill=COLOR_GRID, width=2)

    # Rows
    for r_idx, (person_name, row) in enumerate(df.iterrows()):
        y = HEADER_HEIGHT + r_idx * CELL_HEIGHT
        draw.text((15, y + (CELL_HEIGHT-18)//2), str(person_name), fill=COLOR_TEXT, font=font)
        
        for c_idx, val in enumerate(row):
            x = INDEX_WIDTH + c_idx * CELL_WIDTH
            status = str(val).strip()
            
            fill_color = (255, 255, 255)
            if status == "Absolviert":
                fill_color = COLOR_SUCCESS
            elif status == "In Ausbildung":
                fill_color = COLOR_PROGRESS
            elif status == "Fehlt" or not status:
                fill_color = COLOR_MISSING
                
            draw.rectangle([x+1, y+1, x+CELL_WIDTH-1, y+CELL_HEIGHT-1], fill=fill_color)
            draw.text((x + 10, y + (CELL_HEIGHT-18)//2), status, fill=COLOR_TEXT, font=font)
            
        draw.line([0, y + CELL_HEIGHT, width, y + CELL_HEIGHT], fill=COLOR_GRID, width=1)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def render_pdf_bytes_to_images(pdf_content):
    """
    Renders PDF bytes to a list of PIL images.
    """
    import fitz # PyMuPDF
    images = []
    try:
        doc = fitz.open(stream=pdf_content, filetype="pdf")
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(img)
        doc.close()
    except Exception as e:
        logger.error(f"Failed to render PDF to images: {e}")
    return images
