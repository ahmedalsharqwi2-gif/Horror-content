# قناة الرعب — Pipeline مجاني بالكامل، نشر تلقائي بدون مراجعة

مبني على: Groq (سيناريو مُشكّل) + Pexels (كليبات حقيقية) + edge-tts (صوت بشري
+ ترجمة متزامنة) + ffmpeg (مونتاج وحرق الترجمة) + GitHub Actions (تنسيق ونشر
مباشر) + Buffer (نشر فعلي على يوتيوب)

**النظام بينشر تلقائيًا بدون أي تدخل بشري، مرتين يوميًا: 3 عصرًا و7 مساءً
بتوقيت القاهرة.**

## خطوات التجهيز (مرة واحدة بس)

### 1. اعمل ريبو جديد على GitHub وارفعله المشروع ده
```bash
git init
git add .
git commit -m "initial setup"
git remote add origin https://github.com/USERNAME/horror-content-pipeline.git
git push -u origin main
```

### 2. جيب الـ API Keys المجانية (كلها مجانية 100%)
| المفتاح | من فين | مجاني؟ |
|---|---|---|
| `GROQ_API_KEY` | https://console.groq.com/keys | ✅ مجاني بالكامل |
| `PEXELS_API_KEY` | https://www.pexels.com/api/ | ✅ مجاني بالكامل |
| `BUFFER_ACCESS_TOKEN` | https://buffer.com → Settings → Apps | ✅ مجاني (Free plan) |
| `BUFFER_CHANNEL_ID` | من نفس صفحة Buffer، بعد ربط قناة اليوتيوب | ✅ |

### 3. ضيف المفاتيح في GitHub Secrets
Settings → Secrets and variables → Actions → New repository secret
ضيف كل مفتاح من الجدول فوق (ملحوظة: GITHUB_TOKEN بييجي تلقائي، مش محتاج تضيفه).

### 4. استضافة الفيديو (بيتم تلقائيًا)
`publish_buffer.py` برفع الفيديو النهائي كـ asset في GitHub Release خاص
بالمشروع (اسمه `media-assets`) عشان ياخد رابط عام، وبعدين يبعت الرابط ده لـ
Buffer. مفيش أي إعداد إضافي مطلوب منك هنا.

### 5. جرّبه يدويًا الأول
Actions tab → Create and Publish Horror Episode → Run workflow

⚠️ **تنبيه:** التشغيل اليدوي أو التلقائي بينشر على طول على قناتك الحقيقية —
مفيش خطوة مراجعة أو موافقة في النسخة دي. لو عايز تراجع قبل النشر، قولي
وأرجّعلك بوابة المراجعة.

## إزاي الدورة بتشتغل (مرتين يوميًا تلقائيًا)

```
3 عصرًا / 7 مساءً بتوقيت القاهرة (cron)
   │
   ▼
generate_script.py   → يكتب قصة رعب جديدة مُشكّلة بالكامل + كلمات بحث بصرية
   │
   ▼
fetch_clips.py        → يجيب كليبات حقيقية من Pexels (بدون تكرار)
   │
   ▼
generate_voice.py     → صوت بشري طبيعي + ملف ترجمة متزامن مع كل كلمة (.srt)
   │
   ▼
assemble_video.py     → فيديو 9:16 نهائي، بحد أقصى 178 ثانية، والترجمة محروقة
                         قريب من أعلى الشاشة (تحت كاميرا الموبايل مباشرة)
   │
   ▼
publish_buffer.py     → نشر تلقائي فوري عبر Buffer — بدون انتظار موافقة
```

## إعدادات ممكن تحب تعدّلها

- **مواعيد النشر**: في `.github/workflows/create-draft.yml`، سطور الـ `cron`.
  مضبوطة حاليًا على 13:00 و17:00 UTC (= 3 عصرًا و7 مساءً بتوقيت القاهرة الثابت
  UTC+2). لو غيّرت توقيتك، عدّل الرقمين.
- **طول الفيديو الأقصى**: `MAX_DURATION_SECONDS` في `scripts/assemble_video.py`
  (مضبوط على 178 ثانية، أمان تحت حد الـ 180 ثانية المشترك بين يوتيوب شورتس
  وإنستجرام ريلز وتيك توك).
- **مكان الترجمة على الشاشة**: `SUBTITLE_STYLE` في نفس الملف، القيمة
  `MarginV=230` بتتحكم في المسافة من أعلى الشاشة.
- **عدد الكلمات في كل ظهور ترجمة**: `WORDS_PER_CAPTION_CHUNK` في
  `scripts/generate_voice.py` (مضبوط على 2).

## التعديل على قناتين تانيين

لما تتأكد إن قناة الرعب شغالة كويس، كرر نفس الهيكل لقناة القطط والتذكير
الإسلامي، بس غيّر:
- `prompts/*.md` (نص الـ system prompt)
- كلمات البحث الافتراضية في Pexels
- الصوت المستخدم في `generate_voice.py`

كل قناة تبقى في ريبو منفصل (أو مجلد منفصل في نفس الريبو مع workflows منفصلة).

