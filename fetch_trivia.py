"""
fetch_trivia.py — يولّد سؤالًا تربويًا جديدًا في كل تشغيل (بديل Open Trivia DB للعربية).
- يختار موضوعًا عشوائيًا من TOPICS
- يطلب من نموذج Groq سؤال اختيار من متعدد بصيغة JSON
- يتحقق من الصيغة، ويمنع التكرار عبر history.json، ويراجع صحة الجواب بنداء ثانٍ
المتغيرات: GROQ_API_KEY (مطلوب) — GROQ_MODEL (اختياري)
"""
import json
import os
import random
import re
import time

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_PATH = os.path.join(BASE_DIR, "history.json")
HISTORY_LIMIT = 300
RECENT_IN_PROMPT = 25

API_URL = "https://api.groq.com/openai/v1/chat/completions"
# نماذج Groq الحالية (llama-3.3-70b-versatile لم يعد متاحًا). تُجرَّب بالترتيب عند خطأ 404
MODELS = [m for m in [os.environ.get("GROQ_MODEL"), "openai/gpt-oss-120b", "openai/gpt-oss-20b"] if m]
VERIFY = True       # مراجعة صحة الجواب بنداء ثانٍ (يقلل الأخطاء)
MAX_ATTEMPTS = 6

# (التصنيف الظاهر في الفيديو، وصف الموضوع للنموذج)
TOPICS = [
    ("بيداغوجيا", "البيداغوجيا العامة ومفاهيمها الأساسية (بيداغوجيا الفروق، الخطأ، المشروع، اللعب)"),
    ("ديداكتيك", "الديداكتيك العام: المثلث الديداكتيكي، النقل الديداكتيكي، العقد الديداكتيكي، الوضعية-المشكلة، التمثلات"),
    ("تقويم", "التقويم التربوي: التشخيصي والتكويني والإجمالي، شبكات التقويم، الدعم والمعالجة"),
    ("علم النفس التربوي", "علم النفس التربوي: نظريات التعلم (السلوكية، المعرفية، البنائية)، الدافعية، النمو عند الطفل"),
    ("طرائق التدريس", "طرائق وتقنيات التدريس: الإلقائية، الحوارية، الاكتشاف، العمل بالمجموعات، التعلم الذاتي"),
    ("رواد التربية", "رواد التربية والبيداغوجيا ومفاهيمهم (بياجيه، فيجوتسكي، ديوي، مونتيسوري، بلوم، برونر...)"),
    ("تخطيط الدرس", "تخطيط الدرس وإعداده: الأهداف التربوية، الكفايات، الجذاذة، مراحل الحصة"),
    ("تدبير القسم", "تدبير الفصل الدراسي: الضبط، التحفيز، التعزيز، العلاقة التربوية، العمل بالمستويات المتعددة"),
    ("المنظومة التربوية", "المنظومة التربوية المغربية: الميثاق الوطني للتربية والتكوين، الرؤية الاستراتيجية 2015-2030، القانون الإطار 51.17، التعليم الابتدائي"),
    ("القراءة والكتابة", "ديداكتيك القراءة والكتابة في التعليم الابتدائي (المقاربات الصوتية والكلية، التعلم المبكر للقراءة)"),
    ("الرياضيات", "ديداكتيك الرياضيات في التعليم الابتدائي (العدد، العمليات، حل المسائل، الهندسة)"),
    ("اللغة العربية", "ديداكتيك اللغة العربية في التعليم الابتدائي (القراءة، التعبير، الإملاء، القواعد)"),
]

SYSTEM_PROMPT = (
    "أنت خبير في علوم التربية والبيداغوجيا والديداكتيك، وخاصة التعليم الابتدائي بالمغرب. "
    "تكتب أسئلة اختيار من متعدد دقيقة علميًا باللغة العربية الفصحى لاختبار الأساتذة ومترشحي مباريات التعليم. "
    "تجيب بصيغة JSON فقط."
)


def _parse_json(text):
    try:
        return json.loads(text)
    except ValueError:
        m = re.search(r"\{.*\}", text or "", re.S)
        if m:
            return json.loads(m.group(0))
        raise


def _chat(messages, temperature, retries=3):
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("متغير GROQ_API_KEY غير موجود")
    last = None
    for model in MODELS:
        payload = {"model": model, "messages": messages, "temperature": temperature,
                   "response_format": {"type": "json_object"}, "max_completion_tokens": 2000}
        if model.startswith("openai/gpt-oss"):
            payload["reasoning_effort"] = "low"
        for attempt in range(retries):
            try:
                r = requests.post(API_URL, headers={"Authorization": f"Bearer {key}"},
                                  json=payload, timeout=90)
                if r.status_code in (404, 400) and "model" in r.text.lower():
                    last = f"{model}: HTTP {r.status_code} {r.text[:200]}"
                    print("Groq:", last)
                    break                      # جرّب النموذج التالي
                if r.status_code == 429 or r.status_code >= 500:
                    last = f"{model}: HTTP {r.status_code}"
                    time.sleep(5 * (attempt + 1))
                    continue
                if not r.ok:
                    raise RuntimeError(f"Groq HTTP {r.status_code}: {r.text[:300]}")
                return _parse_json(r.json()["choices"][0]["message"]["content"])
            except (requests.RequestException, ValueError, KeyError) as e:
                last = e
                time.sleep(3)
    raise RuntimeError(f"فشل الاتصال بـ Groq: {last}")


def _norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[ً-ْـ]", "", str(text))).strip()


def load_history():
    try:
        with open(HISTORY_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def record_question(q):
    """يُستدعى بعد النشر الناجح فقط."""
    history = load_history()
    history.append(q["question"])
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history[-HISTORY_LIMIT:], f, ensure_ascii=False, indent=1)


def _validate(item):
    try:
        question = str(item["question"]).strip()
        correct = str(item["correct_answer"]).strip()
        wrong = [str(w).strip() for w in item["wrong_answers"]]
    except (KeyError, TypeError):
        return None
    options = wrong + [correct]
    if len(wrong) != 3 or not question or not all(options):
        return None
    if len({_norm(o) for o in options}) != 4:
        return None
    if len(question) > 150 or any(len(o) > 50 for o in options):
        return None
    if any(bad in _norm(o) for o in options for bad in ("كل ما سبق", "جميع ما سبق", "لا شيء مما")):
        return None
    return question, correct, wrong


def _generate(topic, recent):
    label, hint = topic
    avoid = "\n".join(f"- {r}" for r in recent) or "- (لا يوجد)"
    user = f"""اكتب سؤالًا واحدًا جديدًا في الموضوع: {hint}

الشروط:
- جواب واحد صحيح لا يحتمل الجدل، وثلاثة أجوبة خاطئة معقولة.
- السؤال أقل من 120 حرفًا، وكل جواب أقل من 40 حرفًا.
- لا تذكر تواريخ أو أرقامًا إلا إذا كنت متأكدًا منها تمامًا.
- لا تستعمل «كل ما سبق» ولا «لا شيء مما سبق».
- لا تكرر هذه الأسئلة السابقة ولا تشابهها:
{avoid}

أجب بـ JSON بهذا الشكل فقط:
{{"question": "...", "correct_answer": "...", "wrong_answers": ["...", "...", "..."]}}"""
    return _chat([{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": user}], temperature=0.9)


def _verify(question, correct, wrong):
    options = "\n".join(f"- {o}" for o in wrong + [correct])
    user = f"""راجع هذا السؤال التربوي بدقة:
السؤال: {question}
الخيارات:
{options}
الجواب المعلن: {correct}

هل الجواب المعلن صحيح علميًا، وهو الوحيد الصحيح بين الخيارات؟
أجب بـ JSON فقط: {{"valid": true أو false, "reason": "سبب مختصر"}}"""
    res = _chat([{"role": "system", "content": SYSTEM_PROMPT},
                 {"role": "user", "content": user}], temperature=0)
    return bool(res.get("valid")), res.get("reason", "")


def get_random_question():
    history = load_history()
    seen = {_norm(h) for h in history}
    recent = history[-RECENT_IN_PROMPT:]

    for attempt in range(1, MAX_ATTEMPTS + 1):
        topic = random.choice(TOPICS)
        try:
            parsed = _validate(_generate(topic, recent))
        except RuntimeError as e:
            print(f"محاولة {attempt}: {e}")
            continue
        if not parsed:
            print(f"محاولة {attempt}: صيغة غير صالحة")
            continue
        question, correct, wrong = parsed
        if _norm(question) in seen:
            print(f"محاولة {attempt}: سؤال مكرر")
            continue
        if VERIFY:
            ok, reason = _verify(question, correct, wrong)
            if not ok:
                print(f"محاولة {attempt}: رُفض عند المراجعة — {reason}")
                continue

        answers = wrong + [correct]
        random.shuffle(answers)
        return {
            "question": question,
            "correct_answer": correct,
            "all_answers": answers,
            "correct_index": answers.index(correct),
            "category": topic[0],
        }
    raise RuntimeError("تعذّر توليد سؤال صالح بعد عدة محاولات")


if __name__ == "__main__":
    print(get_random_question())
