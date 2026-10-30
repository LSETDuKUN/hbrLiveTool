from . import theme
from .overdrive import action_background
"""Self-contained portrait exports, using the same local style identity as the UI."""
import base64
import html
import io
from .history import actor_title, skill_title, beneficiary, beneficiary_title
from .portraits import portrait_path


class Images:
    def __init__(self):
        self.cache = {}

    def get(self, label):
        from PIL import Image
        if label not in self.cache:
            picture = None
            path = portrait_path(label)
            if path:
                try:
                    with Image.open(path) as source:
                        picture = source.convert('RGBA')
                        picture.thumbnail((56, 56), Image.Resampling.LANCZOS)
                except OSError:
                    pass
            self.cache[label] = picture
        return self.cache[label]

    def markup(self, label, title):
        picture = self.get(label)
        escaped = html.escape(title, quote=True)
        if picture is None:
            return '<span>'+escaped+'</span>'
        stream = io.BytesIO()
        picture.save(stream, format='PNG')
        return f'<img width="56" height="56" alt="{escaped}" title="{escaped}" src="data:image/png;base64,{base64.b64encode(stream.getvalue()).decode()}">'


def event_html(event, images):
    content = images.markup(event.get('style_label'), actor_title(event))
    content += '<strong>'+html.escape(skill_title(event))+'</strong>'
    target = beneficiary(event)
    if target:
        content += '<span>→</span>'+images.markup(target.get('style_label'), beneficiary_title(event))
    return '<div class="event">'+content+'</div>'


def save_portrait_png(data, rows, path):
    from PIL import Image, ImageDraw, ImageFont
    images = Images()
    normal = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 20)
    bold = ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc', 24)
    measure = ImageDraw.Draw(Image.new('RGB', (1, 1)))

    def wrap(text, font, width):
        lines = []
        for paragraph in text.splitlines() or ['']:
            line = ''
            for char in paragraph:
                if line and measure.textlength(line+char, font=font)>width:
                    lines.append(line)
                    line = ''
                line += char
            lines.append(line)
        return lines

    def event_tile(event, width, bg):
        photo = images.get(event.get('style_label'))
        target = beneficiary(event)
        parts = []
        if photo:
            parts.append((photo, 56, 56, None, None))
            text_width = min(max(100, width-(216 if target else 100)), measure.textlength(skill_title(event), font=bold)+4)
            lines = wrap(skill_title(event), bold, text_width)
            parts.append((lines, text_width, len(lines)*32, bold, theme.GOLD))
            if target:
                parts.append((['→'], 26, 32, normal, theme.CYAN))
                target_photo = images.get(target.get('style_label'))
                if target_photo:
                    parts.append((target_photo, 56, 56, None, None))
                else:
                    lines = wrap(target.get('name') or '友方', normal, 66)
                    parts.append((lines, 66, len(lines)*28, normal, theme.CYAN))
        else:
            text = skill_title(event)+'\n'+actor_title(event)
            if target:
                text += '\n→ '+beneficiary_title(event)
            lines = wrap(text, normal, width-40)
            parts.append((lines, width-40, len(lines)*32, normal, theme.GOLD))
        height = int(max(80, max(p[2] for p in parts)+24))
        tile = Image.new('RGB', (width, height), bg)
        draw = ImageDraw.Draw(tile)
        x = (width-sum(p[1] for p in parts)-14*(len(parts)-1))/2
        for content, part_width, part_height, font, color in parts:
            if font is None:
                tile.paste(content, (int(x+(part_width-content.width)/2), int((height-content.height)/2)), content)
            else:
                step = part_height/len(content)
                for n, line in enumerate(content):
                    draw.text((x+part_width/2, (height-part_height)/2+(n+.5)*step), line,
                              font=font, fill=color, anchor='mm')
            x += part_width+14
        return tile

    tiles = []
    def add_row(label, slots, bg, span=False):
        widths = [1380] if span else [460]*3
        columns = [[event_tile(e, width, bg) for e in slot] for slot,width in zip(slots,widths)]
        labels = wrap(label, normal, 196)
        height = max(88, len(labels)*28+24, max(sum(t.height for t in col) for col in columns))
        tile = Image.new('RGB', (1600, height), bg)
        draw = ImageDraw.Draw(tile)
        for n,line in enumerate(labels):
            draw.text((110, height/2+(n-(len(labels)-1)/2)*28), line, font=normal, fill=theme.CYAN, anchor='mm')
        x = 220
        for column,width in zip(columns,widths):
            y = (height-sum(t.height for t in column))//2
            for part in column:
                tile.paste(part,(x,y));y+=part.height
            if not column:
                draw.text((x+width/2,height/2),'/',font=normal,fill=theme.DIM,anchor='mm')
            x += width
        for top in range(0,height,7000):
            tiles.append(tile.crop((0,top,1600,min(height,top+7000))))
    for index,row in enumerate(rows):
        bg = action_background(row['group'],theme.CARD if index%2==0 else theme.SURFACE)
        if (row['group'] or {}).get('kind') == 'instant':
            add_row(row['values'][0], [row['events']], bg, True)
        else:
            add_row(row['values'][0], row['slots'], bg)
            if row['unplaced']:
                add_row('站位未确认', [row['unplaced']], bg, True)
    pages, page, height = [], [], 112
    for tile in tiles:
        if page and height+tile.height>7200:
            pages.append(page);page=[];height=112
        page.append(tile);height+=tile.height
    pages.append(page)
    outputs = []
    for number,page in enumerate(pages,1):
        image = Image.new('RGB',(1600,132+sum(t.height for t in page)),theme.BG)
        draw = ImageDraw.Draw(image)
        draw.text((24,16),f'HBR Live · 行动轴  {data.get("run_id") or ""}  ({number}/{len(pages)})',font=normal,fill=theme.PINK)
        for x,title in zip((110,450,910,1370),('回合','左','中','右')):
            draw.text((x,78),title,font=bold,fill=theme.CYAN,anchor='mm')
        y=112
        for tile in page:
            image.paste(tile,(0,y));y+=tile.height
        output = path if number==1 else path.with_name(f'{path.stem}-{number:02d}.png')
        image.save(output);outputs.append(output)
    return outputs
