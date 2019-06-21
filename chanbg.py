#!/usr/bin/env python3
import logging
import requests
import random
import time
import os
import subprocess

# This command will be called to change the background
# subprocess will call `BG_CHANGE_CMD BG_CHANGE_OPT_<SCALE/CENTER/ETC> 
#                       <filename> BG_CHANGE_OPT_SUFFIX_<SCALE/CENTER/ETC>`
BG_CHANGE_CMD = "feh"
BG_CHANGE_OPT_SUFFIX = ""
BG_CHANGE_OPT_MAX = "--bg-max"
BG_CHANGE_OPT_FILL = "--bg-fill"
BG_CHANGE_OPT_TILE = "--bg-tile"
BG_CHANGE_OPT_SCALE = "--bg-scale"
BG_CHANGE_OPT_CENTER = "--bg-center"

# Miscellaneous options
ALLOW_STICKIES = False # Set to True to allow images from stickies
DISALLOWED_EXTENSIONS = ['.webm']
SLEEP_FAILURE = 1 # Seconds to sleep between failed attempts to find bg

# Some default values
DEF_BOARDS = ['w', 'wg']
DEF_TIMEOUT = 120
DEF_IMAGE_FOLDER = "img"
DEF_MIN_DIMENSION = (1152, 648)
DEF_MAX_DIMENSION = (DEF_MIN_DIMENSION[0] * 6, DEF_MIN_DIMENSION[1] * 6)

# JSON API and CDN constants
PROTOCOL = "http"
API_DOMAIN = "%s://a.4cdn.org" % (PROTOCOL)
THREAD_JSON_FMT = "%s/{board}/thread/{threadnumber}.json" % (API_DOMAIN)
BOARD_JSON_FMT = "%s/{board}/threads.json" % (API_DOMAIN)
IMAGE_DOMAIN = "%s://i.4cdn.org" % (PROTOCOL)
IMAGE_FMT = "%s/{board}/{filename}{extension}" % (IMAGE_DOMAIN)

#LOG_LEVEL = logging.DEBUG
LOG_LEVEL = logging.INFO
logging.basicConfig(format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y/%m/%d %H:%M:%S', level=LOG_LEVEL)

def _get_json(url):
    """
    Wrapper for requesting data from json API
    """
    try:
        logging.debug("Retrieving: %s" % url)
        return requests.get(url=url).json()
    except Exception as e:
        logging.warning("Error retrieving url %s" % (url))
        logging.warning("Error: %s" % (str(e)))

def _get_random_post(options):
    """
    Selects a random board, then selects a random thread on that board, then 
    returns a post from that thread that has a suitable image or returns 
    None if no suitable posts are found or False if there is an error.
    """
    min_dimension = options['min_dimension']
    max_dimension = options['max_dimension']
    if any(min_dimension[i] > max_dimension[i] for i in range(2)):
        logging.error("Error: Max dimensions are smaller than min dimensions, "
                "no images will be able to be found.")
        return False
    b = random.choice(options['boards'])
    t = _get_random_thread(b)
    if not t:
        return False
    logging.debug("Looking for images in /%s/ thread #%s" % (b, t))
    url = THREAD_JSON_FMT.format(board=b, threadnumber=t)
    json = _get_json(url)
    if not json:
        logging.error('Failed to get thread number %s on board /%s/' % (t, b))
        return False
    all_image_posts = [x for x in json['posts']
            if 'filename' in x and
                ('sticky' not in x or ALLOW_STICKIES) and
                x['w'] >= min_dimension[0] and
                x['w'] <= max_dimension[0] and
                x['h'] >= min_dimension[1] and
                x['h'] <= max_dimension[1] and
                x['ext'] not in DISALLOWED_EXTENSIONS]
    if not all_image_posts:
        logging.info("Could not find any suitable images in thread #%s on "
                "/%s/" % (t, b))
        logging.info("Sleeping %ss to limit API requests" % (SLEEP_FAILURE))
        time.sleep(SLEEP_FAILURE)
        return None
    logging.debug("Found %d posts with suitable images in thread #%s "
            "on /%s/" % (len(all_image_posts), t, b))
    p = random.choice(all_image_posts)
    return {'board': b, 'thread': t, 'post': p}

def _try_create_image_folder(folder):
    """
    Checks if image folder exists, attempts to create it if it does not exist.
    """
    try:
        if not os.path.exists(folder):
            os.makedirs(folder)
    except Exception as e:
        logging.warning("Error: Caught error checking if folder exists")
        logging.warning("Error: %s" % (str(e)))

def _save_image(url, path):
    """
    Downloads image at `url` to `path`
    """
    try:
        r = requests.get(url, stream=True)
        with open(path, 'wb') as f:
            for chunk in r.iter_content(1024):
                f.write(chunk)
    except Exception as e:
        logging.warning("Error: Failed to download url %s" % url)
        logging.warning("Error: %s" % (str(e)))
        return False
    # Adds a zero-width space to allow for linking
    logging.info("Downloaded %s (%s\u200b)" % (path, url))
    return path

def _md5_to_filename(md5):
    """
    Converts base64 encoded md5 to filename safe base64 encoding. Uneeded
    padding is removed and '+' and '/'  are replaced with safe alternatives.
    """
    return md5[:22].replace('+', '-').replace('/', '_')

def _get_random_image(options):
    """
    Loops until an error occurs or until a post with an image is found. When
    an image is found it is downloaded, the path of the downloaded image is
    returned. Files are saved with md5 for filename to avoid duplicates.
    """
    post_info = None
    path = ""
    logging.info("Starting search for random image")
    while post_info == None:
        post_info = _get_random_post(options)
        if not post_info:
            continue
        post = post_info['post']
        path = "{folder}/{filename}{extension}".format(
                folder=options['image_folder'],
                filename=_md5_to_filename(post['md5']),
                extension=post['ext'])
    if not post_info:
        return False # False probably means invalid data from user
    logging.info("Found %s%s (%sx%s) in /%s/ post #%s" % (
                    post['tim'], post['ext'], post['w'], post['h'], 
                    post_info['board'], post['no'],)
            )
    if _check_file_exists(path):
        logging.info("Image already downloaded %s" % (path))
        return path
    _try_create_image_folder(options['image_folder'])
    url = IMAGE_FMT.format(board=post_info['board'],
            filename=post['tim'], extension=post['ext'])
    return _save_image(url, path)

def _get_random_thread(b):
    """
    Returns a random thread from the board `b`
    """
    url = BOARD_JSON_FMT.format(board=b)
    json = _get_json(url)
    if not json:
        logging.error('Failed to get threads for board /%s/' % b)
        return False
    all_threads = [x["no"] for y in json for x in y['threads']]
    logging.debug("Found %d threads on board /%s/" % (len(all_threads), 
            b))
    return random.choice(all_threads)

def _check_file_exists(path):
    """
    Checks if path points to a file that exists.
    """
    return os.path.isfile(path)

def set_background(path, options):
    """
    Calls external command (feh) to set background image.
    """
    logging.info("Setting background to %s" % (path))
    args = " ".join([BG_CHANGE_CMD, options['cmd_scale_option'], path,
            options['cmd_suffix']])
    (status, output) = subprocess.getstatusoutput(args)
    if status != 0:
        logging.warning("Command subprocess returned non-zero value.")
        logging.warning("Command: %s" % (args))
        logging.warning("Output: %s" % (output))
    return status

def create_options(options={}):
    """
    Modified the passed list to make sure defaults are set.
    """
    if 'boards' not in options or not options['boards']:
        options['boards'] = DEF_BOARDS
    if 'image_folder' not in options or not options['image_folder']:
        options['image_folder'] = DEF_IMAGE_FOLDER
    if 'min_dimension' not in options or not options['min_dimension']:
        options['min_dimension'] = DEF_MIN_DIMENSION
    if 'max_dimension' not in options or not options['max_dimension']:
        options['max_dimension'] = DEF_MAX_DIMENSION
    if 'cmd_scale_option' not in options or not options['cmd_scale_option']:
        options['cmd_scale_option'] = BG_CHANGE_OPT_FILL
    if 'cmd_suffix' not in options or not options['cmd_suffix']:
        options['cmd_suffix'] = BG_CHANGE_OPT_SUFFIX
    return options

def update_background(options):
    """
    High level function that will attempt to download an image, then set it as
    the background image.
    """
    path = _get_random_image(options)
    if not path:
        return False
    file_exists = _check_file_exists(path)
    if not file_exists:
        logging.warning("Error: File doesn't exist (path='%s', "
                "file_exists=%s)" % (path, file_exists))
        return False
    set_background(path, options) # FIle exists and is ready to be used

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Periodically downloads new '
            'wallpapers from 4chan and updates your background using feh.')
    parser.add_argument('-t', '--timeout', type=int,
            help='Time in seconds to sleep. (Default: -t %s)' % (DEF_TIMEOUT))
    parser.add_argument('-b', '--boards', nargs='+', type=str,
            help='Space separated list of boards to get background images '
                 'from. (Default: -b %s)' % " ".join(DEF_BOARDS))
    parser.add_argument('--min', nargs="+", type=int,
            help='Space separated minimum width and height for background '
                 'images. (Default --min %s %s)' % (DEF_MIN_DIMENSION[0], 
                     DEF_MIN_DIMENSION[1]))
    parser.add_argument('--max', nargs="+", type=int,
            help='Space separated maximum width and height for background '
                 'images. (Default --max %s %s)' % (DEF_MAX_DIMENSION[0], 
                     DEF_MAX_DIMENSION[1]))
    parser.add_argument('-f', '--folder',
            help='Folder for image storage. (Default -f img)')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-c', '--bg-center', action='store_const', const=True,
            help='Centers the image on the screen without scaling.')
    group.add_argument('-s', '--bg-scale', action='store_const', const=True,
            help="Scales the image to fite the screen  without "
                 "preserving aspect ratio")
    group.add_argument('-x', '--bg-max', action='store_const', const=True,
            help="Scales the image to max size that fits on the screen "
                 "with borders on one side")
    group.add_argument('-y', '--bg-fill', action='store_const', const=True,
            help="Scales the image preserving aspect ratio and zooms "
            "the image until it fits. (Note: This is the default method)")
    group.add_argument('-z', '--bg-tile', action='store_const', const=True,
            help="Tile (repeat) the image in case it is too small.")
    parser.add_argument('-w', '--flags',
            help='Additional arguments added to end of the feh command when '
                 'the background is changed. It is recommended to use the '
                 'syntax -w="<extra flags>" to avoid syntax issues. (eg. '
                 '-w="--no-xinerama --no-fehbg")')
    args = parser.parse_args()
    timeout = args.timeout or DEF_TIMEOUT
    args_min = args.min and len(args.min) > 1 and tuple(args.min[:2]) or None
    args_max = args.max and len(args.max) > 1 and tuple(args.max[:2]) or None
    if args.bg_center:
        scale_option = BG_CHANGE_OPT_CENTER
    elif args.bg_scale:
        scale_option = BG_CHANGE_OPT_SCALE
    elif args.bg_max:
        scale_option = BG_CHANGE_OPT_MAX
    elif args.bg_tile:
        scale_option = BG_CHANGE_OPT_TILE
    else:
        scale_option = BG_CHANGE_OPT_FILL
    options = create_options({'boards': args.boards,
            'image_folder': args.folder, 'min_dimension': args_min,
            'max_dimension': args_max, 'cmd_scale_option': scale_option,
            'cmd_suffix': args.flags,})
    cmd_list = [BG_CHANGE_CMD, options['cmd_scale_option'], "<filename>"]
    if options['cmd_suffix']:
        cmd_list.append(options['cmd_suffix'])
    logging.info('Starting chanbg.')
    logging.info('Current settings: timeout: %ss, boards: %s, folder: %s/, '
            'command: "%s", min_dimension: %s, max_dimension: %s' % (
                    timeout, options['boards'], options['image_folder'],
                    " ".join(cmd_list), options['min_dimension'][:2], 
                    options['max_dimension'][:2],)
            )
    try:
        while True:
            update_background(options)
            time.sleep(timeout)
    except KeyboardInterrupt as e:
        logging.info("Caught keyboard interrupt, exiting.")

