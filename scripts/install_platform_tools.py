"""Fetch a pinned Google Platform-Tools build for independent USB communication."""
import hashlib
from pathlib import Path
import shutil
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://dl.google.com/android/repository/platform-tools_r37.0.1-win.zip'
SHA256 = '45f4d63113e895ebde0c90f194099a4676b6ac653bd28d54314a9e022bbc1a99'


def main():
    build = ROOT/'build'; build.mkdir(exist_ok=True)
    archive = build/'platform-tools-37.0.1.zip'
    if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        with urllib.request.urlopen(URL, timeout=60) as response, archive.open('wb') as output:
            shutil.copyfileobj(response, output)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        raise RuntimeError('Google Platform-Tools checksum mismatch.')
    target = ROOT/'tools'
    target.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        for item in package.infolist():
            resolved = (target/item.filename).resolve()
            if not resolved.is_relative_to(target.resolve()) or not item.filename.startswith('platform-tools/'):
                raise RuntimeError('Unexpected archive entry.')
        package.extractall(target)
    print('Google Platform-Tools 37.0.1 installed; SHA256 verified.')


if __name__ == '__main__': main()
