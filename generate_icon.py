"""Generate the J.A.R.V.I.S. blue/turquoise Windows icon assets."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)
image = Image.new("RGBA", (512, 512), (7, 20, 38, 255))
glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
gd = ImageDraw.Draw(glow)
gd.ellipse((76, 76, 436, 436), outline=(56, 224, 208, 190), width=28)
image = Image.alpha_composite(image, glow.filter(ImageFilter.GaussianBlur(22)))
draw = ImageDraw.Draw(image)
draw.ellipse((82, 82, 430, 430), outline=(56, 224, 208, 255), width=15)
draw.ellipse((116, 116, 396, 396), outline=(57, 139, 255, 255), width=8)
draw.arc((145, 145, 367, 367), 210, 510, fill=(56, 224, 208, 255), width=12)
draw.ellipse((240, 92, 272, 124), fill=(56, 224, 208, 255))
draw.ellipse((240, 388, 272, 420), fill=(57, 139, 255, 255))
draw.line((310, 185, 310, 300), fill=(235, 250, 255, 255), width=30)
draw.arc((190, 260, 340, 370), 0, 180, fill=(235, 250, 255, 255), width=30)
image.resize((256, 256), Image.Resampling.LANCZOS).save(ASSETS / "jarvis.png")
image.save(ASSETS / "jarvis.ico", format="ICO",
           sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
print("Generated assets/jarvis.png and assets/jarvis.ico")
