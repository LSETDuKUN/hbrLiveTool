"""Standalone action-axis tables and paginated PNGs, independent of visible UI."""
import html
import json
from pathlib import Path
from .history import table_rows, actor_title, skill_title


def cells(row):
    result = [[(row['values'][0], False)]]
    for slot in row['slots']:
        lines = []
        for event in slot:
            lines.extend([(skill_title(event), True), (actor_title(event), False)])
        result.append(lines or [('/', False)])
    return result


def save_axis(data, path):
    path = Path(path)
    rows = list(table_rows(data['actions']).values())
    if path.suffix.lower() == '.html':
        body = []
        for row in rows:
            if (row['group'] or {}).get('kind') == 'instant':
                body.append('<tr><td>'+html.escape(row['values'][0])+'</td><td colspan="3"><strong>'+
                    html.escape(' / '.join(e['skill'] for e in row['events']))+'</strong><br>不占指令 · '+
                    html.escape(' / '.join(actor_title(e) for e in row['events']))+'</td></tr>')
                continue
            columns = ['<td>'+ '<br>'.join(
                ('<strong>'+html.escape(text)+'</strong>') if bold else html.escape(text)
                for text, bold in cell)+'</td>' for cell in cells(row)]
            body.append('<tr>'+''.join(columns)+'</tr>')
            if row['unplaced']:
                body.append('<tr><td>站位未确认</td><td colspan="3">'+html.escape('；'.join(
                    actor_title(e)+'：'+e['skill'] for e in row['unplaced']))+'</td></tr>')
        details = html.escape(json.dumps(data, ensure_ascii=False, indent=2))
        page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>HBR Live 行动轴</title><style>
body{background:#201d32;color:#f7f0ff;font:16px "Microsoft YaHei",sans-serif;margin:32px}
table{border-collapse:collapse;width:100%;table-layout:fixed}td,th{padding:16px;text-align:center;
border-bottom:1px solid #605077;overflow-wrap:anywhere}td{color:#bdb1d4}strong{color:#ffd398;font-size:19px}
th{color:#f5aacb}pre{white-space:pre-wrap;overflow-wrap:anywhere}summary{cursor:pointer;margin-top:24px}
</style><h1>HBR Live · 行动轴</h1>'''
        page += '<p>'+html.escape(str(data.get('run_id') or '本场战斗'))+'</p>'
        page += '<table><thead><tr><th>回合</th><th>左</th><th>中</th><th>右</th></tr></thead><tbody>'
        page += ''.join(body)+'</tbody></table><details><summary>展开完整记录与伤害详情</summary><pre>'+details+'</pre></details></html>'
        path.write_text(page, encoding='utf-8')
        return [path]
    if path.suffix.lower() != '.png':
        raise ValueError('请选择 .png 图片或 .html 表格。')
    return save_png(data, rows, path)


def save_png(data, rows, path):
    from PIL import Image, ImageDraw, ImageFont
    normal_path = Path('C:/Windows/Fonts/msyh.ttc')
    bold_path = Path('C:/Windows/Fonts/msyhbd.ttc')
    normal = ImageFont.truetype(str(normal_path), 20)
    bold = ImageFont.truetype(str(bold_path if bold_path.exists() else normal_path), 24)
    fonts = {False: normal, True: bold}
    widths = [220, 460, 460, 460]
    measure = ImageDraw.Draw(Image.new('RGB', (1, 1)))

    def wrap(text, strong, width):
        result = []
        for paragraph in str(text).splitlines() or ['']:
            line = ''
            for char in paragraph:
                if line and measure.textlength(line+char, font=fonts[strong]) > width-32:
                    result.append((line, strong))
                    line = ''
                line += char
            result.append((line, strong))
        return result

    blocks = []
    for row in rows:
        if (row['group'] or {}).get('kind') == 'instant':
            for event in row['events']:
                blocks.append([wrap(row['values'][0], False, widths[0]),
                    wrap(event['skill'], True, widths[1])+wrap('不占指令 · '+actor_title(event), False, widths[1]), [], []])
            continue
        columns = cells(row)
        wrapped = [[line for text, strong in cell for line in wrap(text, strong, width)]
                   for cell, width in zip(columns, widths)]
        blocks.append(wrapped)
        # Never drop actions whose front-line position was unavailable.
        for event in row['unplaced']:
            blocks.append([wrap('站位未确认', False, widths[0]),
                           wrap(event['skill'], True, widths[1])+wrap(actor_title(event), False, widths[1]), [], []])
    pages, current, height = [], [], 110
    for block in blocks:
        # Split unusually long cells without truncating their content.
        for offset in range(0, max(map(len, block)), 180):
            part = [cell[offset:offset+180] for cell in block]
            row_height = max(map(len, part))*32+24
            if current and height+row_height > 7200:
                pages.append((current, height))
                current, height = [], 110
            current.append((part, row_height))
            height += row_height
    pages.append((current, height))
    outputs = []
    for number, (page, height) in enumerate(pages, 1):
        image = Image.new('RGB', (1600, height+20), '#201d32')
        draw = ImageDraw.Draw(image)
        draw.text((24, 12), f'HBR Live · 行动轴  {data.get("run_id") or ""}  ({number}/{len(pages)})',
                  font=normal, fill='#f5aacb')
        x = 0
        for title, width in zip(('回合', '左', '中', '右'), widths):
            draw.text((x+width/2, 64), title, font=bold, anchor='mt', fill='#83e5ed')
            x += width
        y = 110
        for index, (columns, row_height) in enumerate(page):
            draw.rectangle((0, y, 1600, y+row_height), fill='#302b46' if index%2 == 0 else '#252137')
            x = 0
            for cell, width in zip(columns, widths):
                line_y = y+(row_height-len(cell)*32)/2
                for text, strong in cell:
                    draw.text((x+width/2, line_y), text, font=fonts[strong], anchor='mt',
                              fill='#ffd398' if strong else '#bdb1d4')
                    line_y += 32
                x += width
            y += row_height
        output = path if number == 1 else path.with_name(f'{path.stem}-{number:02d}.png')
        image.save(output)
        outputs.append(output)
    return outputs
