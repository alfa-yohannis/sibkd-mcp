"""REST API SIBKD LLDIKTI III.

Menyediakan status laporan BKD SISTER v2 bulanan, rincian satu bulan (NIK,
NPWP, nomor HP, dan tanggal lahir disamarkan), pengumuman, dan unduhan PDF.
Empat endpoint menulis ke SIBKD (unggah, sinkron, tunda, lanjut proses) dan
semuanya menerima `uji_coba`.

Jalankan:
    ./sibkd api              # http://localhost:8000

Contoh:
    curl -X POST "localhost:8000/status" -H "Content-Type: application/json" \
         -d '{"username":"0000000000","password":"..."}'
"""

from __future__ import annotations

import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import requests
from fastapi import APIRouter, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from sibkd_mcp import __version__
from sibkd_mcp.bkd_sister import BkdSister, BulanTidakDitemukan, daftar_jenis_sinkron
from sibkd_mcp.konfigurasi import (
    KonfigurasiError,
    baca_angka,
    baca_pengaturan,
    dir_data,
    path_dari_akar,
    path_masukan,
)
from sibkd_mcp.pengumuman import PapanPengumuman
from sibkd_mcp.sibkd_client import KlienSibkd, SibkdError, galat_jaringan, nama_berkas_aman

# nama instansi hanya untuk label; tidak memengaruhi perilaku apa pun
NAMA_INSTANSI = baca_pengaturan("SIBKD_NAMA_INSTANSI", "LLDIKTI Wilayah III")

# Rute dikumpulkan di router, bukan langsung di app, supaya proyek lain bisa
# menempelkannya ke aplikasi FastAPI miliknya sendiri:
#     from sibkd_mcp.api import router
#     app_saya.include_router(router, prefix="/sibkd")
router = APIRouter()


def buat_app() -> FastAPI:
    """Aplikasi FastAPI berdiri sendiri yang hanya berisi rute paket ini."""
    app = FastAPI(
        title=f"SIBKD {NAMA_INSTANSI} API",
        version=__version__,
        description=(
            "Pantau laporan BKD SISTER v2 bulanan di SIBKD: status tiap bulan, rincian golongan "
            "penyetaraan dan tunjangan, pengumuman, dan PDF laporan. Empat endpoint menulis "
            "(unggah, sinkron, tunda, lanjut) dan semuanya menerima uji_coba."
        ),
    )
    app.include_router(router)
    return app


# satu sesi login dipakai ulang selama masih segar
UMUR_SESI_DETIK = baca_angka("SIBKD_UMUR_SESI_DETIK", 900)
sesi_tersimpan: dict[str, tuple[float, KlienSibkd]] = {}


class Kredensial(BaseModel):
    username: str = Field(description="Username SIBKD, yaitu NIDN")
    password: str = Field(description="Password SIBKD")


class PermintaanBulan(Kredensial):
    bulan: str = Field(default="", description="Mis. 'Oktober 2026', 'oktober', atau '10'; kosong = bulan berjalan")
    id_periode: str = Field(default="", description="Kosong berarti periode aktif")


class PermintaanUnduh(Kredensial):
    jenis: str = Field(default="laporan", description="laporan (PDF BKD satu periode) atau pengumuman")
    id_periode: str = Field(default="", description="Untuk laporan; kosong berarti periode aktif")
    cari: str = Field(default="", description="Untuk pengumuman: saring judul atau nama berkas")
    tujuan: str = Field(default="", description="Folder penyimpanan; kosong = data/laporan_bkd atau data/pengumuman")
    timpa: bool = Field(default=False, description="Unduh ulang berkas yang sudah ada")


class PermintaanTulis(Kredensial):
    bulan: str = Field(description="Bulan laporan, mis. 'Oktober 2026' atau 'oktober'")
    id_periode: str = Field(default="", description="Kosong berarti periode aktif")
    uji_coba: bool = Field(default=False, description="true: tampilkan alamat dan muatannya, jangan kirim")


class PermintaanSinkron(PermintaanTulis):
    jenis: str = Field(description="identitas, homebase, pendidikan, jafung, kepangkatan; pisahkan koma, atau 'semua'")


class PermintaanUnggah(PermintaanTulis):
    berkas: str = Field(
        description="Path PDF di mesin yang menjalankan API; relatif dari direktori kerja server, lalu akar proyek"
    )


class PermintaanLanjut(PermintaanTulis):
    setuju_pernyataan: bool = Field(
        default=False, description="true: pemakai sudah membaca dan menyetujui keempat pernyataan"
    )


@contextmanager
def terjemahkan_galat():
    """Kesalahan pustaka jadi status HTTP yang bermakna, bukan 500 tanpa penjelasan."""
    try:
        yield
    except BulanTidakDitemukan as galat:
        raise HTTPException(status_code=404, detail=str(galat))
    except ValueError as galat:
        raise HTTPException(status_code=422, detail=str(galat))
    except KonfigurasiError as galat:
        raise HTTPException(status_code=500, detail=str(galat))
    except SibkdError as galat:
        raise HTTPException(status_code=502, detail=str(galat))
    except requests.RequestException as galat:
        raise HTTPException(status_code=504, detail=galat_jaringan(galat))


def ambil_klien(kredensial: Kredensial) -> KlienSibkd:
    """Login sekali, lalu pakai ulang sesinya untuk permintaan berikutnya."""
    kunci = f"{kredensial.username}:{hash(kredensial.password)}"
    tersimpan = sesi_tersimpan.get(kunci)
    if tersimpan and time.monotonic() - tersimpan[0] < UMUR_SESI_DETIK:
        return tersimpan[1]
    try:
        klien = KlienSibkd(kredensial.username, kredensial.password).login()
    except SibkdError as galat:
        raise HTTPException(status_code=401, detail=str(galat))
    except requests.RequestException as galat:
        raise HTTPException(status_code=504, detail=galat_jaringan(galat))
    sesi_tersimpan[kunci] = (time.monotonic(), klien)
    return klien


@router.post("/sesi", summary="Cek kredensial SIBKD")
def cek_sesi(kredensial: Kredensial):
    klien = ambil_klien(kredensial)
    return {"ok": True, "beranda": klien.url_beranda, "nama": klien.nama}


@router.post("/menu", summary="Menu SIBKD yang tersedia bagi akun ini")
def daftar_menu(kredensial: Kredensial):
    with terjemahkan_galat():
        return {"data": ambil_klien(kredensial).daftar_navigasi()}


@router.post("/status", summary="Status laporan BKD SISTER v2: periode x bulan dan berkas PDF")
def status_laporan(kredensial: Kredensial):
    with terjemahkan_galat():
        return BkdSister(ambil_klien(kredensial)).status().sebagai_dict()


@router.post("/detail", summary="Rincian satu bulan laporan; data pribadi disamarkan")
def detail_laporan(permintaan: PermintaanBulan):
    """NIK, NPWP, nomor HP, dan tanggal lahir hanya menyisakan 4 karakter terakhir.

    Nominal tunjangan ditampilkan apa adanya karena SIBKD meminta dosen
    memeriksa kesesuaiannya.
    """
    with terjemahkan_galat():
        detail = BkdSister(ambil_klien(permintaan)).detail(permintaan.bulan, permintaan.id_periode)
        return detail.sebagai_dict(samarkan_pribadi=True)


@router.post("/pengumuman", summary="Informasi Terbaru di beranda dan daftar pengumuman")
def pengumuman(kredensial: Kredensial):
    with terjemahkan_galat():
        papan = PapanPengumuman(ambil_klien(kredensial))
        informasi = papan.informasi_terbaru()
        return {
            "informasi_terbaru": informasi.sebagai_dict() if informasi else None,
            "data": [satu.sebagai_dict() for satu in papan.daftar()],
        }


def unduh(permintaan: PermintaanUnduh) -> dict:
    """Simpan PDF laporan atau pengumuman ke folder tujuan; dipakai dua endpoint di bawah."""
    jenis = permintaan.jenis.strip().lower()
    if jenis not in ("laporan", "pengumuman"):
        raise HTTPException(status_code=422, detail="jenis harus 'laporan' atau 'pengumuman'")
    bawaan = dir_data() / ("laporan_bkd" if jenis == "laporan" else "pengumuman")
    tujuan = path_dari_akar(permintaan.tujuan) if permintaan.tujuan else bawaan
    with terjemahkan_galat():
        klien = ambil_klien(permintaan)
        if jenis == "laporan":
            return BkdSister(klien).unduh_laporan(tujuan, id_periode=permintaan.id_periode, timpa=permintaan.timpa)
        return PapanPengumuman(klien).unduh(tujuan, cari=permintaan.cari, timpa=permintaan.timpa)


@router.post("/berkas/unduh", summary="Simpan PDF laporan BKD atau berkas pengumuman ke folder")
def unduh_berkas(permintaan: PermintaanUnduh):
    """Berkas yang sudah ada dilewati kecuali `timpa` bernilai true."""
    return unduh(permintaan)


@router.post("/berkas/pdf", summary="Kembalikan satu PDF (laporan periode atau pengumuman pertama yang cocok)")
def berkas_pdf(permintaan: PermintaanUnduh):
    hasil = unduh(permintaan)
    semua = hasil["berkas"] + hasil["dilewati"]
    if not semua:
        raise HTTPException(status_code=404, detail=hasil.get("pesan") or "Tidak ada berkas yang cocok")
    path = Path(semua[0])
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@router.post("/sinkron", summary="Tarik ulang data dari SISTER/PDDIKTI (menulis)")
def sinkronkan_data(permintaan: PermintaanSinkron):
    """**Menulis** ke SIBKD. Hanya bisa pada bulan yang sedang dibuka dan tidak dikunci Admin PT."""
    with terjemahkan_galat():
        daftar_jenis_sinkron(permintaan.jenis)  # tolak jenis yang salah sebelum login
        return {"data": BkdSister(ambil_klien(permintaan)).sinkronkan_banyak(
            permintaan.bulan, permintaan.jenis, id_periode=permintaan.id_periode, uji_coba=permintaan.uji_coba
        )}


@router.post("/unggah", summary="Unggah PDF laporan BKD dari path di server (menulis)")
def unggah_laporan(permintaan: PermintaanUnggah):
    """**Menulis** ke SIBKD. PDF baru menggantikan PDF lama untuk seluruh bulan periode itu."""
    with terjemahkan_galat():
        return BkdSister(ambil_klien(permintaan)).unggah_laporan(
            permintaan.bulan, path_masukan(permintaan.berkas),
            id_periode=permintaan.id_periode, uji_coba=permintaan.uji_coba,
        )


@router.post("/unggah/berkas", summary="Unggah PDF laporan BKD dari badan multipart (menulis)")
def unggah_laporan_multipart(
    username: str = Form(..., description="NIDN"),
    password: str = Form(...),
    bulan: str = Form(..., description="Mis. 'Oktober 2026' atau 'oktober'"),
    id_periode: str = Form(""),
    uji_coba: bool = Form(False),
    berkas: UploadFile = File(..., description="PDF laporan BKD SISTER"),
):
    """Sama dengan `/unggah`, tetapi PDF-nya dikirim pemanggil, bukan diambil dari disk server."""
    kredensial = Kredensial(username=username, password=password)
    nama = nama_berkas_aman(berkas.filename or "", "laporan.pdf")
    with tempfile.TemporaryDirectory() as ruang:
        path = Path(ruang) / nama
        path.write_bytes(berkas.file.read())
        with terjemahkan_galat():
            hasil = BkdSister(ambil_klien(kredensial)).unggah_laporan(
                bulan, path, id_periode=id_periode, uji_coba=uji_coba
            )
    # path sementara di server tidak berguna bagi pemanggil
    for isian in hasil.get("muatan", {}).values():
        if isinstance(isian, dict) and "path" in isian:
            isian["path"] = nama
    return hasil


@router.post("/tunda", summary="Jadikan status laporan satu bulan Tunda (menulis)")
def tunda_proses(permintaan: PermintaanTulis):
    """**Menulis** ke SIBKD. Laporan yang ditunda masih bisa dilanjutkan selama jadwalnya terbuka."""
    with terjemahkan_galat():
        return BkdSister(ambil_klien(permintaan)).tunda_proses(
            permintaan.bulan, id_periode=permintaan.id_periode, uji_coba=permintaan.uji_coba
        )


@router.post("/lanjut", summary="Setujui empat pernyataan dosen dan lanjut proses (menulis)")
def lanjut_proses(permintaan: PermintaanLanjut):
    """**Menulis** ke SIBKD, dan persetujuannya mengikat serta tidak bisa dibatalkan tanpa prosedur resmi.

    Pengiriman sungguhan butuh `setuju_pernyataan: true`. Jalankan dengan
    `uji_coba: true` lebih dulu: balasannya memuat teks keempat pernyataan dan
    nilai golongan/tunjangan yang akan disetujui.
    """
    with terjemahkan_galat():
        return BkdSister(ambil_klien(permintaan)).lanjut_proses(
            permintaan.bulan, setuju_pernyataan=permintaan.setuju_pernyataan,
            id_periode=permintaan.id_periode, uji_coba=permintaan.uji_coba,
        )


app = buat_app()
