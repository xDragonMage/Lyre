from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os
import sys
import time
import csv
import re
from gooey import Gooey, GooeyParser


# Starts browser driver with chosen settings
def browserSetup(directory, headless, timeout, masked) -> object:
    chromeOptions = webdriver.ChromeOptions()
    if not headless:
        chromeOptions.add_argument("--headless=new")
        chromeOptions.add_argument("--disable-gpu")
        chromeOptions.add_argument("--no-sandbox")
        if masked:
            chromeOptions.add_argument(r"user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                r"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    prefs = {"download.default_directory": directory}
    chromeOptions.add_argument("--window-size=1080,1080")
    chromeOptions.add_experimental_option("prefs", prefs)
    driver = webdriver.Chrome(options=chromeOptions)
    driver.set_page_load_timeout(timeout)
    return driver


# Creates browser driver and checks site to dynamically change masking for access
def checkSite(directory, headless, timeout, masked, service) -> object:
    siteAccess = False
    attempts = 0

    while siteAccess is False and attempts < 3:
        driver = browserSetup(directory, headless, timeout, masked)
        driver.get(service)
        if re.search('cloudflare', driver.title, re.IGNORECASE):
            masked = not masked
            attempts += 1
            driver.quit()

        else:
            siteAccess = True

    if siteAccess is False:
        print('!!! Unable to connect to playlist exporter !!!')
    driver.get('https://www.google.com')
    return driver


# Removes any unwanted characters or extra phrases to normalize strings
def cleanString(word) -> str:
    cleaned = re.sub(r'[^A-zÀ-ÿ0-9()\[\].*?/ -]', '', word)
    cleaned = re.sub(r'\.flac', '', cleaned)
    cleaned = re.sub(r'\b(remastered|version|edited|remix|feat)\b.*',
                     '', cleaned, flags=re.IGNORECASE)
    return cleaned


# Goes to website to convert spotify playlist to csv and downloads csv file to download directory
def getPlaylistCSV(driver, timeout, spotifyService, spotify, directory) -> None:
    try:
        driver.get(spotifyService)

        wait = WebDriverWait(driver, timeout)
        searchBox = wait.until(EC.element_to_be_clickable(
            (By.XPATH, '//*[@id="search-word"]')
        ))
        searchBox.send_keys(spotify + Keys.ENTER)
        time.sleep(0.5)

        startButton = driver.find_element(By.ID, 'analyze')
        startButton.click()
        time.sleep(0.5)

        # If adblocker popup appears, to close it
        try:
            closePopup = wait.until(EC.element_to_be_clickable(
                # (By.CLASS_NAME, '_19ax4ey')
                (By.XPATH, '//*[@id="eavgqh"]/div/section[1]/div[2]/p')
            ))
            closePopup.click()
        except TimeoutException:
            None
        time.sleep(0.5)

        downloadCSV = wait.until(EC.element_to_be_clickable(
            (By.XPATH, '//*[@id="export"]')
        ))
        downloadCSV.click()
        time.sleep(0.5)

        while csvDownloaded(directory) == 'None':
            time.sleep(1)
        print('*' * 40 + '\nSuccessfully converted playlist to csv!\n' + '*' * 40)
        sys.stdout.flush()
        driver.quit()
    except TimeoutException:
        print('*' * 40 + '\nUnable to convert playlist to csv!\n' + '*' * 40)
        sys.stdout.flush()
        print('\nMake sure the playlist is public or try another link!')
        sys.stdout.flush()
        driver.quit()
        sys.exit(0)


# Checks if csv file downloaded to download directory, returns file name
def csvDownloaded(directory) -> str:
    with os.scandir(directory) as files:
        for file in files:
            if file.name.endswith('.csv'):
                return file.name
    return 'None'


# Checks if csv for playlist exists in download directory, returns its file path
def playlistExists(directory) -> str:
    try:
        with os.scandir(directory) as files:
            for file in files:
                if file.is_dir():
                    path = os.path.join(directory, file.name)
                    with os.scandir(path) as subFiles:
                        for subFile in subFiles:
                            if subFile.name.endswith('.csv'):
                                return path
        return 'None'
    except FileNotFoundError:
        return 'None'


# Checks if playlist has already been downloaded
def playlistAlrDownloaded(directory) -> bool:
    previousPlaylists = []
    with os.scandir(directory) as files:
        for file in files:
            if file.is_dir():
                previousPlaylists.append(file.name)
            if file.name.endswith('.csv'):
                currentPlaylist = file.name[:-4]
        if currentPlaylist in previousPlaylists:
            return True
    return False


# Extracts song position, title, and artist from spotify csv
def getPlaylist(directory, csvName) -> list:
    filename = os.path.join(directory, csvName)
    rows = []
    songs = []

    with open(filename, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        headers = next(reader)
        for row in reader:
            rows.append(row)

        for row in rows:
            songs.append([row[0], row[1], row[2]])
    return songs


# Checks files in directory to see if the song has already been downloaded
def isDownloaded(directory, title, artist, numbered, rmArtist) -> bool:
    fileWords = artist.split() + title.split()

    if numbered and not rmArtist:
        fileWords = artist.split() + title.split()
    elif rmArtist:
        fileWords = title.split()

    with os.scandir(directory) as files:
        for file in files:
            if file.name.endswith('.flac'):
                if title in file.name:
                    return True

                file = cleanString(file.name).split()
                if '-' in file:
                    file.remove('-')

                titleLen = len(file)
                overlap = set(fileWords) - set(file)
                if len(overlap) < 0:
                    return True

                match = [word for word in file if word in fileWords]
                match = len(match)
                if numbered:
                    match += 1
                # print(fileWords)
                # print(file)
                # print(match, titleLen)

                # Returns true if complete or partial match is found
                if set(title.split()) == set(file) or (match / titleLen) > 0.75:
                    return True
    return False


# Checks every 0.5s if download has completed or timed out and returns status
def downloadWait(directory, oldFiles, timeout) -> str:
    sec = 0
    while sec < timeout:
        time.sleep(0.5)
        newFiles = set(os.listdir(directory))
        newSong = newFiles - oldFiles
        cleanName = cleanString(str(newSong))
        if cleanName != 'set()' and not (cleanName.endswith('.tmp') or cleanName.endswith('.crdownload')):
            status = 'success'
            return status
        sec += 0.5
    status = 'timeout'
    return status


# Renames song file name, either removing artist or numbering it, returns if successful
def renameSong(directory, oldFiles, numbered, rmArtist, index, artist) -> bool:
    newFiles = set(os.listdir(directory))
    songName = ', '.join(map(str, (newFiles - oldFiles)))
    oldPath = f'{directory}\\{songName}'
    unsuppChar = False

    # Checks if artist name starts with inconsistent phrase, removes it
    if songName.lower().startswith('the'):
        songName = songName[4:]

    if rmArtist:
        artists = artist.split(',')
        for artist in artists:
            # If artist name starts with inconsistent phrase, removes it
            if artist.lower().startswith('the'):
                artist = artist[4:]

            # Checks if artist has unsupported characters in name
            if re.match(r'[À-ÿ]*', artist):
                artistLen = len(artist) + 3
                unsuppChar = True

            if artist in songName:
                newName = songName.replace(artist, '')
                newName = newName[3:]
                if numbered:
                    newName = f'{index}. {newName}'
                    if index < 10:
                        newName = f'0{newName}'
                newPath = f'{directory}\\{newName}'
                os.rename(oldPath, newPath)
                return True
            elif unsuppChar:
                newName = songName[artistLen:]
                if numbered:
                    newName = f'{index}. {newName}'
                    if index < 10:
                        newName = f'0{newName}'
                newPath = f'{directory}\\{newName}'
                os.rename(oldPath, newPath)
                return True

    if numbered:
        newName = f'{index}. {songName}'
        if index < 10:
            newName = f'0{newName}'
        newPath = f'{directory}\\{newName}'
        os.rename(oldPath, newPath)
        return True
    return False


# Goes to service and downloads song
def download(driver, downloadService, timeout, title, artist) -> bool:
    title = cleanString(title)
    artist = cleanString(artist)
    searchSong = f'{title} {artist}'

    try:
        driver.get(downloadService)
        wait = WebDriverWait(driver, timeout)
        match = False

        searchBox = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "input[placeholder*='Search']")
        ))
        searchBox.clear()
        searchBox.send_keys(searchSong[:60] + Keys.ENTER)
        time.sleep(1)

        # Checks first 5 results for title matches
        songPlace = 1
        while songPlace < 6:
            songTitle = wait.until(EC.presence_of_element_located(
                (By.XPATH, f"(//div[@class='min-w-0 flex-1']//child::h3)[{songPlace}]")
            ))
            if cleanString(songTitle.text) == title:
                match = True
                break
            songPlace += 1
        if not match:
            # If no title matches, checks for artist matches instead
            songPlace = 1
            oddLoop = 1
            while songPlace < 10:
                songArtist = wait.until(EC.presence_of_element_located(
                    (By.XPATH, f"(//div[@class='min-w-0 flex-1']//child::a)[{songPlace}]")
                ))
                if cleanString(songArtist.text) == artist:
                    songPlace = oddLoop
                    match = True
                    break
                songPlace += 2
                oddLoop += 1
        time.sleep(1)
        if match:
            downloadButton = wait.until(EC.element_to_be_clickable(
                (By.XPATH, f"(//button[.//*[contains(@class, 'lucide-download')]])[{songPlace}]")
            ))
            downloadButton.click()
            return match
        else:
            downloadButton = wait.until(EC.element_to_be_clickable(
                (By.XPATH, f"(//button[.//*[contains(@class, 'lucide-download')]])")
            ))
            downloadButton.click()
            return not match
    except Exception:
        return False


# Creates playlist folder based on playlist name, moves csv into this folder, returns playlist path
def createPlaylistFolder(directory, playlist) -> str:
    newFolder = f'{directory}\\{playlist[:-4]}'
    os.makedirs(newFolder, exist_ok=True)

    with os.scandir(directory) as files:
        for file in files:
            if file.name.endswith('.csv'):
                csvPath = f'{directory}\\{file.name}'
                playlistPath = f'{newFolder}\\{file.name}'
                os.rename(csvPath, playlistPath)
                return newFolder


@Gooey(
    program_name='Lyre v0.55', image_dir=f'{os.getcwd()}', tabbed_groups=True,
    show_stop_warning=False, footer_bg_color=('#2e070f'), menu=[{'name': 'Info', 'items':
    [{'type': 'AboutDialog', 'menuTitle': 'About', 'name': 'Lyre', 'description':
      '  Lyre is a tool to break free from streaming services and provide real  \n'
      '  ownership over the songs you want.  ',
      'version': '0.55', 'copyright': '2026', 'license':
      'Lyre © 2026 by Sigillum Deim is licensed under CC BY-NC-SA 4.0.\nTo view a copy of this license, '
      'visit \nhttps://creativecommons.org/licenses/by-nc-sa/4.0/'},
     {'type': 'MessageDialog', 'menuTitle': 'Support', 'caption': 'Support Email',
      'message': 'Currently abandoned due to depreciation of reliant services.\n'
                 'Email any questions or concerns to the email below.\n\n'
                 '               *****sigillumdeim@gmail.com*****'}
     ]}]
)
def main():
    parser = GooeyParser(description='Enter a Spotify playlist to download songs!')
    mainTab = parser.add_argument_group('Main Options', gooey_options={
        'show_border': True, 'columns': 1
    })
    settingsTab = parser.add_argument_group('Settings', 'Adjust settings for Lyre',
        gooey_options={
            'show_border': True
    })
    advSettingsTab = parser.add_argument_group('Advanced Settings', 'Changing these may cause errors!',
        gooey_options={
            'show_border': True
    })
    mainTab.add_argument('spotify', metavar='Spotify Playlist', widget='Textarea',
        help='Enter the Spotify playlist list', gooey_options={
            'initial_value': 'https://spotify.com/playlist/', 'height': 21
    })
    mainTab.add_argument('--continueDownload', metavar='Continue Download', widget='CheckBox',
        help='Check to continue downloading an already started playlist '
            '(Can leave playlist as default if checked)',
        action='store_true', default=False
    )
    mainTab.add_argument('downloadDirectory', metavar='Download Directory',
        help='Choose where to download playlist (Or leave default)', widget='DirChooser',
        default=f'{os.getcwd()}\\Music Downloads'
    )
    settingsTab.add_argument('--timeout', metavar='Timeout',
        help='The time to wait for websites to load', widget='IntegerField', default=20,
        gooey_options={
            'min': 5, 'max': 60
    })
    settingsTab.add_argument('--downloadTimeout', metavar='Download Timeout',
        help='The time to wait for songs to download', widget='IntegerField', default=120,
        gooey_options={
            'min': 10, 'max': 300
    })
    settingsTab.add_argument('--rmArtist', metavar='Artist Name',
        help='Remove the artist name from song file name', action='store_true', default=False
    )
    settingsTab.add_argument('--numbered', metavar='Number Songs',
        help='Number the song files downloaded', action='store_true', default=False
    )
    advSettingsTab.add_argument('downloadService', metavar='Download Service',
        help='The website where songs are downloaded from', widget='TextField',
        default='https://tidal.qqdl.site/'
    )
    advSettingsTab.add_argument('spotifycsvService', metavar='Spotify Service',
        help='The website where playlists are converted to CSV', widget='TextField',
        default='https://chosic.com/spotify-playlist-exporter/'
    )
    advSettingsTab.add_argument('--headless', metavar='Headless Mode',
        help='Operate in headless mode', action='store_false', default=True
    )
    args = parser.parse_args()

    # Convert args into variables, casts to appropriate types, and initializes variables
    downloadDirectory = args.downloadDirectory
    downloadTimeout = int(args.downloadTimeout)
    timeout = int(args.timeout)
    downloadService = args.downloadService
    spotifycsvService = args.spotifycsvService
    spotify = args.spotify
    headless = args.headless
    continueDownload = args.continueDownload
    newSongs = not continueDownload
    masked = False
    rmArtist = args.rmArtist
    numbered = args.numbered
    successfulDownloads = 0

    os.makedirs(downloadDirectory, exist_ok=True)
    try:
        print('Lyre starting up...\n')
        # If continue download selected, checks playlist CSV exists or exits program
        if continueDownload:
            playlistPath = playlistExists(downloadDirectory)
            if playlistPath != 'None':
                print('Playlist csv found! Continuing download...')
                sys.stdout.flush()
                csvName = csvDownloaded(playlistPath)
            else:
                print('No playlist found to continue!\n'
                      'Rerun Lyre with \"Continue Download\" unchecked and provide a Spotify link!')
                sys.stdout.flush()
                sys.exit(0)
        # Starts driver, checks for access, and converts spotify link to csv
        else:
            driver = checkSite(downloadDirectory, headless, timeout, masked, spotifycsvService)
            print('Converting Spotify playlist to csv...')
            sys.stdout.flush()
            getPlaylistCSV(driver, timeout, spotifycsvService, spotify, downloadDirectory)
            csvName = csvDownloaded(downloadDirectory)

            # Checks if playlist has already been downloaded/ started download
            if playlistAlrDownloaded(downloadDirectory):
                print(f'Playlist {csvName[:-4]} has already been downloaded!\n'
                      f'If it was incomplete and you wish to continue downloading, '
                      f'check the \"Continue Download\" option and try again!')
                sys.stdout.flush()
                os.remove(os.path.join(downloadDirectory, csvName))
                sys.exit(0)
            else:
                # Creates playlist folder if new playlist and returns its path
                playlistPath = createPlaylistFolder(downloadDirectory, csvName)

        songs = getPlaylist(playlistPath, csvName)
        totalSongs = len(songs)

        # Starts driver again for download service and checks for access
        driver = checkSite(playlistPath, headless, timeout, masked, downloadService)
        if continueDownload:
            print('Checking if any songs are already downloaded...\n')
        else:
            print('Starting downloads...\n')
        sys.stdout.flush()

        # Loops through all songs in playlist csv and extracts title and artist
        for index, title, artist in songs:
            index = int(index)
            # Checks if song is already downloaded, skips checking if not continuing a previous playlist
            if not newSongs and isDownloaded(playlistPath, title, artist, numbered, rmArtist):
                print(f'○○○{index}/{totalSongs} | {title} already downloaded...')
                sys.stdout.flush()
                successfulDownloads += 1
                continue

            newSongs = True
            # Calls to download song and receives True if song download started
            status = download(driver, downloadService, timeout, title, artist)
            if status:
                print(f'***{index}/{totalSongs} | {title} | downloading...')
                sys.stdout.flush()

                # Get a set of the songs that have already been downloaded
                currentSongs = set(os.listdir(playlistPath))

                # Waits until new song has been downloaded
                downloadStatus = downloadWait(playlistPath, currentSongs, downloadTimeout)
                if downloadStatus == 'success':
                    print(f'+++{index}/{totalSongs} | {title} | downloaded!')
                    sys.stdout.flush()

                    # Adjusts file name after download
                    if numbered or rmArtist:
                        renamed = renameSong(playlistPath, currentSongs, numbered, rmArtist, index, artist)
                        if renamed:
                            print(f'+++{index}/{totalSongs} | {title} | File successfully renamed!')
                            sys.stdout.flush()
                        else:
                            print(f'---{index}/{totalSongs} | {title} | Failed to rename file!')
                            sys.stdout.flush()

                    successfulDownloads += 1
                elif downloadStatus == 'error':
                    print(f'---{index}/{totalSongs} | {title} | failed to download...')
                    sys.stdout.flush()
                elif downloadStatus == 'timeout':
                    print(f'!!!{index}/{totalSongs} | {title} | download timed out!')
                    sys.stdout.flush()
            else:
                print(f'---{index}/{totalSongs} | {title} | not found, downloaded first result...')
                sys.stdout.flush()

        # Deletes playlist csv after downloading all songs
        os.remove(os.path.join(playlistPath, csvName))

        # Ending message
        successPercentage = successfulDownloads / totalSongs
        print(f'*' * 40 + '\n'
              f'Successfully downloaded {successfulDownloads} songs out of {totalSongs}.\n'
              f'Moved all {successfulDownloads} songs into playlist folder at {playlistPath}.\n'
              f'Lyre ran with {round(successPercentage * 100, 2)}% efficiency!\n' +
              f'*' * 12 + ' Feliz Navidad! ' + '*' * 12 + '\n' +
              f'*' * 40)
        sys.stdout.flush()

        time.sleep(0.5)
        driver.quit()
    except Exception:
        print('Total Failure')
        sys.exit(1)


if __name__ == '__main__':
    main()
