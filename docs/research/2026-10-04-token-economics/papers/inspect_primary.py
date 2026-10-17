"""Fetch one explicitly versioned primary paper and print targeted context only."""
import argparse
import re
import sys
import urllib.request
from html.parser import HTMLParser

class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.skip += 1
        if tag in {"p", "tr", "h1", "h2", "h3", "h4", "figcaption"}:
            self.parts.append("\n")
        if tag in {"td", "th"}:
            self.parts.append(" | ")

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.skip:
            self.skip -= 1
        if tag in {"p", "tr", "h1", "h2", "h3", "h4", "figcaption"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser()
    p.add_argument("url")
    p.add_argument("terms", nargs="+")
    p.add_argument("--context", type=int, default=1000)
    args = p.parse_args()
    if not re.fullmatch(r"https://arxiv.org/(?:html|abs)/\d{4}\.\d{4,5}v\d+", args.url):
        raise SystemExit("An explicit arXiv version is required.")
    page = urllib.request.urlopen(args.url, timeout=50).read().decode("utf-8")
    parser = Text()
    parser.feed(page)
    text = re.sub(r"[ \t]+", " ", "".join(parser.parts))
    text = re.sub(r"\n{3,}", "\n\n", text)
    print(args.url)
    for term in args.terms:
        matches = list(re.finditer(re.escape(term), text, re.I))
        print(f"\n--- {term}: {len(matches)} hits")
        for match in matches[-3:]:
            print(text[max(0, match.start()-args.context):match.end()+args.context])
