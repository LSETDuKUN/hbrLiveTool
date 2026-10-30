from . import theme
from .overdrive import action_background
"""Standalone action-axis tables and paginated PNGs, independent of visible UI."""
import html
import json
from pathlib import Path
from .history import table_rows, actor_title, skill_title, beneficiary_title,skill_summary,summary_text


def cells(row):
    result = [[(row['values'][0], False)]]
    for slot in row['slots']:
        lines = []
        for event in slot:
            lines.extend([(skill_title(event), True), (actor_title(event), False)])
            if beneficiary_title(event):
                lines.append(('→ '+beneficiary_title(event), False))
        result.append(lines or [('/', False)])
    return result


def save_axis(data, path, portraits=False):
    path = Path(path)
    rows = list(table_rows(data['actions']).values())
    if path.suffix.lower() == '.html':
        body = []
        from .axis_portraits import Images, event_html
        images = Images()
        for row in rows:
            row_open='<tr style="background:'+action_background(row['group'],theme.CARD)+'">'
            if portraits:
                label = '<td>'+html.escape(row['values'][0])+'</td>'
                if (row['group'] or {}).get('kind') == 'instant':
                    body.append(row_open+label+'<td colspan="3">'+''.join(event_html(e, images) for e in row['events'])+'</td></tr>')
                else:
                    body.append(row_open+label+''.join('<td>'+(''.join(event_html(e, images) for e in slot) or '/')+'</td>' for slot in row['slots'])+'</tr>')
                    if row['unplaced']:
                        body.append('<tr><td>站位未确认</td><td colspan="3">'+''.join(event_html(e, images) for e in row['unplaced'])+'</td></tr>')
                continue
            if (row['group'] or {}).get('kind') == 'instant':
                body.append(row_open+'<td>'+html.escape(row['values'][0])+'</td><td colspan="3"><strong>'+
                    html.escape(' / '.join(e['skill'] for e in row['events']))+'</strong><br>不占指令 · '+
                    html.escape(' / '.join(actor_title(e) for e in row['events']))+'</td></tr>')
                continue
            columns = ['<td>'+ '<br>'.join(
                ('<strong>'+html.escape(text)+'</strong>') if bold else html.escape(text)
                for text, bold in cell)+'</td>' for cell in cells(row)]
            body.append(row_open+''.join(columns)+'</tr>')
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
.event{display:flex;align-items:center;justify-content:center;gap:14px;min-height:76px;flex-wrap:wrap}.event img{flex-shrink:0;object-fit:contain}.event strong{min-width:0}
</style><h1>HBR Live · 行动轴</h1>'''
        for color,token in {'#201d32': 'BG', '#f7f0ff': 'FG', '#605077': 'LINE', '#bdb1d4': 'DIM', '#ffd398': 'GOLD', '#f5aacb': 'PINK', '#83e5ed': 'CYAN', '#302b46': 'CARD', '#252137': 'SURFACE'}.items():
            page=page.replace(color,getattr(theme,token))
        page += '<p>'+html.escape(str(data.get('run_id') or '本场战斗'))+'</p>'
        if data.get('history_mode')=='planned':
            page+='<h2>计划技能汇总</h2><p>本场计划使用的技能；小按钮另有标记。</p>'
            for actor in skill_summary(data['actions']):
                page+='<div class="event">'+images.markup(actor.get('style_label'),actor_title(actor))
                for skill in actor['skills']:
                    label=skill['name']+(' · 小按钮' if skill['instant'] else '')
                    page+='<span style="border:1px solid '+theme.LINE+';border-radius:8px;padding:6px 10px;background:'+theme.GOLD_DEEP+';color:'+theme.GOLD+'">'+html.escape(label)+'</span>'
                if actor['unknown']:page+='<span>预选未读到</span>'
                page+='</div>'
        page += '<table><thead><tr><th>回合</th><th>左</th><th>中</th><th>右</th></tr></thead><tbody>'
        page += ''.join(body)+'</tbody></table><details><summary>展开完整记录与伤害详情</summary><pre>'+details+'</pre></details></html>'
        path.write_text(page, encoding='utf-8')
        return [path]
    if path.suffix.lower() != '.png':
        raise ValueError('请选择 .png 图片或 .html 表格。')
    if portraits:
        from .axis_portraits import save_portrait_png
        outputs=save_portrait_png(data, rows, path)
    else:outputs=save_png(data, rows, path)
    if data.get('history_mode')=='planned':prepend_summary(outputs[0],data)
    return outputs


def prepend_summary(path,data):
    from PIL import Image,ImageDraw,ImageFont
    from .axis_portraits import Images
    images=Images();font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',22)
    measure=ImageDraw.Draw(Image.new('RGB',(1,1)))
    blocks=[]
    with Image.open(path) as original:
        base=original.convert('RGB')
    for actor in skill_summary(data['actions']):
        photo=images.get(actor.get('style_label'))
        text='\n'.join(s['name']+(' · 小按钮' if s['instant'] else '') for s in actor['skills'])
        if actor['unknown']:text+='\n预选未读到'
        if not photo:text=actor_title(actor)+'\n'+text
        lines=[];line=''
        for char in text:
            if char=='\n':
                lines.append(line);line='';continue
            if line and measure.textlength(line+char,font=font)>base.width-140:lines.append(line);line=''
            line+=char
        lines.append(line);blocks.append((photo,lines,max(80,len(lines)*40+20)))
    height=54+sum(b[2] for b in blocks)
    result=Image.new('RGB',(base.width,height+base.height),theme.BG);draw=ImageDraw.Draw(result)
    draw.text((24,12),'计划技能汇总',font=font,fill=theme.PINK)
    y=54
    for photo,lines,h in blocks:
        if photo:result.paste(photo,(24,y+(h-photo.height)//2),photo)
        for i,line in enumerate(lines):
            top=y+5+i*40
            draw.rounded_rectangle((94,top,112+measure.textlength(line,font=font),top+36),radius=8,fill=theme.GOLD_DEEP,outline=theme.LINE)
            draw.text((102,top+3),line,font=font,fill=theme.GOLD)
        y+=h
    result.paste(base,(0,height));result.save(path)


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
    block_groups = []
    for row in rows:
        previous_blocks=len(blocks)
        if (row['group'] or {}).get('kind') == 'instant':
            for event in row['events']:
                blocks.append([wrap(row['values'][0], False, widths[0]),
                    wrap(event['skill'], True, widths[1])+wrap('不占指令 · '+actor_title(event), False, widths[1]), [], []])
            block_groups.extend([row['group']]*(len(blocks)-previous_blocks))
            continue
        columns = cells(row)
        wrapped = [[line for text, strong in cell for line in wrap(text, strong, width)]
                   for cell, width in zip(columns, widths)]
        blocks.append(wrapped)
        # Never drop actions whose front-line position was unavailable.
        for event in row['unplaced']:
            blocks.append([wrap('站位未确认', False, widths[0]),
                           wrap(event['skill'], True, widths[1])+wrap(actor_title(event), False, widths[1]), [], []])
        block_groups.extend([row['group']]*(len(blocks)-previous_blocks))
    pages, current, height = [], [], 110
    for block,group in zip(blocks,block_groups):
        # Split unusually long cells without truncating their content.
        for offset in range(0, max(map(len, block)), 180):
            part = [cell[offset:offset+180] for cell in block]
            row_height = max(map(len, part))*32+24
            if current and height+row_height > 7200:
                pages.append((current, height))
                current, height = [], 110
            current.append((part, row_height,group))
            height += row_height
    pages.append((current, height))
    outputs = []
    for number, (page, height) in enumerate(pages, 1):
        image = Image.new('RGB', (1600, height+20), theme.BG)
        draw = ImageDraw.Draw(image)
        draw.text((24, 12), f'HBR Live · 行动轴  {data.get("run_id") or ""}  ({number}/{len(pages)})',
                  font=normal, fill=theme.PINK)
        x = 0
        for title, width in zip(('回合', '左', '中', '右'), widths):
            draw.text((x+width/2, 64), title, font=bold, anchor='mt', fill=theme.CYAN)
            x += width
        y = 110
        for index, (columns, row_height,group) in enumerate(page):
            draw.rectangle((0, y, 1600, y+row_height), fill=action_background(group,theme.CARD if index%2 == 0 else theme.SURFACE))
            x = 0
            for cell, width in zip(columns, widths):
                line_y = y+(row_height-len(cell)*32)/2
                for text, strong in cell:
                    draw.text((x+width/2, line_y), text, font=fonts[strong], anchor='mt',
                              fill=theme.GOLD if strong else theme.DIM)
                    line_y += 32
                x += width
            y += row_height
        output = path if number == 1 else path.with_name(f'{path.stem}-{number:02d}.png')
        image.save(output)
        outputs.append(output)
    return outputs
