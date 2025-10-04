import base64, io, os, random, json
from typing import List, Dict
import requests
from PIL import Image, ImageDraw, ImageFont

# ----- Env & config -----
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINTEREST_TOKEN = os.getenv("PINTEREST_ACCESS_TOKEN")
BOARD_ID = os.getenv("PINTEREST_BOARD_ID")
STORE_URL = os.getenv("SPIRALWICK_STORE_URL")
BRAND = os.getenv("SPIRALWICK_BRAND", "Spiralwick Candles")
DAILY_PINS = int(os.getenv("DAILY_PINS", "1"))
UTM_SOURCE = os.getenv("UTM_SOURCE", "pinterest")
UTM_CAMPAIGN = os.getenv("UTM_CAMPAIGN", "organic_pins")
DRY_RUN = os.getenv("DRY_RUN", "0") == "1"   # set DRY_RUN=1 secret to test safely

def red(s):
    if not s: return "MISSING"
    return f"{s[:4]}…{s[-4:]}" if len(s) > 10 else "SET"

print("[env] BOARD_ID:", BOARD_ID)
print("[env] OPENAI_API_KEY:", red(OPENAI_API_KEY))
print("[env] PINTEREST_ACCESS_TOKEN:", red(PINTEREST_TOKEN))
print("[env] SPIRALWICK_STORE_URL:", STORE_URL)
print("[env] DRY_RUN:", DRY_RUN)

# ---- your products (edit names/urls later) ----
PRODUCTS: List[Dict] = [
    {"name":"Spiralwick Twisted Taper — Ivory","color":"ivory","shape":"twisted taper","scent":"unscented","url":STORE_URL},
    {"name":"Spiralwick Bubble Cube — Blush Pink","color":"blush pink","shape":"bubble cube","scent":"rose & peony","url":STORE_URL},
    {"name":"Spiralwick Ribbed Pillar — Forest Green","color":"forest green","shape":"ribbed pillar","scent":"evergreen","url":STORE_URL},
]
SCENE_STYLES = [
    "minimalist flat-lay on linen with soft morning light and gentle shadows",
    "cozy living room vignette with books and a ceramic tray, golden-hour light",
    "spa setting with marble, eucalyptus sprigs, and steam softly blurred",
    "festive table with subtle fairy lights and bokeh, elegant and clean",
    "Nordic interior styling with oak, matte ceramics, and neutral palette",
]
HASHTAGS = ["#candles","#homedecor","#aesthetic","#candlemaking","#cozyhome","#minimalism","#giftideas","#relaxation","#pinterestinspired"]

# ---- OpenAI endpoints ----
OPENAI_URL_IMG = "https://api.openai.com/v1/images/generations"
OPENAI_URL_CHAT = "https://api.openai.com/v1/chat/completions"
HEADERS_OAI = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}

def ai_copy(product: Dict, scene: str) -> Dict:
    body = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system","content":"You are a concise ecommerce copywriter."},
            {"role":"user","content": f"""
            Write Pinterest metadata for a product Pin.
            Product: {product['name']}. Color: {product['color']}. Shape: {product['shape']}. Scent: {product['scent']}.
            Scene: {scene}. Return JSON keys: title, description, alt.
            """}
        ],
        "temperature": 0.6
    }
    try:
        r = requests.post(OPENAI_URL_CHAT, headers=HEADERS_OAI, json=body, timeout=60)
        if r.status_code >= 300:
            print("[openai] copy error:", r.status_code, r.text)
            raise RuntimeError("OpenAI copy failed")
        content = r.json()["choices"][0]["message"]["content"]
        try:
            data = json.loads(content)
        except Exception:
            data = {"title": content[:90], "description": content, "alt": content[:120]}
        return data
    except Exception as e:
        print("[openai] copy fallback:", repr(e))
        title = f"{BRAND} • {product['shape'].title()} in {product['color'].title()}"
        desc = f"Sculptural {product['shape']} candle by {BRAND} in {product['color']}."
        alt = f"{product['color']} {product['shape']} candle in styled scene"
        return {"title": title, "description": desc, "alt": alt}

def placeholder_img(text: str):
    W, H = 1024, 1024
    img = Image.new("RGB", (W, H), (245, 242, 238))
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    d.multiline_text((40, 40), text, fill=(40,40,40), font=font, spacing=6)
    return img

def ai_image(product: Dict, scene: str):
    if DRY_RUN or not OPENAI_API_KEY:
        return placeholder_img(f"{BRAND}\n{product['shape']} • {product['color']}")
    body = {"model":"gpt-image-1","prompt":
            f"Photorealistic {product['shape']} candle in {product['color']} by {BRAND} in a {scene}.",
            "size":"1024x1024","n":1}
    try:
        r = requests.post(OPENAI_URL_IMG, headers=HEADERS_OAI, json=body, timeout=120)
        if r.status_code >= 300:
            print("[openai] image error:", r.status_code, r.text)
            raise RuntimeError("OpenAI image failed")
        b64 = r.json()["data"][0]["b64_json"]
        from PIL import Image
        return Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
    except Exception as e:
        print("[openai] image fallback:", repr(e))
        return placeholder_img(f"{BRAND}\n{product['shape']} • {product['color']}")

def add_watermark(img, text: str = None):
    text = text or BRAND
    im = img.copy()
    d = ImageDraw.Draw(im)
    W, H = im.size
    font = ImageFont.load_default()
    tw, th = d.textbbox((0,0), text, font=font)[2:]
    x, y = W - tw - 16, H - th - 16
    d.rectangle([x-6, y-6, x+tw+6, y+th+6], fill=(255,255,255))
    d.text((x,y), text, fill=(30,30,30), font=font)
    return im

# ---- Pinterest API ----
PINS_URL = "https://api.pinterest.com/v5/pins"
HEADERS_PIN = {"Authorization": f"Bearer {PINTEREST_TOKEN}", "Content-Type": "application/json"}

def post_pin(image, title: str, description: str, alt: str, link_url: str):
    if DRY_RUN or not (PINTEREST_TOKEN and BOARD_ID):
        print("[dry-run] Would post pin:", {"title": title, "link": link_url, "alt": alt})
        return {"id": "dry_run"}
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=92)
    payload = {
        "title": title,
        "description": description,
        "alt_text": alt,
        "board_id": BOARD_ID,
        "link": link_url,
        "media_source": {
            "source_type":"image_base64",
            "content_type":"image/jpeg",
            "data": base64.b64encode(buf.getvalue()).decode()
        },
    }
    r = requests.post(PINS_URL, headers=HEADERS_PIN, json=payload, timeout=60)
    if r.status_code >= 300:
        print("[pinterest] error:", r.status_code, r.text)
        r.raise_for_status()
    return r.json()

def build_link(url: str) -> str:
    sep = '&' if '?' in url else '?'
    return f"{url}{sep}utm_source={UTM_SOURCE}&utm_medium=social&utm_campaign={UTM_CAMPAIGN}"

def run_once():
    product = random.choice(PRODUCTS)
    scene = random.choice(SCENE_STYLES)
    print("[run] product:", product["name"])
    print("[run] scene:", scene)
    meta = ai_copy(product, scene)
    img = ai_image(product, scene)
    branded = add_watermark(img)
    link = build_link(product.get("url") or STORE_URL)
    res = post_pin(branded, meta["title"], meta["description"], meta["alt"], link)
    print("[done] pin id:", res.get("id"))

if __name__ == "__main__":
    pins = max(1, DAILY_PINS)
    for _ in range(pins):
        run_once()
