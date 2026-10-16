"""Distinguish media URLs from local paths, including Windows drive letters."""
import ntpath
import os
from urllib.parse import unquote, urlparse


def source_scheme(source):
    source = str(source)
    # urlparse treats C:\Music and C:/Music as URLs with scheme 'c'.
    if ntpath.splitdrive(source)[0] and (source[1:2] == ':' or source.startswith('\\\\')):
        return ''
    return urlparse(source).scheme


def file_uri_path(source):
    parsed = urlparse(str(source))
    path = unquote(parsed.path)
    if os.name == 'nt':
        if parsed.netloc and parsed.netloc.lower() != 'localhost':
            return '//'+parsed.netloc+path
        if path.startswith('/') and path[2:3] == ':':
            path = path[1:]
    return path
