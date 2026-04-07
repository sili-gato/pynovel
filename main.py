import argparse
import html
import json
import os
import re
import shutil
import tempfile
import textwrap as tr
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from ebooklib import epub
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.text import Text
from simple_term_menu import TerminalMenu

BASE_URL = "https://novelhi.com/"
DEFAULT_CONFIG_PATH = os.path.expanduser("~/.pynovel.json")
DEFAULT_THREADS = 4
REQUEST_TIMEOUT = 30

console = Console()


@dataclass
class Book:
    name: str
    author: str
    desc: str
    img_url: str
    rating: str
    chapter_count: str
    genres: list[str] = field(default_factory=list)
    status: str = "ongoing"

    def __str__(self):
        return f"{self.name} by {self.author}"


def load_config(config_path=DEFAULT_CONFIG_PATH):
    """Load config from ~/.pynovel.json if it exists."""
    defaults = {
        "download_dir": os.getcwd(),
        "threads": DEFAULT_THREADS,
    }
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                user_config = json.load(f)
            defaults.update(user_config)
        except (json.JSONDecodeError, OSError) as e:
            console.print(f"[yellow]Warning: Could not read config: {e}[/yellow]")
    return defaults


def create_session():
    """Create a requests session with cookies cached from the base URL."""
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    try:
        session.get(BASE_URL, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.RequestException as e:
        console.print(f"[red]Warning: Could not initialize session cookies: {e}[/red]")
    return session


def search_books(session, query):
    """Search for books and return (book_list, result_count)."""
    url = f"{BASE_URL}book/searchByPageInShelf?curr=1&limit=200&keyword={quote(query)}"

    try:
        resp = session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()["data"]
    except requests.exceptions.RequestException as e:
        console.print(f"[red]Network error during search: {e}[/red]")
        return [], 0
    except (json.JSONDecodeError, KeyError) as e:
        console.print(f"[red]Unexpected API response: {e}[/red]")
        return [], 0

    result_count = data.get("total", 0)
    books = []

    for entry in data.get("list", []):
        genres = [g["genreName"] for g in entry.get("genres", [])]
        status = "ongoing" if int(entry.get("bookStatus", 0)) == 0 else "completed"
        desc = tr.fill(
            str(entry.get("bookDesc", "")).replace("<br>", "\n"),
            shutil.get_terminal_size().columns - 1,
        )

        # Extract chapter count number from "Chapter 450" style strings
        last_index = entry.get("lastIndexName", "0")
        chapter_count_match = re.search(r"\d+", last_index)
        chapter_count = chapter_count_match.group() if chapter_count_match else "0"

        books.append(
            Book(
                name=entry["bookName"],
                author=entry["authorName"],
                desc=desc,
                img_url=entry.get("picUrl", ""),
                rating=str(entry.get("rate", "N/A")),
                chapter_count=chapter_count,
                genres=genres,
                status=status,
            )
        )

    return books, result_count


def fetch_chapter(session, book_name, chapter_num):
    """Fetch a single chapter's text. Returns (chapter_num, lines) or (chapter_num, None)."""
    book_slug = quote(book_name).replace("%20", "-")
    url = f"{BASE_URL}s/{book_slug}/{chapter_num}"

    try:
        resp = session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.exceptions.RequestException:
        return chapter_num, None

    soup = BeautifulSoup(resp.content, "html.parser")
    sent_tags = soup.find_all("sent")

    if not sent_tags:
        return chapter_num, None

    lines = [tag.get_text() for tag in sent_tags]
    return chapter_num, lines


def build_epub(book, chapters, download_dir, session):
    """Build an EPUB file from downloaded chapters. Returns the output path or None."""
    tmp_cover = None
    try:
        # Download cover image to temp file
        tmp_fd, tmp_cover = tempfile.mkstemp(suffix=".png")
        os.close(tmp_fd)

        if book.img_url:
            try:
                cover_resp = session.get(book.img_url, timeout=REQUEST_TIMEOUT)
                cover_resp.raise_for_status()
                with open(tmp_cover, "wb") as f:
                    f.write(cover_resp.content)
            except requests.exceptions.RequestException:
                console.print("[yellow]Warning: Could not download cover image[/yellow]")
                tmp_cover_data = None
            else:
                with open(tmp_cover, "rb") as f:
                    tmp_cover_data = f.read()
        else:
            tmp_cover_data = None

        epub_book = epub.EpubBook()

        if tmp_cover_data:
            epub_book.set_cover("cover.png", tmp_cover_data)

        epub_book.set_identifier(str(epub.uuid.uuid4()))
        epub_book.set_title(book.name)
        epub_book.add_author(book.author)

        epub_chapters = []
        toc = []

        for chapter_num in sorted(chapters.keys()):
            chapter_lines = chapters[chapter_num]
            c = epub.EpubHtml(
                title=f"Chapter {chapter_num}",
                file_name=f"chap_{chapter_num}.xhtml",
                lang="en",
            )
            paragraphs = "".join(f"<p>{html.escape(line)}</p>" for line in chapter_lines)
            c.content = f"<h2>Chapter {chapter_num}</h2>{paragraphs}"
            toc.append(epub.Link(f"chap_{chapter_num}.xhtml", f"Chapter {chapter_num}", "toc"))
            epub_chapters.append(c)
            epub_book.add_item(c)

        style = """
h2 {
    text-align: left;
    text-transform: uppercase;
    font-weight: 200;
}
ol {
    list-style-type: none;
}
ol > li:first-child {
    margin-top: 0.3em;
}
nav[epub|type~='toc'] > ol > li > ol {
    list-style-type: square;
}
nav[epub|type~='toc'] > ol > li > ol > li {
    margin-top: 0.3em;
}"""

        nav_css = epub.EpubItem(
            uid="style_nav",
            file_name="style/nav.css",
            media_type="text/css",
        )
        nav_css.content = style

        epub_book.toc = toc
        epub_book.add_item(nav_css)
        epub_book.add_item(epub.EpubNcx())
        epub_book.add_item(epub.EpubNav())

        spine = ["cover", "nav"] + epub_chapters if tmp_cover_data else ["nav"] + epub_chapters
        epub_book.spine = spine

        safe_name = re.sub(r'[^\w\s\-.]', '_', book.name).strip()
        output_path = os.path.join(download_dir, f"{safe_name}.epub")
        resolved = os.path.realpath(output_path)
        if not resolved.startswith(os.path.realpath(download_dir)):
            console.print("[red]Invalid book name: path traversal detected[/red]")
            return None
        epub.write_epub(output_path, epub_book, {})
        return output_path

    except Exception as e:
        console.print(f"[red]Failed to build EPUB: {e}[/red]")
        return None
    finally:
        if tmp_cover and os.path.exists(tmp_cover):
            os.remove(tmp_cover)


def download_book(session, book, start, end, download_dir, threads=DEFAULT_THREADS):  # noqa: PLR0913
    """Download chapters and create an EPUB. Returns True on success."""
    total = end - start + 1
    chapters = {}
    failed = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed}/{task.total})"),
        console=console,
    ) as progress:
        task = progress.add_task("Downloading chapters...", total=total)

        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {}
            for i in range(start, end + 1):
                future = executor.submit(fetch_chapter, session, book.name, i)
                futures[future] = i
                time.sleep(0.05)  # Small stagger to avoid rate limiting

            for future in as_completed(futures):
                chapter_num, lines = future.result()
                if lines:
                    chapters[chapter_num] = lines
                else:
                    failed.append(chapter_num)
                progress.advance(task)

    if failed:
        failed.sort()
        console.print(f"[yellow]Warning: Failed to download chapters: {failed}[/yellow]")

    if not chapters:
        console.print("\n[red]No chapters could be downloaded :([/red]")
        return False

    console.print("[dim]Building EPUB...[/dim]")
    output_path = build_epub(book, chapters, download_dir, session)

    if output_path:
        console.print(f"\n[green]Successfully saved to:[/green] {output_path}")
        return True

    return False


def display_book_details(book):
    """Display book details using rich formatting."""
    genre_str = ", ".join(book.genres) if book.genres else "N/A"

    info = Text()
    info.append(f"Status: {book.status}\n")
    info.append(f"Author: {book.author}\n")
    info.append(f"Chapters: {book.chapter_count}\n")
    info.append(f"Rating: {book.rating} \u2b50\n")
    info.append(f"Genres: {genre_str}")

    console.print(Panel(info, title=f"[bold]{book.name}[/bold]", expand=False))
    console.print()
    console.print(Panel(book.desc, title="[underline]Description[/underline]", expand=True))
    console.print()


def get_chapter_range(book):
    """Prompt for chapter range with validation. Returns (start, end) or None."""
    max_chapter = None
    try:
        max_chapter = int(book.chapter_count)
    except (ValueError, TypeError):
        pass

    while True:
        console.print()
        raw_start = input("Enter starting chapter number (or 'all' / empty to cancel): ").strip()

        if not raw_start:
            return None

        if raw_start.lower() == "all":
            if max_chapter and max_chapter > 0:
                return 1, max_chapter
            console.print("[yellow]Cannot determine total chapters. Please enter a range.[/yellow]")
            continue

        try:
            start = int(raw_start)
        except ValueError:
            console.print("[red]Please enter a valid number.[/red]")
            continue

        if start < 1:
            console.print("[red]Starting chapter must be at least 1.[/red]")
            continue

        try:
            end = int(input("Enter ending chapter number: ").strip())
        except ValueError:
            console.print("[red]Please enter a valid number.[/red]")
            continue

        if end < start:
            console.print("[red]Ending chapter must be >= starting chapter.[/red]")
            continue

        if max_chapter and end > max_chapter:
            console.print(f"[yellow]Warning: Book may only have {max_chapter} chapters.[/yellow]")

        return start, end


def interactive_mode(session, download_dir, threads):
    """Run the interactive TUI loop."""
    while True:
        query = input("Search: ").strip()
        if not query:
            continue

        console.print()
        book_list, result_count = search_books(session, query)

        if not book_list:
            console.print("[yellow]No results found.[/yellow]")
        else:
            book_names = [b.name for b in book_list]
            book_names.append("Back to Search")

            menu = TerminalMenu(
                book_names,
                title=f"Available Books: {result_count}",
                search_key=None,
                clear_screen=True,
                clear_menu_on_exit=True,
                search_highlight_style=("bg_purple", "fg_black"),
            )

            while True:
                selected = menu.show()

                if selected is None or selected == len(book_names) - 1:
                    break

                book = book_list[selected]
                display_book_details(book)

                download_menu = TerminalMenu(["Yes", "No"], title="Download Book?")
                if download_menu.show() == 0:
                    chapter_range = get_chapter_range(book)
                    if chapter_range:
                        start, end = chapter_range
                        console.print()
                        download_book(session, book, start, end, download_dir, threads)
                    break

        # Search again prompt
        console.print()
        again = TerminalMenu(["Search Again", "Quit"], title="What next?")
        if again.show() != 0:
            break


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="PyNovel - Download web novels as EPUB files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-s", "--search",
        help="Search query (skips interactive prompt if combined with --start/--end)",
    )
    parser.add_argument(
        "-o", "--output-dir",
        help="Download directory (default: config value or current directory)",
    )
    parser.add_argument(
        "--start", type=int,
        help="Starting chapter number (for non-interactive mode)",
    )
    parser.add_argument(
        "--end", type=int,
        help="Ending chapter number (for non-interactive mode)",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Download all chapters",
    )
    parser.add_argument(
        "--threads", type=int,
        help=f"Number of download threads (default: {DEFAULT_THREADS})",
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help=f"Config file path (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--index", type=int, default=0,
        help="Book index in search results for non-interactive mode (default: 0, first result)",
    )

    # Backward compat: if a single positional arg is given, treat it as output dir
    parser.add_argument("legacy_dir", nargs="?", help=argparse.SUPPRESS)

    return parser.parse_args()


def main():
    args = parse_args()
    config = load_config(args.config)

    # Resolve download directory: CLI flag > legacy positional > config > cwd
    download_dir = (
        args.output_dir
        or args.legacy_dir
        or config.get("download_dir", os.getcwd())
    )
    download_dir = os.path.expanduser(download_dir)

    if not os.path.isdir(download_dir):
        console.print(f"[red]Download directory does not exist: {download_dir}[/red]")
        return

    threads = args.threads or config.get("threads", DEFAULT_THREADS)

    session = create_session()

    # Non-interactive mode: --search with --start/--end or --all
    if args.search and (args.all or (args.start is not None and args.end is not None)):
        book_list, count = search_books(session, args.search)
        if not book_list:
            console.print("[red]No results found.[/red]")
            return

        if args.index >= len(book_list):
            console.print(f"[red]Index {args.index} out of range (found {len(book_list)} books).[/red]")
            return

        book = book_list[args.index]
        console.print(f"[bold]Selected:[/bold] {book}")

        if args.all:
            try:
                end = int(book.chapter_count)
            except (ValueError, TypeError):
                console.print("[red]Cannot determine chapter count. Use --start and --end instead.[/red]")
                return
            start = 1
        else:
            start, end = args.start, args.end

        if start < 1 or end < start:
            console.print("[red]Invalid chapter range.[/red]")
            return

        download_book(session, book, start, end, download_dir, threads)
        return

    # Interactive mode
    interactive_mode(session, download_dir, threads)


if __name__ == "__main__":
    main()
