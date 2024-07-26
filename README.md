# PyNovel
A basic website scraper and downloader to download your favorite webnovels.

## Usage
1. Clone the GitHub Repo 
```sh
git clone "https://github.com/sili-gato/pynovel.git"
```
2. Add PyNovel to PATH by adding the following line in your .zshrc (or other relevant shell config files)
```sh
export PATH="path/to/cloned/repo:$PATH"

### For Example, if you cloned to "~/Documents", the command would be
export PATH="Users/yourName/Documents:$PATH" # For macOS
```
3. (OPTIONAL) Setup an alias for pynovel by adding the following line to your .zshrc (or other relevant shell config files)
```sh
alias pynovel="pynovel.sh" 
```
#### Assuming you have aliased pynovel.sh as pynovel
4. Create your config file by running "pynovel -e"
```sh
pynovel -e
```
5. Default PyNovel Configuration
```sh
pynovel_editor=nano #SETS THE TEXT EDITOR FOR WHEN YOU RUN "pynovel -e"
download_dir="$PWD" #SETS THE DIRECTORY FOR THE NOVELS DOWNLOADED
```
6. My config
```
pynovel_editor=nvim
download_dir="$HOME/Documents/Novels" ### "$HOME" is your root directory path. For example its the "~" on macOS.
```

### Work In Progress
1. Working on adding novel cover preview support when selecting which novel to download.



Ps: It's my first attempt at making a script like this so the code is pretty messy :O
