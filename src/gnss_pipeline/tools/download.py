"""FTP/HTTPS file fetching with decompression. Raises DownloadError on any failure."""

from __future__ import annotations

import ftplib
import gzip
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import requests


class DownloadError(Exception):
    pass


class _EarthdataSession(requests.Session):
    """Keep netrc auth across the CDDIS -> urs.earthdata.nasa.gov redirect."""

    AUTH_HOST = "urs.earthdata.nasa.gov"

    def rebuild_auth(self, prepared_request, response):
        headers = prepared_request.headers
        if "Authorization" in headers:
            orig = urlparse(response.request.url).hostname
            new = urlparse(prepared_request.url).hostname
            if orig != new and self.AUTH_HOST not in (orig, new):
                del headers["Authorization"]


def _fetch_ftp(url: str, dest: Path, timeout: float) -> None:
    u = urlparse(url)
    try:
        with ftplib.FTP(u.hostname, timeout=timeout) as ftp:
            ftp.login()
            with open(dest, "wb") as f:
                ftp.retrbinary(f"RETR {u.path}", f.write)
    except ftplib.error_perm as exc:
        raise DownloadError(f"not found on server: {exc}") from exc
    except (OSError, EOFError, ftplib.Error) as exc:
        raise DownloadError(f"FTP failure: {exc}") from exc


def _fetch_http(url: str, dest: Path, timeout: float) -> None:
    with _EarthdataSession() as s:
        try:
            r = s.get(url, timeout=timeout, stream=True)
        except requests.RequestException as exc:
            raise DownloadError(f"HTTP failure: {exc}") from exc
        if r.status_code != 200:
            raise DownloadError(f"HTTP {r.status_code}")
        if "text/html" in r.headers.get("Content-Type", ""):
            raise DownloadError("got HTML instead of data (login page?)")
        with open(dest, "wb") as f:
            f.writelines(r.iter_content(1 << 16))


def decompress(path: Path) -> Path:
    if path.suffix == ".gz":
        out = path.with_suffix("")
        with gzip.open(path, "rb") as src, open(out, "wb") as dst:
            shutil.copyfileobj(src, dst)
    elif path.suffix == ".Z":
        out = path.with_suffix("")
        with open(out, "wb") as dst:
            subprocess.run(["gzip", "-dc", str(path)], stdout=dst, check=True)
    else:
        return path
    path.unlink()
    return out


def fetch(url: str, dest_dir: Path, timeout: float = 60) -> Path:
    """Download url into dest_dir (cached), returning the decompressed file path."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = Path(urlparse(url).path).name
    final = dest_dir / (name[: -len(Path(name).suffix)] if name.endswith((".gz", ".Z")) else name)
    if final.exists() and final.stat().st_size > 0:
        return final

    tmp = dest_dir / (name + ".part")
    scheme = urlparse(url).scheme
    try:
        if scheme == "ftp":
            _fetch_ftp(url, tmp, timeout)
        elif scheme in ("http", "https"):
            _fetch_http(url, tmp, timeout)
        else:
            raise DownloadError(f"unsupported scheme {scheme}")
        if tmp.stat().st_size == 0:
            raise DownloadError("empty file")
        downloaded = tmp.rename(dest_dir / name)
        try:
            return decompress(downloaded)
        except (OSError, EOFError, subprocess.CalledProcessError) as exc:
            downloaded.unlink(missing_ok=True)
            raise DownloadError(f"corrupt archive: {exc}") from exc
    finally:
        tmp.unlink(missing_ok=True)
