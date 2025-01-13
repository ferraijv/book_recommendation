import os
import yaml
import logging
from markdown2 import markdown, Markdown
BLOG_DIR = "blog/posts"

def load_blog_posts():
    posts = []
    for filename in os.listdir(BLOG_DIR):
        if filename.endswith(".md"):
            with open(os.path.join(BLOG_DIR, filename), "r") as file:
                content = file.read()
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    metadata = yaml.safe_load(parts[1])
                    html_content = markdown(parts[2].strip())
                    posts.append({"metadata": metadata, "content": html_content})

    logging.warning(posts)
    return sorted(posts, key=lambda x: x["metadata"]["date"], reverse=True)