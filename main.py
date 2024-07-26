import requests,textwrap as tr,shutil, os,json
from urllib.request import Request, urlopen,urlretrieve
from urllib.parse import quote
from bs4 import BeautifulSoup
from ebooklib import epub
from progress.bar import Bar
from PIL import Image
from simple_term_menu import TerminalMenu

base_url = "https://novelhi.com/"

searchQuery = input("Search : ")
print()

queryFormat = "%20"
searchQuery = queryFormat.join(searchQuery.split(" "))

headers = lambda url : {'User-Agent': 'Mozilla/5.0',
    '__cf_bm': f'{requests.Session().get(url).cookies.get_dict().get('__cf_bm')}'}

resultCount = 0

class Book:
    def __init__(self,name,author,desc,imgURL,rating,chapter_count,genres,status):
        self.name = name
        self.author = author
        self.desc = desc
        self.imgURL = imgURL
        self.rating = rating,
        self.chapter_count = chapter_count,
        self.genres = genres,
        self.status = status
    def __str__ (self):
        return self.name + " by " + self.author

def getSearchResults(searchQuery):
    global resultCount
    req = requests.get(base_url+rf"book/searchByPageInShelf?curr=1&limit=200&keyword={searchQuery}", headers=headers(base_url))
    responseJson = json.loads(req.content)["data"]
    resultCount = responseJson["total"]
    books = responseJson["list"]
    bookList = []
    for book in books:
        genres = [genre["genreName"] for genre in book["genres"]]
        status = "ongoing" if int(book["bookStatus"]) == 0 else "completed"
        desc = tr.fill(str(book["bookDesc"]).replace("<br>","\n"),shutil.get_terminal_size().columns-1)
        bookList.append(Book(book["bookName"],book["authorName"],desc,book["picUrl"],book["rate"],book["lastIndexName"].split(" ")[1],genres,status))
    return bookList



bookList = getSearchResults(searchQuery)
books = [book.name for book in bookList]
books.append("None")

library_menu_exit = False
libraryMenu = TerminalMenu(books, title=f"Available Books : {resultCount}", search_key=None, clear_screen=True, clear_menu_on_exit=True, search_highlight_style=("bg_purple", "fg_black"))

while not library_menu_exit:
    book_selected = libraryMenu.show()
    if book_selected == len(books) - 1:
        library_menu_exit = True
    else:
        book = bookList[int(str(book_selected))]

        print(('\033[4m' + book.name + '\033[0m').center(shutil.get_terminal_size().columns+14))
        print(("Status : " + book.status).center(shutil.get_terminal_size().columns))
        print(("Author : " + book.author).center(shutil.get_terminal_size().columns))
        print(("Chapters : " + book.chapter_count[0]).center(shutil.get_terminal_size().columns))
        print(("Rating : " + book.rating[0] + " ⭐").center(shutil.get_terminal_size().columns))
        print(("Genres : " + str(book.genres[0]).strip("[").strip("]").replace("'","")).center(shutil.get_terminal_size().columns))
        print("\n")
        print(('\033[4m' + "Novel Description" + '\033[0m').center(shutil.get_terminal_size().columns+14))
        print(book.desc)
        print()
        download_menu = TerminalMenu(["Yes","No"],title="Download Book?")
        option_sel = download_menu.show()
        download_menu_exit = False
        while not download_menu_exit:
            if option_sel ==0:
                chapters = {}
                print()
                start = int(input("Enter starting chapter number : "))
                end = int(input("Enter ending chapter number : "))
                print()
                bar = Bar('Extracting chapter content...', max=end-start+1, fill="◉",width=(end-start+1))
                header = headers(base_url)
                for i in range(start,end+1):
                    book_base_url = base_url + "s/" + quote(book.name).replace("%20","-") + f"/{i}"
                    req = Request(book_base_url,headers=header)
                    webpage = urlopen(req).read()
                    chap_soup = BeautifulSoup(webpage,"html.parser")
                    c = epub.EpubHtml(title=f"Chapter {i}", file_name=f"ch{i}.xhtml")
                    chapter_content = chap_soup.find_all("sent")
                    if len(chapter_content) == 0 :
                        print("No Content Found :(")
                        break
                    chapter_text = []
                    for line in chapter_content:
                        chapter_text.append(str(line).split(">")[1].split("<")[0])
                    chapters[i] = chapter_text
                    bar.next()
                bar.finish()
                if len(chapters) != 0:
                    urlretrieve(f"{book.imgURL}","cover.png")
                    img = Image.open("cover.png")
                    epubBook = epub.EpubBook()
                    epubBook.set_cover('cover.png',open('cover.png', 'rb').read())
                    uuid = epub.uuid.uuid4()
                    epubBook.set_identifier(str(uuid))
                    epubBook.add_author(book.author)
                    count = start
                    epubChaps = []
                    toc = []
                    for chapter in list(chapters.values()):
                        c = epub.EpubHtml(title=f"Chapter {count}", file_name=f"chap_{count}.xhtml",lang="en")
                        contents = [f"<p>{line}</p><br>" for line in chapter]
                        contentString =f"<h2>Chapter {count}</h2><br>"
                        for content in contents:
                            contentString+=content
                        c.content = contentString
                        toc.append(epub.Link(f"chap_{count}.xhtml",f"Chapter {count}","toc"))
                        count+=1
                        epubChaps.append(c)
                        epubBook.add_item(c)

                    style = '''
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
                   nav[epub|type~='toc'] > ol > li > ol  {
                       list-style-type:square;
                   }
                   nav[epub|type~='toc'] > ol > li > ol > li {
                           margin-top: 0.3em;
                   }'''
                    nav_css = epub.EpubItem(uid="style_nav", file_name="style/nav.css", media_type="text/css")
                    nav_css.content = style
                    epubBook.toc = toc
                    epubBook.add_item(nav_css)
                    epubBook.spine = ["cover","nav"] + epubChaps
                    os.remove("cover.png")
                    epubBook.add_item(epub.EpubNcx())
                    epubBook.add_item(epub.EpubNav())
                    epub.write_epub(f"{book.name}.epub", epubBook, {})
                print()
                print("Downloaded! Enjoy your read!")
                os.rename(f"./{book.name}.epub",f"~/Documents/PyNovel/{book.name}.epub")
                download_menu_exit=True
                library_menu_exit = True
            else:
                download_menu_exit=True
