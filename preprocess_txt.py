from unicodedata import normalize
from src.main import TextBookParser
from tqdm import tqdm
import os
import re


def preprocess_txt(file_path: str, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)

    book_content = open(file_path, "r", encoding="utf-8").read()
    book_content = TextBookParser.preprocess_txt(book_content)

    chapters = []
    cur_chapter = ""
    for line in tqdm(book_content.split("\n"), desc="discovering chapters"):
        if line.startswith("第") and line.strip():
            # new chapter
            chapters.append(cur_chapter)
            cur_chapter = line + "\n"

        else:
            cur_chapter += line + "\n"
    chapters.append(cur_chapter)

    print(f"{len(chapters)} chapters found")

    for idx, chapter in tqdm(
        enumerate(chapters), desc="writing chapters", total=len(chapters)
    ):
        title = chapter.split("\n")[0]
        title = normalize("NFKD", title).replace("/", "").strip()

        if idx > 0:
            assert len(
                re.findall("^第([\u4e00-\u9fa5\d]+)(?:章)?\s*(.*)", title)
            ), title

        file_path = f"{idx}-{title}.txt"

        open(f"{output_dir}/{file_path}", "w", encoding="utf-8").write(chapter)


if __name__ == "__main__":
    preprocess_txt("./玄鉴仙族_cleaned.txt", "./test_book/玄鉴仙族")
