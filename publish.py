"""publish.py — اختبر معلوماتك التربوية: سؤال اليوم -> فيديو -> YouTube Short."""
import argparse
import os
import sys
from datetime import datetime, timezone

from fetch_trivia import get_random_question, record_question
from generate_video import build_trivia_video

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POSTS_DIR = os.path.join(BASE_DIR, "posts")
REQUIRED_ENV = ["YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"]


def post_to_youtube(video_path, q):
    from youtube_upload import upload_short

    title = f"{q['question']} #shorts"
    if len(title) > 100:
        title = q["question"][:88].rstrip() + "… #shorts"
    description = (
        f"{q['question']}\n\n"
        f"الجواب الصحيح: {q['correct_answer']}\n\n"
        f"التصنيف: {q['category']}\n\n"
        "#تربية #بيداغوجيا #ديداكتيك #التعليم_الابتدائي #علوم_التربية #مباراة_التعليم #shorts"
    )
    return upload_short(video_path, title, description,
                        tags=["بيداغوجيا", "ديداكتيك", "علوم التربية", "التعليم الابتدائي", "مباراة التعليم", "اسئلة تربوية", "shorts"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-upload", action="store_true", help="توليد الفيديو فقط")
    parser.add_argument("--keep", action="store_true", help="الاحتفاظ بالفيديو بعد الرفع")
    args = parser.parse_args()

    missing = [n for n in REQUIRED_ENV if not os.environ.get(n)]
    upload = not args.no_upload and not missing
    if missing and not args.no_upload:
        print(f"متغيرات ناقصة: {missing} — سيتم توليد الفيديو فقط.")

    q = get_random_question()
    print(f"السؤال: {q['question']}\nالجواب: {q['correct_answer']}")

    os.makedirs(POSTS_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    video_path = os.path.join(POSTS_DIR, f"edu_{stamp}.mp4")
    build_trivia_video(q, video_path)
    print("تم توليد الفيديو:", video_path)

    if not upload:
        return 0
    try:
        res = post_to_youtube(video_path, q)
        print("تم النشر، معرّف الفيديو:", res.get("id"))
        record_question(q)
    except Exception as e:
        print("خطأ في YouTube:", e, file=sys.stderr)
        return 1
    if not args.keep:
        os.remove(video_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
