"""Klien SIBKD LLDIKTI III: login, baca halaman, kirim permintaan tulis, unduh berkas.

SIBKD adalah aplikasi CodeIgniter sederhana. Loginnya satu langkah, tanpa token
CSRF dan tanpa captcha, dengan NIDN sebagai username:

    GET  /login/login   -> form username + password, cookie PHPSESSID
    POST /login/login   -> 303 ke /usulan/usulan kalau diterima,
                           303 ke /login/login?pesan=error kalau ditolak

Halaman yang dibuka tanpa sesi dialihkan (307) ke /login/login?pesan=belumlogin.
Klien ini mengenali keadaan itu dan login ulang sekali, supaya sesi yang
kedaluwarsa di tengah jalan tidak menggagalkan pembacaan.

Semua modul lain (CLI, REST API, MCP) memakai kelas di sini, jadi logika login,
pengiriman, dan pengunduhan hanya ditulis sekali.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from sibkd_mcp.konfigurasi import baca_angka, baca_kredensial, baca_pengaturan, buat_sesi_http

# alamat bawaan; instance lain diatur lewat SIBKD_BASE_URL di .env atau
# base_url: di sibkd.yaml, tanpa menyentuh kode
SIBKD_BASE_URL_BAWAAN = "https://sibkd-lldikti3.kemdiktisaintek.go.id"
PATH_LOGIN_BAWAAN = "/login/login"
PATH_BERANDA_BAWAAN = "/usulan"

# Batas waktu tiap jenis permintaan, dalam detik. Halaman biasa cepat; unggahan
# PDF dan sinkronisasi ke SISTER bisa lama, jadi batasnya dipisah.
BATAS_LOGIN_BAWAAN_DETIK = 60
BATAS_HALAMAN_BAWAAN_DETIK = 120
BATAS_KIRIM_BAWAAN_DETIK = 300

KODE_PENGALIHAN = (301, 302, 303, 307, 308)


class SibkdError(RuntimeError):
    """Kegagalan yang berasal dari SIBKD (login ditolak, halaman berubah, balasan aneh)."""


def alamat_sibkd() -> str:
    """Alamat instance SIBKD.

    Urutannya SIBKD_BASE_URL, lalu asal dari SIBKD_WEBSITE (yang di .env biasanya
    berisi alamat halaman login), lalu alamat bawaan LLDIKTI III.
    """
    ditetapkan = baca_pengaturan("SIBKD_BASE_URL")
    if ditetapkan:
        return ditetapkan.rstrip("/")
    situs = urlparse(baca_pengaturan("SIBKD_WEBSITE"))
    if situs.scheme and situs.netloc:
        return f"{situs.scheme}://{situs.netloc}"
    return SIBKD_BASE_URL_BAWAAN


def path_login() -> str:
    """Path form login; instance lain bisa memakai alamat berbeda."""
    return baca_pengaturan("SIBKD_PATH_LOGIN", PATH_LOGIN_BAWAAN)


def path_beranda() -> str:
    """Path beranda dosen, tempat blok Informasi Terbaru."""
    return baca_pengaturan("SIBKD_PATH_BERANDA", PATH_BERANDA_BAWAAN)


def adalah_halaman_login(url: str) -> bool:
    """Apakah alamat ini halaman login, tempat SIBKD membuang sesi yang tidak sah."""
    return urlparse(url or "").path.rstrip("/").endswith(path_login().rstrip("/"))


def teks_ringkas(html: str, batas: int = 300) -> str:
    """Isi teks sebuah balasan HTML, dirapatkan, untuk pesan galat."""
    teks = BeautifulSoup(html or "", "lxml").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", teks)[:batas]


def baca_jawaban_json(jawaban) -> dict:
    """Terjemahkan balasan endpoint tulis SIBKD jadi {ok, status, pesan, status_http}.

    Semua endpoint tulis membalas {"status": "success"|..., "message": "..."}.
    Sebagian mengirimnya dengan tipe text/html (halamannya sendiri memanggil
    JSON.parse), jadi badan teks juga dicoba diurai sebagai JSON.
    """
    hasil = {"ok": False, "status": "", "pesan": "", "status_http": jawaban.status_code}
    try:
        badan = jawaban.json()
    except ValueError:
        try:
            badan = json.loads((jawaban.text or "").strip().lstrip("﻿"))
        except ValueError:
            badan = None

    if isinstance(badan, dict):
        hasil["status"] = str(badan.get("status", ""))
        hasil["pesan"] = str(badan.get("message") or badan.get("pesan") or "")
        hasil["ok"] = jawaban.status_code < 400 and hasil["status"].lower() == "success"
        hasil["mentah"] = badan
        return hasil

    hasil["pesan"] = f"Balasan SIBKD bukan JSON (HTTP {jawaban.status_code}): {teks_ringkas(jawaban.text)}"
    return hasil


def baca_nama_pengguna(html: str) -> str:
    """Nama dosen yang tercetak di kepala halaman setelah login."""
    sup = BeautifulSoup(html or "", "lxml")
    for pemilih in (".profile-pic .hidden-md-down", ".chatonline span"):
        tempat = sup.select_one(pemilih)
        if tempat:
            teks = tempat.get_text("\n", strip=True).split("\n")[0]
            if teks:
                return teks.strip()
    return ""


def nama_berkas_aman(nama: str, cadangan: str = "berkas.pdf") -> str:
    """Nama berkas yang aman ditulis ke disk: tanpa folder dan tanpa karakter aneh."""
    dasar = Path(str(nama or "")).name
    dasar = re.sub(r"[^A-Za-z0-9._ ()-]+", "_", dasar).strip(" .")
    return dasar or cadangan


class KlienSibkd:
    """Sesi SIBKD milik satu dosen. Cukup beri NIDN dan password."""

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        base_url: str = "",
    ):
        # kalau tidak diberikan, jatuh ke .env supaya pemakaian CLI tetap ringkas
        if not username or not password:
            kredensial = baca_kredensial("SIBKD_USERNAME", "SIBKD_PASSWORD")
            username = username or kredensial["SIBKD_USERNAME"]
            password = password or kredensial["SIBKD_PASSWORD"]
        self.username = username
        self.password = password
        self.base_url = (base_url or alamat_sibkd()).rstrip("/")
        self.sesi_http = buat_sesi_http()
        self.url_beranda = ""
        self.nama = ""

    def url(self, path_atau_url: str) -> str:
        """URL penuh dari path relatif; URL penuh dipakai apa adanya."""
        if path_atau_url.startswith(("http://", "https://")):
            return path_atau_url
        if path_atau_url.startswith("/"):
            return f"{self.base_url}{path_atau_url}"
        return urljoin(f"{self.base_url}/", path_atau_url)

    def login(self) -> "KlienSibkd":
        """Login satu langkah ke SIBKD; SibkdError kalau kredensialnya ditolak."""
        batas = baca_angka("SIBKD_BATAS_LOGIN_DETIK", BATAS_LOGIN_BAWAAN_DETIK)
        halaman = self.sesi_http.get(self.url(path_login()), timeout=batas)
        if halaman.status_code != 200:
            raise SibkdError(f"Halaman login SIBKD tidak bisa dibuka (HTTP {halaman.status_code})")
        sup = BeautifulSoup(halaman.text, "lxml")
        form = next((satu for satu in sup.find_all("form") if satu.find("input", {"type": "password"})), None)
        if form is None:
            raise SibkdError(f"Form login tidak ditemukan di {halaman.url}")

        isian = {
            masukan["name"]: masukan.get("value", "")
            for masukan in form.find_all("input")
            if masukan.get("name") and (masukan.get("type") or "text").lower() not in ("submit", "button", "checkbox")
        }
        nama_sandi = form.find("input", {"type": "password"})["name"]
        nama_pengguna = next(
            (
                masukan["name"]
                for masukan in form.find_all("input")
                if masukan.get("name") and (masukan.get("type") or "text").lower() in ("text", "email", "number")
            ),
            "username",
        )
        isian[nama_pengguna] = self.username
        isian[nama_sandi] = self.password

        jawaban = self.sesi_http.post(
            urljoin(halaman.url, form.get("action") or halaman.url),
            data=isian,
            timeout=batas,
            allow_redirects=True,
            headers={"Referer": halaman.url},
        )
        if jawaban.status_code >= 400:
            raise SibkdError(f"Login SIBKD gagal (HTTP {jawaban.status_code})")
        # login yang ditolak kembali ke form login dengan ?pesan=error, tanpa teks pesan
        if adalah_halaman_login(jawaban.url):
            raise SibkdError("Login SIBKD ditolak; periksa SIBKD_USERNAME (NIDN) dan SIBKD_PASSWORD")

        self.url_beranda = jawaban.url
        self.nama = baca_nama_pengguna(jawaban.text)
        return self

    def _get(self, url: str, **kwargs):
        batas = baca_angka("SIBKD_BATAS_HALAMAN_DETIK", BATAS_HALAMAN_BAWAAN_DETIK)
        return self.sesi_http.get(url, timeout=batas, **kwargs)

    def ambil_halaman(self, path_atau_url: str):
        """GET halaman SIBKD. Terima path relatif maupun URL penuh.

        Kalau SIBKD mengalihkan ke halaman login (sesi habis), login ulang sekali
        lalu ulangi permintaannya.
        """
        url = self.url(path_atau_url)
        jawaban = self._get(url)
        if adalah_halaman_login(jawaban.url) and not adalah_halaman_login(url):
            self.login()
            jawaban = self._get(url)
            if adalah_halaman_login(jawaban.url):
                raise SibkdError(f"SIBKD terus mengalihkan {url} ke halaman login")
        if jawaban.status_code != 200:
            raise SibkdError(f"Halaman {url} tidak bisa dibuka (HTTP {jawaban.status_code})")
        return jawaban

    def kirim(self, path_atau_url: str, *, data=None, files=None, referer: str = "") -> dict:
        """POST ke endpoint tulis SIBKD; balasannya lewat baca_jawaban_json().

        Pengalihan sengaja tidak diikuti. Kalau sesi sudah habis, SIBKD
        mengalihkan POST ini dengan 307 ke halaman login, dan requests akan ikut
        mengirim ulang seluruh muatannya (termasuk PDF) ke form login. Yang
        dilakukan di sini: login ulang lalu kirim sekali lagi. Muatan pertama
        memang belum diproses karena ditolak sebelum sampai ke endpointnya.
        `files` harus berisi bytes, bukan berkas terbuka, supaya bisa dikirim ulang.
        """
        url = self.url(path_atau_url)
        batas = baca_angka("SIBKD_BATAS_KIRIM_DETIK", BATAS_KIRIM_BAWAAN_DETIK)
        kepala = {
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": referer or self.url_beranda or self.base_url,
        }
        for percobaan in range(2):
            jawaban = self.sesi_http.post(
                url, data=data, files=files, headers=kepala, timeout=batas, allow_redirects=False
            )
            lokasi = urljoin(url, jawaban.headers.get("Location", ""))
            if jawaban.status_code in KODE_PENGALIHAN and adalah_halaman_login(lokasi):
                if percobaan == 0:
                    self.login()
                    continue
                raise SibkdError(f"SIBKD terus mengalihkan {url} ke halaman login")
            if jawaban.status_code in KODE_PENGALIHAN:
                raise SibkdError(f"SIBKD mengalihkan {url} ke {lokasi} alih-alih membalas")
            return baca_jawaban_json(jawaban)
        raise SibkdError(f"Permintaan ke {url} tidak terkirim")

    def unduh(self, url: str, tujuan: Path, *, timpa: bool = False) -> tuple[Path, bool]:
        """Unduh satu berkas SIBKD ke path `tujuan`. Balikan: (path, baru_diunduh).

        Hanya berkas dari host SIBKD sendiri yang diunduh. Berkas yang sudah ada
        dilewati kecuali `timpa`, dan berkas ditulis lewat nama sementara supaya
        unduhan yang terputus tidak meninggalkan PDF setengah jadi.
        """
        alamat = self.url(url)
        if urlparse(alamat).netloc != urlparse(self.base_url).netloc:
            raise SibkdError(f"Menolak mengunduh dari luar SIBKD: {alamat}")
        tujuan = Path(tujuan)
        if tujuan.exists() and not timpa:
            return tujuan, False

        with self._get(alamat, stream=True) as jawaban:
            if jawaban.status_code != 200:
                raise SibkdError(f"Gagal mengunduh {alamat} (HTTP {jawaban.status_code})")
            if adalah_halaman_login(jawaban.url) or jawaban.headers.get("Content-Type", "").startswith("text/html"):
                raise SibkdError(f"{alamat} membalas halaman HTML, bukan berkas")
            tujuan.parent.mkdir(parents=True, exist_ok=True)
            sementara = tujuan.with_name(tujuan.name + ".sebagian")
            with open(sementara, "wb") as keluaran:
                for potongan in jawaban.iter_content(chunk_size=65536):
                    keluaran.write(potongan)
        sementara.replace(tujuan)
        return tujuan, True

    def daftar_navigasi(self) -> list[dict]:
        """Menu yang tersedia setelah login, urut seperti di sidebar SIBKD."""
        sup = BeautifulSoup(self.ambil_halaman(self.url_beranda or path_beranda()).text, "lxml")
        wadah = sup.select_one("#sidebarnav") or sup
        menu: dict[str, str] = {}
        for tautan in wadah.find_all("a", href=True):
            teks = tautan.get_text(" ", strip=True)
            alamat = self.url(tautan["href"])
            if teks and alamat.startswith(self.base_url) and "logout" not in alamat.lower():
                menu.setdefault(alamat, teks[:60])
        # halaman pengumuman tidak ada di sidebar, hanya ditautkan dari beranda
        for tautan in sup.find_all("a", href=True):
            alamat = self.url(tautan["href"])
            if "pengumuman" in alamat and not alamat.lower().endswith(".pdf"):
                menu.setdefault(alamat, "Pengumuman")
        return [{"nama": nama, "url": alamat} for alamat, nama in menu.items()]


def galat_jaringan(galat: requests.RequestException) -> str:
    """Pesan satu baris untuk kegagalan jaringan, tanpa jejak tumpukan."""
    if isinstance(galat, requests.exceptions.SSLError):
        return f"Verifikasi TLS ke SIBKD gagal: {galat}. Periksa SIBKD_CA_BUNDLE kalau Anda mengisinya."
    if isinstance(galat, requests.exceptions.Timeout):
        return "SIBKD tidak menjawab dalam batas waktu; coba lagi atau naikkan batas_*_detik di sibkd.yaml"
    return f"Tidak bisa menghubungi SIBKD: {galat}"
