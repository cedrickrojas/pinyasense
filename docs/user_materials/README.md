# PinyaSense: flyer, user manual, at survey

Mga materyal sa Filipino, bersiyon 1.0, 17 Oktubre 2026.

| File | Nilalaman |
| --- | --- |
| `01_PinyaSense_Flyer.pdf` / `.docx` | Isang pahinang pagpapakilala at mabilis na gabay |
| `02_PinyaSense_User_Manual.pdf` / `.docx` | Pagsisimula, detection, soil moisture, pump, schedules, reports, troubleshooting, at pangangalaga |
| `03_PinyaSense_Survey_Questionnaire.pdf` / `.docx` | Boluntaryong pakikilahok, respondent profile, trial checklist, 24 rating items, at 3 bukas na tanong |

PDF: nakaayos para sa A4 printing. DOCX: editable sa Word o compatible na editor; maaaring bahagyang mag-iba ang pagination ayon sa editor. Punan ang mga blankong system address at administrator/researcher contact bago ipamahagi.

## Para sa mananaliksik / facilitator

Orihinal na draft ang questionnaire para sa proyektong ito. Hindi ito validated instrument, standardized usability scale, o patunay ng pagsunod sa isang quality standard. Ipasuri sa adviser/content validators at mag-pilot test bago gamitin para sa pinal na data collection. Iayon ang consent sa aprubadong research protocol, kabilang ang aktuwal na pag-iingat, access, at retention ng responses; ipaliwanag ito sa respondent bago magsimula.

1. Gumamit ng respondent codes sa halip na pangalan. Ibigay ang contact ng research team. Huwag magpatuloy kung walang pagsang-ayon.
2. Ibigay ang parehong orientation at pangunahing gawain sa lahat: login, upload at detect, pagbasa ng result/history, at export. Itala ang device, koneksiyon, at anumang tulong sa hiwalay na session log.
3. Ipasubok lamang ang pump at Auto sa ligtas at aktuwal na nakakabit na device, kasama ang operator. Kung wala ang hardware, huwag magkunwaring natest ito; N/A ang naaangkop na device items. Hindi pa nasusukat ng questionnaire ang scheduled watering; gumamit ng hiwalay na observed trial kung susuriin iyon.
4. Sagutan ang survey pagkatapos ng pagsubok. Huwag magdikta ng rating. Hayaang magbigay ng negatibong puna ang respondent.
5. Ang rating ay tungkol sa karanasan at pananaw. Ang detection accuracy, sensor calibration, response time, at pump reliability ay nangangailangan ng hiwalay na technical measurements at reference data.

## Pag-code at pag-score

Rating: 5 = Lubos na sumasang-ayon; 4 = Sumasang-ayon; 3 = Neutral / walang kinikilingan; 2 = Hindi sumasang-ayon; 1 = Lubos na hindi sumasang-ayon. N/A at blankong sagot ay missing, hindi zero at hindi neutral.

| Domain | Item numbers |
| --- | --- |
| Mga pangunahing gawain | 1–4 |
| Dali ng paggamit | 5–8 |
| Bilis ng pagtugon | 9–12 |
| Linaw at pagpapatuloy ng paggamit | 13–16 |
| Device at patubig | 17–20 |
| Pakinabang at pagtanggap | 21–24 |

Walang reverse-coded items. Iulat muna ang bilang at porsiyento ng bawat sagot (1–5 at N/A) kada item. Kung gagamit ng mean bilang deskriptibong buod, ang item mean ay kabuuan ng valid ratings na hinati sa bilang ng valid ratings. Iulat ang valid n at N/A count kasama nito.

Maaaring kumuha ng respondent domain mean kung may hindi bababa sa 3 sa 4 valid answers sa domain; kung kulang, markahang missing. Itakda ang patakarang ito bago ang data collection. Kumuha ng mean ng eligible respondent domain means at iulat ang eligible n. Iulat nang hiwalay ang device domain dahil maaaring hindi lahat ay nakasubok ng hardware. Iwasang bumuo ng isang overall score nang walang paunang paliwanag at validation.

Halimbawa: 5, 4, N/A, 3 → (5 + 4 + 3) / 3 = 4.00; valid n = 3; N/A = 1. Ang bukas na sagot sa items 25–27 ay ibuod ayon sa tema, kasama ang mga problemang naiulat. Walang awtomatikong “passed/failed,” accuracy percentage, o quality certification mula sa survey scores.

## Batayan ng nilalaman

Sinuri ang lokal na implementation: `templates/index.html`, `templates/soil_moisture.html`, `templates/water_pump.html`, `templates/login.html`, `templates/signup.html`, `app.py`, `core/sensor_monitor.py`, `core/disease_detector.py`, at setup notes sa `README.md` at `scripts/README.md`.

Nakabatay ang mga hakbang sa interface at code; hindi sa aktuwal na hardware acceptance test. Hindi itinuring ang detection CSVs o generated sensor samples na ebidensiya ng accuracy. Walang admin password o ibang credential na isinama sa mga handout. Nakadepende sa deployed configuration at access ng account ang available na features. Walang live system o hardware na binago sa paggawa ng mga dokumentong ito.

## Muling pagbuo

Mula sa workspace root, gamitin ang kasalukuyang environment na may ReportLab:

```powershell
& .venv311/Scripts/python.exe pinyasense/docs/user_materials/build_materials.py
```

Ginagamit ng generator ang Arial fonts sa Windows at gumagawa ng lokal na PDF at DOCX lamang.
