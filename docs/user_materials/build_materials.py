"""Build Filipino PinyaSense handouts as PDF and editable DOCX (local only)."""
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether

OUT = Path(__file__).resolve().parent
GREEN = '#145A42'
GOLD = '#E7B647'
INK = '#243B32'
PALE = '#EDF5EF'
pdfmetrics.registerFont(TTFont('Arial', 'C:/Windows/Fonts/arial.ttf'))
pdfmetrics.registerFont(TTFont('ArialBold', 'C:/Windows/Fonts/arialbd.ttf'))
pdfmetrics.registerFontFamily('Arial', normal='Arial', bold='ArialBold', italic='Arial', boldItalic='ArialBold')
styles = getSampleStyleSheet()
for name, size, leading, after in [('Body',10.2,14.1,7), ('Small',9,12,5), ('Heading',13,17,8), ('TitleLocal',27,31,12), ('Subtitle',12,17,12), ('Cell',9.3,12.4,0)]:
    styles.add(ParagraphStyle(name, fontName='ArialBold' if name in ('Heading','TitleLocal') else 'Arial', fontSize=size, leading=leading, spaceAfter=after, textColor=colors.HexColor(GREEN if name in ('Heading','TitleLocal') else INK)))
styles.add(ParagraphStyle('Scale', parent=styles['Small'], backColor=colors.HexColor(PALE), borderPadding=8, spaceAfter=13))

def p(text, kind='Body'):
    return ('p', kind, text)

def h(text):
    return p(text,'Heading')

def table(headers, rows, widths):
    return ('table', headers, rows, widths)

def page():
    return ('break',)

FLYER = [
    p('PINYASENSE', 'TitleLocal'),
    p('Katuwang sa pagmamanman ng taniman ng pinya', 'Subtitle'),
    p('Isang web-based system na pinagsasama ang pagsusuri ng larawan, pagsubaybay sa halumigmig ng lupa, at pagkontrol ng patubig. Para sa mga magsasaka at awtorisadong tagapangasiwa ng taniman.'),
    h('Ano ang magagawa nito?'),
    table(['Tampok', 'Gamit sa taniman'], [
        ['Pagsusuri ng larawan', 'Mag-upload o kumuha ng larawan ng pinya upang makita ang prediksiyon ng system at confidence score. May batch photo at video upload din.'],
        ['Soil Moisture', 'Tingnan ang readings at history ng lupa sa apat na zone, depende sa nakakabit na sensors.'],
        ['Water Pump', 'Kontrolin ang pump gamit ang ON, OFF, o Run 2s. May automatic watering at daily/weekly schedules kapag naka-configure.'],
        ['Mga tala at ulat', 'Balikan ang detection records at i-export ang datos bilang CSV o PDF.'],
        ['Forecast', 'Tingnan ang pagtataya sa paglaki at pag-aani batay sa impormasyong inilagay sa system.'],
    ], [0.29,0.71]),
    h('Mabilis na paggamit'),
    p('<b>1. Mag-log in.</b> Buksan ang system address na ibinigay ng administrator at gamitin ang aprubadong account.'),
    p('<b>2. Mag-upload at magsuri.</b> Piliin ang Upload Photo o Open Camera, saka pindutin ang Detect Disease.'),
    p('<b>3. Tingnan ang lupa at patubig.</b> Buksan ang Soil Moisture at Water Pump; tiyaking tama ang zone, oras ng reading, at aktuwal na lagay ng device.'),
    p('<b>4. Balikan ang mga tala.</b> Suriin ang resulta at mag-export ng ulat kung kinakailangan.'),
    p('Ang detection at forecast ay mga pagtataya. Ang confidence score ay hindi garantiya ng tamang pagkilala. Ang pump at sensors ay nangangailangan ng maayos na hardware at koneksiyon.', 'Scale'),
    p('<b>System address:</b> __________________________________________<br/><b>Administrator / contact:</b> ___________________________________', 'Small'),
]

MANUAL = [
    p('PINYASENSE', 'TitleLocal'),
    p('User Manual • Gabay sa system at device', 'Subtitle'),
    h('1. Bago gamitin'),
    p('Ihanda ang phone, tablet, o computer na may browser; system address mula sa administrator; aprubadong account; at malinaw na larawan ng pinya. Para sa device functions, kailangang nakakonekta at naka-configure ang controller, sensors, relay, at water pump.'),
    p('Gumagamit ang setup ng Raspberry Pi para sa controller at may suporta sa Arduino bridge para sa apat na soil moisture zone. Ang eksaktong koneksiyon at sensor type ay dapat kumpirmahin sa administrator ng inyong unit.'),
    p('<b>Paunang pagsusuri:</b> Tiyaking tuyo at protektado ang controller at power connections. Suriin ang pagkakakabit ng sensors, hose, at suplay ng tubig. Ipagawa sa administrator ang wiring at calibration; patayin muna ang power bago galawin ang mga koneksiyon.'),
    h('2. Pagbukas at pag-log in'),
    p('1. Ipa-on sa operator ang device at system service. Ikonekta ang browser device sa network na may access sa system.'),
    p('2. Buksan ang address na ibinigay ng administrator. Sa lokal na network, maaaring ganito ang format: <b>http://&lt;IP-ng-controller&gt;:5001</b>. Gamitin ang aktuwal na address ng inyong unit.'),
    p('3. Sa Login, ilagay ang email at password. Kung bagong user, piliin ang Sign Up/Create Account at kumpletuhin ang hinihinging detalye. Maaaring kailanganin ang admin approval bago makapasok ang staff account.'),
    p('4. Kapag nakapasok, buksan ang Home/dashboard. Kung pending ang account, kontakin ang administrator.'),
    h('3. Pagsusuri ng larawan ng pinya'),
    p('1. Sa <b>Upload &amp; Analyze</b>, piliin ang <b>Upload Photo</b> o <b>Open Camera</b>. Gumamit ng JPG, JPEG, o PNG na malinaw at may sapat na liwanag.'),
    p('2. Ituon ang larawan sa dahon o bunga na susuriin. Iwasan ang malabong kuha at mga bagay na tumatakip sa pinya. Suriin ang preview bago magpatuloy.'),
    p('3. Pindutin ang <b>Detect Disease</b> at hintayin ang resulta. Basahin ang label, confidence score, at ipinakitang rekomendasyon.'),
    p('4. Kung hindi matukoy ang pinya o hindi malinaw ang resulta, kumuha ng mas malinaw na larawan at subukan muli. May <b>Batch Upload</b> para sa maraming larawan at <b>Upload Video</b> para sa suportadong video files.'),
    p('Ang resulta ay prediksiyon mula sa larawan. Hindi nito napapatunayan ang sanhi ng sakit. Ipa-verify sa kwalipikadong agricultural technician ang resulta bago gumawa ng desisyong nakabatay rito.', 'Scale'),
    page(),
    h('4. Pagtingin sa soil moisture'),
    p('1. Buksan ang <b>Soil Moisture</b> sa menu. Tingnan ang bawat zone at ang oras ng pinakahuling reading.'),
    p('2. Basahin ang ipinakitang sensor value at status. Maaaring ADC/raw value, relative percentage, o digital WET/DRY ang output, depende sa configuration.'),
    table(['Ipinakita sa screen', 'Paano babasahin'], [
        ['DRY / TOO DRY', 'Nasa tuyong bahagi ng configured scale. Kumpirmahin ang sensor placement at aktuwal na lagay ng lupa.'],
        ['NORMAL / MOIST', 'Nasa gitnang bahagi ng configured scale, kung analog ang sensor.'],
        ['WET / TOO WET', 'Nasa basang bahagi ng configured scale. Suriin muna ang lupa bago magdagdag ng tubig.'],
        ['Last saved reading / error', 'Maaaring lumang tala o walang sariwang reading. Tingnan ang timestamp at koneksiyon.'],
    ], [0.31,0.69]),
    p('3. Sa history, piliin ang saklaw na 1, 6, 12, 24, o 48 oras para makita ang available na pagbabago sa readings.'),
    p('Ang relative moisture percentage ay batay sa calibration ng sensor. Huwag itong ituring na eksaktong dami ng tubig sa lupa. Ang digital WET/DRY sensor ay state lamang, hindi continuous percentage.', 'Small'),
    h('5. Manual na paggamit ng water pump'),
    p('1. Buksan ang <b>Water Pump</b>. Suriin ang <b>Pump Status</b>, tubig, hose, at power/breaker ng inyong unit.'),
    p('2. Piliin ang <b>Run 2s</b> para sa maikling pagsubok, o <b>ON</b> para paandarin ang pump. Bantayan ang aktuwal na daloy ng tubig.'),
    p('3. Pindutin ang <b>OFF</b> kapag sapat na ang patubig. Gamitin ang <b>Refresh</b> at kumpirmahin na huminto ang aktuwal na pump.'),
    h('6. Automatic watering at schedules'),
    p('<b>Automatic:</b> Sa Automatic Watering, piliin ang <b>Enable Auto</b> kung nais gamitin ang configured dry-soil rule. Gamitin ang <b>Disable Auto</b> upang ihinto ang awtomatikong pag-trigger. Ang tagal, pagitan, at zone policy ay itinatalaga ng administrator.'),
    p('<b>Schedule:</b> Ilagay ang schedule name, Every day o Specific days, oras, at duration in seconds. Pumili ng mga araw kung weekly, saka <b>Save schedule</b>. Suriin ang saved entry at status; gamitin ang Delete kung aalisin ito.'),
    p('Kapag naka-ON ang automatic watering, nilalaktawan ng system ang fixed-time schedules. Kailangan ding tumatakbo ang scheduler para maisagawa ang mga ito. Ipakumpirma sa administrator ang timezone ng device bago magtakda ng oras.', 'Scale'),
    page(),
    h('7. Pagtingin at pag-export ng ulat'),
    p('1. Sa Home/dashboard, tingnan ang available na detection records at trends. Ang makikitang records ay maaaring nakadepende sa access ng account.'),
    p('2. Sa <b>Export Data</b>, piliin ang <b>Export as CSV</b> para sa spreadsheet o <b>Export as PDF</b> para sa printable report.'),
    p('3. Buksan ang downloaded file at kumpirmahin ang petsa at mga record bago gamitin o ibahagi.'),
    p('Sa <b>Diseases</b>, makikita ang impormasyong nakalagay sa system. Sa <b>Forecast</b>, sundin ang mga field para sa plant/growth records at tingnan ang available na estimates. Nakadepende ang pagtataya sa input at configuration; hindi ito garantisadong petsa ng ani.'),
    h('8. Karaniwang problema at paunang aksiyon'),
    table(['Problema', 'Paunang aksiyon'], [
        ['Hindi mabuksan ang system', 'Kumpirmahin ang address, network, power ng controller, at kung tumatakbo ang service. Ipa-check sa administrator kung hindi pa rin ma-access.'],
        ['Hindi makapasok ang account', 'Suriin ang email/password at account approval. Gamitin ang password recovery kung available o kontakin ang administrator.'],
        ['Hindi tanggap ang upload', 'Gumamit muna ng malinaw na JPG/PNG. Suriin ang file format at size limit; ulitin gamit ang mas maliit na file kung kinakailangan.'],
        ['Walang bago o kakaibang reading', 'Tingnan ang timestamp, zone, placement, at cable. Ipa-check ang Arduino bridge o sensor connection at calibration.'],
        ['Hindi gumagana ang pump', 'Kumpirmahin ang tubig, breaker, at power. Basahin ang error sa screen; ipasuri sa operator ang relay at pump.'],
        ['Hindi tumakbo ang schedule', 'Suriin kung naka-ON ang Auto, tama ang oras/araw, at available ang scheduler.'],
    ], [0.31,0.69]),
    h('9. Pangangalaga at pagtatapos'),
    p('Linisin ang dumi sa sensor ayon sa tagubilin ng operator at suriin ang kaagnasan o maluwag na cable. Panatilihing tuyo ang controller, relay, at power supply. Ipa-check ang calibration kapag hindi tugma ang reading sa aktuwal na kondisyon.'),
    p('Bago patayin ang device, i-disable ang Auto at alisin ang mga schedule kung kailangang ihinto ang lahat ng patubig. Pindutin ang OFF at kumpirmahing tumigil ang pump. Ipa-shutdown nang maayos sa operator ang controller bago tanggalin ang power; mag-log out sa shared browser.'),
    p('<b>System address:</b> __________________________________________<br/><b>Administrator / contact:</b> ___________________________________<br/><b>Device / lokasyon:</b> ________________________________________', 'Small'),
]

GROUPS = [
('A. Mga pangunahing gawain', [
    'Nai-upload ko ang larawang pinili ko para sa pagsusuri.',
    'Naipakita ng system ang resulta matapos kong piliin ang Detect Disease.',
    'Nakita ko ang mga naunang detection record na kailangan kong balikan.',
    'Nakuha ko ang ulat sa pinili kong format (CSV o PDF).',
]),
('B. Dali ng paggamit', [
    'Madaling hanapin ang feature na kailangan kong gamitin.',
    'Malinaw sa akin ang mga pangalan ng button at menu.',
    'Madaling basahin ang teksto at mga value sa screen.',
    'Nagagawa ko ang mga pangunahing hakbang nang walang tuloy-tuloy na tulong.',
]),
('C. Bilis ng pagtugon', [
    'Katanggap-tanggap ang oras ng pagbukas ng mga pahina.',
    'Katanggap-tanggap ang paghihintay ko sa pag-upload ng larawan.',
    'Katanggap-tanggap ang paghihintay ko sa detection result.',
    'Katanggap-tanggap ang paghihintay ko sa pag-download ng ulat.',
]),
('D. Linaw at pagpapatuloy ng paggamit', [
    'Natapos ko ang mga sinubukang gawain nang hindi nag-hang ang system.',
    'Nakita kong lumitaw sa history ang natapos kong detection.',
    'Malinaw kung kailan naitala ang ipinakitang resulta o reading.',
    'Naiintindihan ko ang ibig sabihin ng ipinakitang confidence score.',
]),
('E. Device at patubig — sagutan lamang kung nasubukan', [
    'Madaling matukoy kung saang zone kabilang ang soil moisture reading.',
    'Malinaw sa akin ang ipinakitang soil moisture status.',
    'Tumugon ang aktuwal na pump sa manual na ON/OFF command sa aking pagsubok.',
    'Malinaw sa akin kung naka-enable o naka-disable ang automatic watering.',
]),
('F. Pakinabang at pagtanggap', [
    'Nakatulong ang system upang makita ko kung aling halaman ang kailangan pang siyasatin.',
    'Nakatulong ang mga tala upang masubaybayan ko ang mga nakaraang obserbasyon.',
    'Naaangkop ang system sa mga gawain ko sa pagmamanman ng taniman.',
    'Handa akong gamitin ang system sa mga susunod na pagmamanman.',
]),
]

SURVEY = [
    p('PINYASENSE', 'TitleLocal'),
    p('Survey Questionnaire • Pagsusuri pagkatapos gamitin', 'Subtitle'),
    p('<b>Respondent code:</b> ______________  <b>Petsa:</b> ______________'),
    h('Layunin at pakikilahok'),
    p('Layunin ng survey na malaman ang inyong karanasan sa paggamit ng PinyaSense upang matukoy ang mga kailangang pagbutihin. Sagutin ito matapos ang aktuwal na paggamit o guided demonstration. Tinatayang 8–12 minuto ang pagsagot, bukod sa pagsubok sa system.'),
    p('Boluntaryo ang pakikilahok. Maaari kayong lumaktaw sa tanong o huminto anumang oras. Walang tama o maling sagot. Huwag ilagay ang inyong pangalan, password, email, o numero ng telepono sa questionnaire.'),
    p('<b>Mananaliksik / contact:</b> _____________________________________<br/><b>Paaralan / departamento:</b> ____________________________________'),
    p('[  ] Nabasa/ipinaliwanag sa akin ang layunin at pumapayag akong sumagot.<br/>[  ] Hindi ako pumapayag. (Itigil ang pagsagot.)'),
    h('A. Tungkol sa respondent at pagsubok'),
    p('<b>Papel:</b> [  ] Magsasaka  [  ] Tagapangasiwa/staff  [  ] Agricultural technician<br/>[  ] Iba pa: ____________________'),
    p('<b>Karanasan sa pagtatanim/pagmamanman ng pinya:</b><br/>[  ] Wala pa  [  ] Mas mababa sa 1 taon  [  ] 1–5 taon  [  ] Higit sa 5 taon'),
    p('<b>Dalas ng paggamit ng phone/computer:</b><br/>[  ] Araw-araw  [  ] Ilang beses bawat linggo  [  ] Bihira  [  ] Hindi gumagamit'),
    p('<b>Device sa pagsubok:</b> [  ] Phone  [  ] Tablet  [  ] Laptop/desktop<br/><b>Tulong na natanggap:</b> [  ] Wala  [  ] Kaunti  [  ] Madalas'),
    h('Mga gawaing nasubukan — lagyan ng tsek'),
    p('[  ] Pag-log in at pag-navigate<br/>[  ] Pag-upload ng larawan at pagtingin sa detection result<br/>[  ] Pagtingin sa history at pag-export ng CSV/PDF<br/>[  ] Pagtingin sa soil moisture ng mga zone<br/>[  ] Manual na pagsubok ng pump kasama ang operator<br/>[  ] Pag-enable/pag-disable ng Auto kasama ang operator'),
    p('Sagutan batay sa sariling karanasan. Gamitin ang N/A kung hindi nasubukan o hindi sapat ang karanasan upang magbigay ng rating.', 'Scale'),
    page(),
    h('B. Pagtataya sa system'),
    p('Bilugan ang isang sagot sa bawat pahayag. <b>5</b> = Lubos na sumasang-ayon; <b>4</b> = Sumasang-ayon; <b>3</b> = Neutral / walang kinikilingan; <b>2</b> = Hindi sumasang-ayon; <b>1</b> = Lubos na hindi sumasang-ayon; <b>N/A</b> = Hindi nasubukan / hindi mataya.', 'Scale'),
]

counter = 1
for group_index, (label, questions) in enumerate(GROUPS):
    if group_index == 3:
        SURVEY.extend([page(), h('B. Pagtataya sa system — pagpapatuloy'), p('Bilugan ang isang sagot: 5 = Lubos na sumasang-ayon; 4 = Sumasang-ayon; 3 = Neutral / walang kinikilingan; 2 = Hindi sumasang-ayon; 1 = Lubos na hindi sumasang-ayon; N/A = Hindi nasubukan / hindi mataya.', 'Scale')])
    SURVEY.append(h(label))
    rows=[]
    for question in questions:
        rows.append([f'{counter}. {question}', '5   4   3   2   1   N/A'])
        counter += 1
    SURVEY.append(table(['Pahayag', 'Rating'], rows, [0.71,0.29]))
SURVEY.extend([
    h('C. Mungkahi at karagdagang komento'),
    p('25. Aling feature ang pinakanakatulong sa inyo? Bakit?<br/>________________________________________________________________<br/>________________________________________________________________', 'Small'),
    p('26. Anong problema o kalituhan ang naranasan ninyo?<br/>________________________________________________________________<br/>________________________________________________________________', 'Small'),
    p('27. Ano ang pinakamahalagang dapat pagbutihin o idagdag?<br/>________________________________________________________________<br/>________________________________________________________________', 'Small'),
    p('Maraming salamat sa inyong oras at tapat na puna.', 'Small'),
])

def para(text, style='Body'):
    return Paragraph(text, styles[style])

def footer(canvas, doc):
    canvas.saveState()
    width,height=A4
    canvas.setFillColor(colors.HexColor(GREEN))
    canvas.rect(0,height-12,width,12,fill=1,stroke=0)
    canvas.setStrokeColor(colors.HexColor(GOLD))
    canvas.setLineWidth(1)
    canvas.line(43,37,width-43,37)
    canvas.setFont('Arial',8)
    canvas.drawString(43,24,'PINYASENSE  |  Gabay at pagsusuri ng gumagamit  |  v1.0 • 17 Oktubre 2026')
    canvas.drawRightString(width-43,24,f'{doc.page}')
    canvas.restoreState()

def make_pdf(stem, blocks):
    story=[]
    for block in blocks:
        if block[0]=='p':
            story.append(para(block[2],block[1]))
        elif block[0]=='break':
            story.append(PageBreak())
        else:
            _,headers,rows,widths=block
            cells=[[para(x,'Cell') for x in row] for row in [headers]+rows]
            t=Table(cells,colWidths=[(A4[0]-86)*w for w in widths],repeatRows=1,hAlign='LEFT')
            padding = 4 if 'Survey' in stem else 7
            t.setStyle(TableStyle([
                ('BACKGROUND',(0,0),(-1,0),colors.HexColor(GREEN)),
                ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor(PALE)]),
                ('VALIGN',(0,0),(-1,-1),'TOP'),
                ('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),9),
                ('TOPPADDING',(0,0),(-1,-1),padding),('BOTTOMPADDING',(0,0),(-1,-1),padding),
                ('LINEBELOW',(0,0),(-1,0),0.8,colors.HexColor(GOLD)),
            ]))
            for cell in cells[0]:
                cell.style=ParagraphStyle('HeaderCell',parent=styles['Cell'],textColor=colors.white,fontName='ArialBold')
            story.extend([t,Spacer(1,10)])
    doc=SimpleDocTemplate(str(OUT/(stem+'.pdf')),pagesize=A4,rightMargin=43,leftMargin=43,topMargin=36,bottomMargin=48,title=stem.replace('_',' '),author='PinyaSense',pageCompression=0)
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    count=len(re.findall(rb'/Type\s*/Page\b',(OUT/(stem+'.pdf')).read_bytes()))
    expected=1+sum(b[0]=='break' for b in blocks)
    if count != expected:
        raise RuntimeError(f'{stem}: expected {expected} pages, got {count}; adjust layout')
    return count

def runs(text):
    out=[]
    bold=False
    for part in re.split(r'(<b>|</b>|<br\s*/?>)',text):
        if part=='<b>': bold=True
        elif part=='</b>': bold=False
        elif part.startswith('<br'): out.append('<w:r><w:br/></w:r>')
        elif part:
            from html import unescape
            out.append('<w:r>'+('<w:rPr><w:b/></w:rPr>' if bold else '')+'<w:t xml:space="preserve">'+escape(unescape(part))+'</w:t></w:r>')
    return ''.join(out)

def docx_p(text, style='Body', white=False):
    body=runs(text)
    if white:
        body=body.replace('<w:r>','<w:r><w:rPr><w:color w:val="FFFFFF"/><w:b/></w:rPr>')
    return f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr>{body}</w:p>'

def make_docx(stem, blocks):
    body=[]
    for block in blocks:
        if block[0]=='p': body.append(docx_p(block[2],block[1]))
        elif block[0]=='break': body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
        else:
            _,headers,rows,widths=block
            colwidths=[round(10180*w) for w in widths]
            props='<w:tblPr><w:tblW w:w="10180" w:type="dxa"/><w:tblLayout w:type="fixed"/><w:tblCellMar><w:top w:w="95" w:type="dxa"/><w:left w:w="120" w:type="dxa"/><w:bottom w:w="95" w:type="dxa"/><w:right w:w="120" w:type="dxa"/></w:tblCellMar></w:tblPr>'
            xml=['<w:tbl>',props,'<w:tblGrid>'+''.join(f'<w:gridCol w:w="{w}"/>' for w in colwidths)+'</w:tblGrid>']
            for i,row in enumerate([headers]+rows):
                xml.append('<w:tr><w:trPr><w:cantSplit/>'+('<w:tblHeader/>' if i==0 else '')+'</w:trPr>')
                for value,width in zip(row,colwidths):
                    fill='145A42' if i==0 else ('EDF5EF' if i%2==0 else 'FFFFFF')
                    xml.append(f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/><w:shd w:fill="{fill}"/></w:tcPr>'+docx_p(value,'Cell',i==0)+'</w:tc>')
                xml.append('</w:tr>')
            xml.append('</w:tbl>')
            body.extend(xml)
            body.append(docx_p('','Small'))
    ns='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    document=f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="{ns}"><w:body>'+''.join(body)+'<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="650" w:right="860" w:bottom="850" w:left="860"/></w:sectPr></w:body></w:document>'
    stylexml=[f'<?xml version="1.0" encoding="UTF-8"?><w:styles xmlns:w="{ns}"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:sz w:val="20"/><w:lang w:val="fil-PH"/></w:rPr></w:rPrDefault></w:docDefaults>']
    for name,size,after,bold in [('Body',20,120,False),('Small',18,80,False),('Scale',18,180,False),('Cell',18,0,False),('Heading',26,100,True),('TitleLocal',54,140,True),('Subtitle',24,140,False)]:
        keep='<w:keepNext/>' if name in ('Heading','TitleLocal','Subtitle') else ''
        stylexml.append(f'<w:style w:type="paragraph" w:styleId="{name}"><w:name w:val="{name}"/><w:pPr>{keep}<w:spacing w:after="{after}" w:line="260" w:lineRule="auto"/></w:pPr><w:rPr><w:sz w:val="{size}"/>'+('<w:b/><w:color w:val="145A42"/>' if bold else '')+'</w:rPr></w:style>')
    stylexml.append('</w:styles>')
    with ZipFile(OUT/(stem+'.docx'),'w',ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')
        z.writestr('_rels/.rels','<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr('word/_rels/document.xml.rels','<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr('word/document.xml',document)
        z.writestr('word/styles.xml',''.join(stylexml))

if __name__=='__main__':
    for stem,blocks in [('01_PinyaSense_Flyer',FLYER),('02_PinyaSense_User_Manual',MANUAL),('03_PinyaSense_Survey_Questionnaire',SURVEY)]:
        pages=make_pdf(stem,blocks)
        make_docx(stem,blocks)
        print(f'{stem}: PDF ({pages} pages) + DOCX created')
