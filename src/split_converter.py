import os
import re
import shutil
import sys
from typing import NoReturn, Optional, Callable, Any

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cn2an
from ebooklib import epub
from PIL import Image, ImageDraw, ImageFont
import unicodedata

from src.main import MultiLevelBook, TextBookParser


class SplitByMaxChaptersConverter:
    """
    按每卷最大章节数分卷的转换器
    """

    def __init__(
        self,
        txt_path: str,
        epub_base_path: str,
        book_title: str,
        author_name: str,
        max_chapters_per_volume: int,
        cover_image: Optional[str] = None,
        output_folder: str = "./html_chapters",
        progress_callback: Optional[Callable[[float], None]] = None,
    ):
        """
        初始化转换器实例。

        :param txt_path: TXT文件或目录的路径。
        :param epub_base_path: 输出的EPUB文件基础路径（不包含卷号）。
        :param book_title: 电子书标题。
        :param author_name: 作者名。
        :param max_chapters_per_volume: 每卷最大章节数。
        :param cover_image: 封面图片文件的路径。
        :param output_folder: 存放HTML章节文件的目录，默认为'./html_chapters'。
        :param progress_callback: 进度回调函数，接受0-100的进度值。
        """
        self.txt_path = txt_path
        self.epub_base_path = epub_base_path
        self.book_title = book_title
        self.author_name = author_name
        self.max_chapters_per_volume = max_chapters_per_volume
        self.cover_image = cover_image
        self.output_folder = output_folder
        self.progress_callback = progress_callback

    def generate_cover(self) -> str:
        """
        生成封面图片。

        :return: 封面图片的路径。
        """
        width, height = 600, 800
        background_color = "white"
        font_color = "black"

        image = Image.new("RGB", (width, height), background_color)
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()

        text_x = width / 2
        text_y = height / 2
        draw.text(
            (text_x, text_y), self.book_title, fill=font_color, font=font, anchor="mm"
        )

        cover_path = os.path.join(self.output_folder, "cover.jpg")
        image.save(cover_path)

        return cover_path

    def create_single_epub(
        self,
        chapters: list[dict[str, Any]],
        volume_number: int,
        output_folder: str,
    ) -> None:
        """
        创建单个EPUB文件。

        :param chapters: 章节列表，每个元素是{"title": str, "content": list[str]}。
        :param volume_number: 卷号（从1开始）。
        :param output_folder: 输出目录。
        """
        # 创建EPUB书籍并设置元数据
        book = epub.EpubBook()
        volume_title = f"{self.book_title}_第{volume_number}卷"
        book.set_title(volume_title)
        book.set_language("zh-cn")
        book.add_author(self.author_name)

        # 添加封面图片
        if self.cover_image and os.path.isfile(self.cover_image):
            cover_path = self.cover_image
        else:
            cover_path = self.generate_cover()

        book.set_cover(os.path.basename(cover_path), open(cover_path, "rb").read())

        # 准备EPUB书籍结构
        spine = []
        toc = []

        # 遍历章节
        for chapter_index, chapter in enumerate(chapters, start=1):
            chap_file_name = f"vol{volume_number:03}_chap{chapter_index:03}.html"
            chap_file_path = os.path.join(output_folder, chap_file_name)

            # 读取章节内容
            with open(chap_file_path, "r", encoding="utf8") as f:
                fcontent = f.read()

            # 创建EpubHtml对象代表章节
            chap_title = chapter["title"]
            chapter_item = epub.EpubHtml(
                title=chap_title,
                file_name=chap_file_name,
                lang="zh-cn",
                content=fcontent,
            )

            book.add_item(chapter_item)
            spine.append(chapter_item)
            toc.append(epub.Link(chap_file_name, chap_title, chap_title))

        # 设置EPUB书籍的导航和样式
        book.spine = ["nav"] + spine
        book.toc = toc

        nav_css = epub.EpubItem(
            uid="style_nav",
            file_name="style/nav.css",
            media_type="text/css",
            content="body { font-family: Times, Times New Roman, serif; }",
        )
        book.add_item(nav_css)
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        # 写入EPUB文件
        epub_path = os.path.join(
            output_folder, f"{self.book_title}_vol{volume_number}.epub"
        )
        print(epub.write_epub(epub_path, book, {"raise_exceptions": 1}))

    def convert(self) -> None:
        """
        执行转换，生成多个EPUB文件。
        """
        os.makedirs(self.output_folder, exist_ok=True)

        # 解析TXT文件并构建书籍结构
        parser = TextBookParser()
        book_structure = parser.read_dir(self.txt_path)

        # 进度更新：解析完成后（10%）
        if self.progress_callback:
            self.progress_callback(10)

        # 保存所有章节为HTML文件
        parser.save_chapters_as_html(book_structure, self.output_folder)

        # 进度更新：HTML保存完成后（40%）
        if self.progress_callback:
            self.progress_callback(40)

        # 遍历所有卷的章节，按max_chapters_per_volume分组
        all_chapters = []
        for volume in book_structure.volumes:
            all_chapters.extend(volume["chapters"])

        total_chapters = len(all_chapters)
        volume_number = 1
        chapters_processed = 0

        # 按每卷最大章节数分组
        for i in range(0, total_chapters, self.max_chapters_per_volume):
            volume_chapters = all_chapters[i : i + self.max_chapters_per_volume]

            # 创建输出目录
            output_dir = os.path.dirname(self.epub_base_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            # 创建单个EPUB文件
            self.create_single_epub(volume_chapters, volume_number, output_dir or ".")

            chapters_processed += len(volume_chapters)

            # 进度更新：动态计算进度
            if self.progress_callback:
                progress = 40 + (chapters_processed / total_chapters * 60)
                self.progress_callback(progress)

            volume_number += 1

        # 进度更新：转换完成（100%）
        if self.progress_callback:
            self.progress_callback(100)

        # 清理临时HTML文件
        self.cleanup()

    def cleanup(self) -> None:
        """
        清理输出目录中的所有文件。
        """
        if os.path.isdir(self.output_folder):
            for filename in os.listdir(self.output_folder):
                file_path = os.path.join(self.output_folder, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    print("Failed to delete %s. Reason: %s" % (file_path, e))

        print("Cleanup completed, temporary files removed.")


class AutoSplitConverter:
    """
    自动检测分卷点的转换器
    """

    def __init__(
        self,
        txt_path: str,
        epub_base_path: str,
        book_title: str,
        author_name: str,
        cover_image: Optional[str] = None,
        output_folder: str = "./html_chapters",
        progress_callback: Optional[Callable[[float], None]] = None,
    ):
        """
        初始化转换器实例。

        :param txt_path: TXT文件或目录的路径。
        :param epub_base_path: 输出的EPUB文件基础路径（不包含卷号）。
        :param book_title: 电子书标题。
        :param author_name: 作者名。
        :param cover_image: 封面图片文件的路径。
        :param output_folder: 存放HTML章节文件的目录，默认为'./html_chapters'。
        :param progress_callback: 进度回调函数，接受0-100的进度值。
        """
        self.txt_path = txt_path
        self.epub_base_path = epub_base_path
        self.book_title = book_title
        self.author_name = author_name
        self.cover_image = cover_image
        self.output_folder = output_folder
        self.progress_callback = progress_callback

    def generate_cover(self) -> str:
        """
        生成封面图片。

        :return: 封面图片的路径。
        """
        width, height = 600, 800
        background_color = "white"
        font_color = "black"

        image = Image.new("RGB", (width, height), background_color)
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()

        text_x = width / 2
        text_y = height / 2
        draw.text(
            (text_x, text_y), self.book_title, fill=font_color, font=font, anchor="mm"
        )

        cover_path = os.path.join(self.output_folder, "cover.jpg")
        image.save(cover_path)

        return cover_path

    def create_single_epub(
        self,
        chapters: list[dict[str, Any]],
        volume_number: int,
        output_folder: str,
    ) -> None:
        """
        创建单个EPUB文件。

        :param chapters: 章节列表，每个元素是{"title": str, "content": list[str]}。
        :param volume_number: 卷号（从1开始）。
        :param output_folder: 输出目录。
        """
        # 创建EPUB书籍并设置元数据
        book = epub.EpubBook()
        volume_title = f"{self.book_title}_第{volume_number}卷"
        book.set_title(volume_title)
        book.set_language("zh-cn")
        book.add_author(self.author_name)

        # 添加封面图片
        if self.cover_image and os.path.isfile(self.cover_image):
            cover_path = self.cover_image
        else:
            cover_path = self.generate_cover()

        book.set_cover(os.path.basename(cover_path), open(cover_path, "rb").read())

        # 准备EPUB书籍结构
        spine = []
        toc = []

        # 遍历章节
        for chapter_index, chapter in enumerate(chapters, start=1):
            chap_file_name = f"vol{volume_number:03}_chap{chapter_index:03}.html"
            chap_file_path = os.path.join(output_folder, chap_file_name)

            # 读取章节内容
            with open(chap_file_path, "r", encoding="utf8") as f:
                fcontent = f.read()

            # 创建EpubHtml对象代表章节
            chap_title = chapter["title"]
            chapter_item = epub.EpubHtml(
                title=chap_title,
                file_name=chap_file_name,
                lang="zh-cn",
                content=fcontent,
            )

            book.add_item(chapter_item)
            spine.append(chapter_item)
            toc.append(epub.Link(chap_file_name, chap_title, chap_title))

        # 设置EPUB书籍的导航和样式
        book.spine = ["nav"] + spine
        book.toc = toc

        nav_css = epub.EpubItem(
            uid="style_nav",
            file_name="style/nav.css",
            media_type="text/css",
            content="body { font-family: Times, Times New Roman, serif; }",
        )
        book.add_item(nav_css)
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        # 写入EPUB文件
        epub_path = os.path.join(
            output_folder, f"{self.book_title}_vol{volume_number}.epub"
        )
        print(epub.write_epub(epub_path, book, {"raise_exceptions": 1}))

    def convert(self) -> None:
        """
        执行转换，生成多个EPUB文件。
        """
        os.makedirs(self.output_folder, exist_ok=True)

        # 解析TXT文件并构建书籍结构
        parser = TextBookParser()
        book_structure = parser.read_dir(self.txt_path)

        # 进度更新：解析完成后（10%）
        if self.progress_callback:
            self.progress_callback(10)

        # 保存所有章节为HTML文件
        parser.save_chapters_as_html(book_structure, self.output_folder)

        # 进度更新：HTML保存完成后（40%）
        if self.progress_callback:
            self.progress_callback(40)

        # 遍历所有卷的章节
        all_chapters = []
        for volume in book_structure.volumes:
            all_chapters.extend(volume["chapters"])

        total_chapters = len(all_chapters)
        volume_number = 1
        chapters_processed = 0

        # 使用自动分卷检测逻辑
        current_volume_chapters = []
        current_chapter = 0

        CHAPTER_ID_PATTERN = r"第(\w+)章?"

        for chapter in all_chapters:
            chapter_title = chapter["title"]

            # 提取章节编号
            try:
                chapter_index = cn2an.cn2an(
                    re.findall(CHAPTER_ID_PATTERN, chapter_title)[0].replace("章", ""),
                    mode="smart",
                )
            except (IndexError, ValueError) as e:
                print(e, chapter_title)
                chapter_index = current_chapter + 1

            # 检测分卷点：章节编号归回到小数字
            if (
                chapter_index < current_chapter
                and chapter_index <= 3
                and current_volume_chapters
            ):
                print(
                    f"卷数改变 {chapter_index} < {current_chapter}，创建第{volume_number}卷"
                )

                # 创建输出目录
                output_dir = os.path.dirname(self.epub_base_path)
                if output_dir:
                    os.makedirs(output_dir, exist_ok=True)

                # 创建当前卷的EPUB文件
                self.create_single_epub(
                    current_volume_chapters, volume_number, output_dir or "."
                )

                chapters_processed += len(current_volume_chapters)

                # 进度更新
                if self.progress_callback:
                    progress = 40 + (chapters_processed / total_chapters * 60)
                    self.progress_callback(progress)

                volume_number += 1
                current_volume_chapters = []
                current_chapter = chapter_index
            else:
                current_chapter = chapter_index

            # 添加章节到当前卷
            current_volume_chapters.append(chapter)

        # 创建最后一卷
        if current_volume_chapters:
            output_dir = os.path.dirname(self.epub_base_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            self.create_single_epub(
                current_volume_chapters, volume_number, output_dir or "."
            )

            chapters_processed += len(current_volume_chapters)

            # 进度更新
            if self.progress_callback:
                progress = 40 + (chapters_processed / total_chapters * 60)
                self.progress_callback(progress)

        # 进度更新：转换完成（100%）
        if self.progress_callback:
            self.progress_callback(100)

        # 清理临时HTML文件
        self.cleanup()

    def cleanup(self) -> None:
        """
        清理输出目录中的所有文件。
        """
        if os.path.isdir(self.output_folder):
            for filename in os.listdir(self.output_folder):
                file_path = os.path.join(self.output_folder, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    print("Failed to delete %s. Reason: %s" % (file_path, e))

        print("Cleanup completed, temporary files removed.")


def run_split_converter(
    method: str,
    txt_path: str,
    book_title: str,
    author_name: str,
    max_chapters_per_volume: Optional[int] = None,
    cover_image: Optional[str] = None,
    output_folder: str = "./html_chapters",
    progress_callback: Optional[Callable[[float], None]] = None,
) -> None:
    """
    便捷的代码入口函数，可以直接在代码中调用进行EPUB分卷

    :param method: 分卷方法，"max-chapters"或"auto"
    :param txt_path: TXT文件路径或目录
    :param book_title: 书名
    :param author_name: 作者名
    :param max_chapters_per_volume: 每卷最大章节数（仅用于max-chapters方法）
    :param cover_image: 封面图片路径（可选）
    :param output_folder: HTML临时文件目录
    :param progress_callback: 进度回调函数
    """
    # 构建EPUB基础路径
    epub_base_path = os.path.join("out", book_title, f"{book_title}.epub")

    if method == "max-chapters":
        if max_chapters_per_volume is None:
            raise ValueError("max_chapters_per_volume is required for max-chapters method")

        converter = SplitByMaxChaptersConverter(
            txt_path=txt_path,
            epub_base_path=epub_base_path,
            book_title=book_title,
            author_name=author_name,
            max_chapters_per_volume=max_chapters_per_volume,
            cover_image=cover_image,
            output_folder=output_folder,
            progress_callback=progress_callback,
        )
        converter.convert()
    elif method == "auto":
        converter = AutoSplitConverter(
            txt_path=txt_path,
            epub_base_path=epub_base_path,
            book_title=book_title,
            author_name=author_name,
            cover_image=cover_image,
            output_folder=output_folder,
            progress_callback=progress_callback,
        )
        converter.convert()
    else:
        raise ValueError(f"Unknown method: {method}. Use 'max-chapters' or 'auto'")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="EPUB分卷转换器 - 支持按章节数分卷和自动分卷"
    )
    parser.add_argument(
        "--method",
        type=str,
        required=True,
        choices=["max-chapters", "auto"],
        help="分卷方法：max-chapters（按章节数分卷）或auto（自动分卷）",
    )
    parser.add_argument(
        "--max-chapters",
        type=int,
        help="每卷最大章节数（仅用于max-chapters方法）",
    )
    parser.add_argument(
        "--txt-path",
        type=str,
        required=True,
        help="TXT文件或目录的路径",
    )
    parser.add_argument(
        "--book-title",
        type=str,
        required=True,
        help="书名",
    )
    parser.add_argument(
        "--author-name",
        type=str,
        required=True,
        help="作者名",
    )
    parser.add_argument(
        "--cover-image",
        type=str,
        help="封面图片路径（可选）",
    )

    args = parser.parse_args()

    # 验证参数
    if args.method == "max-chapters" and args.max_chapters is None:
        parser.error("--max-chapters is required when using max-chapters method")

    # 执行转换
    run_split_converter(
        method=args.method,
        txt_path=args.txt_path,
        book_title=args.book_title,
        author_name=args.author_name,
        max_chapters_per_volume=args.max_chapters,
        cover_image=args.cover_image,
    )