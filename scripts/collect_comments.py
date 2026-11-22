
import os
import json
import time
import html
import requests
from pathlib import Path
from html.parser import HTMLParser

BLOG = "heatedalien.tumblr.com"
API_KEY = os.environ["TUMBLR_API_KEY"]
BASE = f"https://api.tumblr.com/v2/blog/{BLOG}"

session = requests.Session()
session.headers.update({
    "User-Agent": "HeatedAlienComments/1.0"
})


def api_get(url, params=None):
    params = dict(params or {})
    params["api_key"] = API_KEY

    response = session.get(url, params=params, timeout=30)
    response.raise_for_status()

    data = response.json()

    if data.get("meta", {}).get("status") != 200:
        raise RuntimeError("Tumblr API returned an error.")

    return data.get("response", {})


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def get_text(self):
        return " ".join(" ".join(self.parts).split())


def clean_text(value):
    if not value:
        return ""

    parser = TextExtractor()
    parser.feed(html.unescape(str(value)))
    return parser.get_text()


def post_description(post):
    title = clean_text(post.get("title", ""))
    caption = clean_text(post.get("caption", ""))
    summary = clean_text(post.get("summary", ""))

    return title or caption or summary or "Untitled video"


def get_video_posts():
    posts = []
    offset = 0

    while True:
        data = api_get(
            f"{BASE}/posts/video",
            {"limit": 20, "offset": offset}
        )

        batch = data.get("posts", [])
        posts.extend(batch)

        if len(batch) < 20:
            break

        offset += len(batch)
        time.sleep(0.2)

    return posts


def get_post_comments(post):
    comments = []
    before_timestamp = None
    seen_cursors = set()

    while True:
        params = {
            "id": post.get("id_string", str(post["id"])),
            "mode": "conversation"
        }

        if before_timestamp is not None:
            params["before_timestamp"] = before_timestamp

        data = api_get(f"{BASE}/notes", params)

        for note in data.get("notes", []):
            note_type = note.get("type", "")

            if note_type == "reply":
                text = (
                    note.get("reply_text")
                    or note.get("text")
                    or ""
                )
                kind = "reply"

            elif note_type == "reblog":
                text = (
                    note.get("added_text")
                    or note.get("text")
                    or ""
                )
                kind = "reblog"

            else:
                continue

            text = clean_text(text)

            if not text:
                continue

            comments.append({
                "username": note.get("blog_name", "Unknown"),
                "text": text,
                "type": kind,
                "timestamp": note.get("timestamp", 0),
                "post_title": post_description(post),
                "post_url": post.get("post_url", ""),
                "post_id": str(post.get("id_string", post["id"]))
            })

        next_link = data.get("_links", {}).get("next", {})
        query_params = next_link.get("query_params", {})
        next_cursor = query_params.get("before_timestamp")

        if next_cursor is None:
            break

        if str(next_cursor) in seen_cursors:
            break

        seen_cursors.add(str(next_cursor))
        before_timestamp = next_cursor
        time.sleep(0.2)

    return comments


def main():
    print("Fetching video posts...")
    posts = get_video_posts()
    print(f"Found {len(posts)} video posts.")

    all_comments = []

    for index, post in enumerate(posts, start=1):
        print(f"Checking video {index}/{len(posts)}")

        try:
            all_comments.extend(get_post_comments(post))
        except Exception:
            print(f"Could not retrieve comments for post {post['id']}")
            continue

        time.sleep(0.2)

    all_comments.sort(
        key=lambda item: item.get("timestamp", 0),
        reverse=True
    )

    output = Path("public")
    output.mkdir(exist_ok=True)

    with open(output / "comments.json", "w", encoding="utf-8") as file:
        json.dump(
            all_comments,
            file,
            ensure_ascii=False,
            indent=2
        )

    print(f"Saved {len(all_comments)} comments.")


if __name__ == "__main__":
    main()
