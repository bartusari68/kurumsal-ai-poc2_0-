from pathlib import Path
from PIL import Image, ImageOps, ImageDraw

folder = Path(__file__).parent
pages = sorted(folder.glob('page-*.png'))
for start in range(0, len(pages), 8):
    sheet = Image.new('RGB', (1600, 1050), '#e7e7e7')
    draw = ImageDraw.Draw(sheet)
    for offset, path in enumerate(pages[start:start+8]):
        thumb = ImageOps.contain(Image.open(path).convert('RGB'), (380, 480))
        x = (offset % 4) * 400 + (400-thumb.width)//2
        y = (offset // 4) * 525 + 30
        sheet.paste(thumb, (x, y))
        draw.text(((offset % 4)*400+16, (offset//4)*525+8), f'PDF PAGE {start+offset+1}', fill='#222222')
    sheet.save(folder / f'contact-{start+1:02d}-{min(start+8,len(pages)):02d}.jpg', quality=90)
print(f'{len(pages)} pages included')
