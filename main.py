import os
import re
import subprocess
import shutil
import requests
from urllib.parse import urlparse

DOWNLOAD_DIR = "downloads"
BULK_FILE = "bulk.txt"

HEADERS = {
    "Referer": "https://streamrizz.com/",
    "Origin": "https://streamrizz.com",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "sec-ch-ua": '"Not=A?Brand";v="99", "Chromium";v="124"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Range": "bytes=0-",
}


def check_ffmpeg():
    if shutil.which("ffmpeg") is None:
        print("\n[!] ffmpeg tidak ditemukan. Install dulu, contoh:")
        print("    sudo apt-get update && sudo apt-get install -y ffmpeg\n")
        return False
    return True


def get_unique_filepath(directory, filename):
    name, ext = os.path.splitext(filename)
    filepath = os.path.join(directory, filename)
    counter = 1

    while os.path.exists(filepath):
        filepath = os.path.join(directory, f"{name} ({counter}){ext}")
        counter += 1

    return filepath


def build_output_filename(url):
    path = urlparse(url).path
    filename = os.path.basename(path)
    name_only, _ext = os.path.splitext(filename)

    if name_only in ["master", "index", "playlist"] and _ext == ".m3u8":
        parts = path.strip("/").split("/")
        if len(parts) >= 2:
            name_only = parts[-2]

    if not name_only:
        name_only = "video"

    return f"{name_only}.mp4"


def headers_to_ffmpeg_arg():
    ffmpeg_headers = {k: v for k, v in HEADERS.items() if k != "Range"}
    return "".join(f"{k}: {v}\r\n" for k, v in ffmpeg_headers.items())


def is_hls_url(url):
    return url.lower().split("?")[0].endswith(".m3u8")


def download_hls(url, filepath):
    print(f"\nDownloading (HLS): {os.path.basename(filepath)}")

    cmd = [
        "ffmpeg",
        "-y",
        "-headers", headers_to_ffmpeg_arg(),
        "-i", url,
        "-c", "copy",
        "-bsf:a", "aac_adtstoasc",
        filepath,
    ]

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )

    time_re = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")

    for line in process.stdout:
        match = time_re.search(line)
        if match:
            h, m, s = match.groups()
            elapsed = f"{h}:{m}:{s}"
            print(f"\r[HLS] Progress: {elapsed}", end="", flush=True)

    process.wait()
    print()

    if process.returncode != 0:
        print("Gagal download HLS (cek apakah URL/headers valid).")
        if os.path.exists(filepath):
            os.remove(filepath)
        return False

    return True


def download_direct(url, filepath):
    print(f"\nDownloading: {os.path.basename(filepath)}")

    try:
        with requests.get(url, headers=HEADERS, stream=True) as r:
            r.raise_for_status()

            total_size = int(r.headers.get("content-length", 0))
            downloaded = 0
            chunk_size = 8192

            with open(filepath, "wb") as f:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        if total_size > 0:
                            percent = downloaded * 100 / total_size
                            bar_length = 30
                            filled = int(bar_length * downloaded / total_size)
                            bar = "█" * filled + "-" * (bar_length - filled)

                            print(
                                f"\r[{bar}] {percent:5.1f}% ({downloaded}/{total_size} bytes)",
                                end="",
                                flush=True,
                            )

        print()
        return True

    except Exception as e:
        print("\nError:", e)
        return False


def download_file(url):
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    filename = build_output_filename(url)
    filepath = get_unique_filepath(DOWNLOAD_DIR, filename)

    if is_hls_url(url):
        if not check_ffmpeg():
            return False
        success = download_hls(url, filepath)
    else:
        success = download_direct(url, filepath)

    if not success:
        return False

    if not os.path.exists(filepath):
        print("File tidak ditemukan setelah download.")
        return False

    size = os.path.getsize(filepath)
    print(f"Ukuran file: {size} bytes")

    if size < 1000000:
        print("File terlalu kecil, kemungkinan bukan video.")
        if os.path.exists(filepath):
            os.remove(filepath)
        return False

    print(f"Selesai → {filepath}")
    return True


def single_download():
    url = input("Masukkan URL MP4/M3U8: ").strip()
    if url:
        download_file(url)


def parse_range(range_str, total):
    """
    Terima input seperti:
    - "50"      -> ambil 50 pertama
    - "1-50"    -> ambil index 1 s/d 50
    - "all"     -> ambil semua
    Return (start_idx, end_idx) 0-based, end exclusive.
    """

    range_str = range_str.strip().lower()

    if range_str == "" or range_str == "all":
        return 0, total

    if "-" in range_str:
        try:
            start, end = range_str.split("-")
            start = int(start)
            end = int(end)
        except ValueError:
            print("⚠️ Format range salah, pakai semua list")
            return 0, total

        start_idx = max(0, start - 1)
        end_idx = min(total, end)
        return start_idx, end_idx

    try:
        n = int(range_str)
        return 0, min(total, n)
    except ValueError:
        print("⚠️ Format salah, pakai semua list")
        return 0, total


def bulk_download():
    if not os.path.exists(BULK_FILE):
        print(f"File {BULK_FILE} tidak ditemukan.")
        return

    with open(BULK_FILE, "r") as f:
        urls = [line.strip() for line in f if line.strip()]

    total = len(urls)

    if total == 0:
        print("bulk.txt kosong.")
        return

    print(f"\nMenemukan {total} URL di {BULK_FILE}.")

    range_str = input("Mau download berapa? (contoh: 50 / 1-50 / all): ")

    start_idx, end_idx = parse_range(range_str, total)

    selected = urls[start_idx:end_idx]

    print(f"\n▶️ Akan download {len(selected)} URL (index {start_idx + 1}-{end_idx})\n")

    success_urls = []

    for i, url in enumerate(selected, 1):
        print(f"\n=== Download {i}/{len(selected)} ===")

        ok = download_file(url)

        if ok:
            success_urls.append(url)
        else:
            print(f"❌ Gagal: {url} (tetap di {BULK_FILE})")

    # update bulk.txt: hapus url yang sudah sukses didownload
    remaining = [u for u in urls if u not in success_urls]

    with open(BULK_FILE, "w") as f:
        f.write("\n".join(remaining))
        if remaining:
            f.write("\n")

    print(f"\n✅ Bulk download selesai. {len(success_urls)} berhasil, {len(remaining)} sisa di {BULK_FILE}.")


def main():
    while True:
        print("\n===== VIDEO DOWNLOADER =====")
        print("1. Single Download")
        print("2. Bulk Download (bulk.txt)")
        print("3. Keluar")

        choice = input("Pilih menu: ").strip()

        if choice == "1":
            single_download()
        elif choice == "2":
            bulk_download()
        elif choice == "3":
            print("Keluar.")
            break
        else:
            print("Pilihan tidak valid.")


if __name__ == "__main__":
    main()
