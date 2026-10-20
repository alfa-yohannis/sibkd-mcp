"""Informasi Terbaru di beranda (/usulan) dan daftar pengumuman (/all_pengumuman).

Beranda dosen memuat satu blok "Informasi Terbaru" berisi instruksi pelaporan
bulan berjalan, mis. kapan harus mengunggah LKD dan menekan Lanjut Proses. Di
bawahnya ada cuplikan pengumuman; daftar lengkapnya di /all_pengumuman, berupa
tabel No, Pengumuman, File Pengumuman, dan Tanggal Pengumuman. Berkasnya PDF di
/assets/pengumuman/, mis. daftar penerima tunjangan sertifikasi.

Tanggal pengumuman ditulis dengan nama bulan bahasa Inggris ("7 August 2025"),
berbeda dari bagian SIBKD lainnya; keduanya diurai jadi tanggal ISO.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

from bs4 import BeautifulSoup, Comment

from sibkd_mcp.bulan import tanggal_iso
from sibkd_mcp.konfigurasi import baca_pengaturan
from sibkd_mcp.sibkd_client import KlienSibkd, SibkdError, nama_berkas_aman, path_beranda

PATH_PENGUMUMAN_BAWAAN = "/all_pengumuman"


def path_pengumuman() -> str:
    """Path daftar pengumuman lengkap."""
    return baca_pengaturan("SIBKD_PATH_PENGUMUMAN", PATH_PENGUMUMAN_BAWAAN)


@dataclass
class InformasiTerbaru:
    """Blok "Informasi Terbaru" di beranda."""

    judul: str
    isi: str

    def sebagai_dict(self) -> dict:
        return asdict(self)


@dataclass
class Pengumuman:
    """Satu baris tabel pengumuman beserta berkas PDF-nya."""

    nomor: int
    judul: str
    nama_berkas: str
    url: str
    tanggal_teks: str

    @property
    def tanggal(self) -> str:
        """Tanggal ISO, mis. '2025-08-07'; kosong kalau tidak terbaca."""
        return tanggal_iso(self.tanggal_teks)

    def cocok(self, cari: str) -> bool:
        """Apakah judul atau nama berkasnya memuat `cari` (tanpa membedakan huruf besar)."""
        dicari = (cari or "").strip().lower()
        return not dicari or dicari in self.judul.lower() or dicari in self.nama_berkas.lower()

    def sebagai_dict(self) -> dict:
        return asdict(self) | {"tanggal": self.tanggal}


def urai_informasi_terbaru(html: str) -> InformasiTerbaru | None:
    """Blok Informasi Terbaru; None kalau beranda tidak menampilkannya."""
    sup = BeautifulSoup(html, "lxml")
    for badan in sup.select(".card-body"):
        if not badan.get_text(" ", strip=True).lower().startswith("informasi terbaru"):
            continue
        judul_el = badan.find("b")
        judul = judul_el.get_text(" ", strip=True) if judul_el else ""
        for komentar in badan.find_all(string=lambda isi: isinstance(isi, Comment)):
            komentar.extract()
        for br in badan.find_all("br"):
            br.replace_with("\n")
        baris = [satu.strip() for satu in badan.get_text().splitlines()]
        baris = [satu for satu in baris if satu]
        if baris and baris[0].lower().startswith("informasi terbaru"):
            sisa = baris[0].split(":", 1)[1].strip() if ":" in baris[0] else ""
            baris = ([sisa] if sisa else []) + baris[1:]
        if judul and baris and baris[0] == judul:
            baris = baris[1:]
        return InformasiTerbaru(judul=judul, isi="\n".join(baris))
    return None


def urai_pengumuman(html: str) -> list[Pengumuman]:
    """Seluruh baris tabel pengumuman, urut seperti di halaman."""
    sup = BeautifulSoup(html, "lxml")
    tabel = sup.select_one("table.allpengumuman") or next(
        (satu for satu in sup.find_all("table") if "pengumuman" in satu.get_text(" ", strip=True).lower()),
        None,
    )
    if tabel is None:
        raise SibkdError("Tabel pengumuman tidak ditemukan; tampilan SIBKD mungkin berubah")

    hasil = []
    for baris in tabel.select("tbody tr") or tabel.find_all("tr"):
        sel = baris.find_all("td")
        if len(sel) < 4:
            continue
        tautan = sel[2].find("a", href=True)
        nomor = re.sub(r"\D", "", sel[0].get_text())
        hasil.append(Pengumuman(
            nomor=int(nomor) if nomor else len(hasil) + 1,
            judul=sel[1].get_text(" ", strip=True),
            nama_berkas=tautan.get_text(" ", strip=True) if tautan else sel[2].get_text(" ", strip=True),
            url=tautan["href"] if tautan else "",
            tanggal_teks=re.sub(r"\s+", " ", sel[3].get_text(" ", strip=True)),
        ))
    return hasil


class PapanPengumuman:
    """Akses Informasi Terbaru dan daftar pengumuman untuk satu sesi SIBKD."""

    def __init__(self, klien: KlienSibkd):
        self.klien = klien

    def informasi_terbaru(self) -> InformasiTerbaru | None:
        return urai_informasi_terbaru(self.klien.ambil_halaman(path_beranda()).text)

    def daftar(self) -> list[Pengumuman]:
        return urai_pengumuman(self.klien.ambil_halaman(path_pengumuman()).text)

    def unduh(self, tujuan: str | Path, *, cari: str = "", timpa: bool = False) -> dict:
        """Unduh berkas pengumuman yang judul/nama berkasnya memuat `cari` (kosong = semua)."""
        hasil = {"tujuan": str(tujuan), "berkas": [], "dilewati": [], "gagal": []}
        for satu in self.daftar():
            if not satu.url or not satu.cocok(cari):
                continue
            try:
                path, baru = self.klien.unduh(satu.url, Path(tujuan) / nama_berkas_aman(satu.nama_berkas), timpa=timpa)
            except SibkdError as galat:
                hasil["gagal"].append({"judul": satu.judul, "pesan": str(galat)})
                continue
            hasil["berkas" if baru else "dilewati"].append(str(path))
        if not (hasil["berkas"] or hasil["dilewati"] or hasil["gagal"]):
            hasil["pesan"] = f"Tidak ada pengumuman yang cocok dengan {cari!r}" if cari else "Belum ada pengumuman"
        return hasil
