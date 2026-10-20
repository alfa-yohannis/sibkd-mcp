"""SIBKD MCP: pantau dan kelola laporan BKD SISTER v2 di SIBKD LLDIKTI III.

Tiga cara memakainya, semuanya dari paket yang sama:

    pustaka   from sibkd_mcp import KlienSibkd, BkdSister
              klien = KlienSibkd("0000000000", "sandi").login()
              status = BkdSister(klien).status()
              for bulan in status.periode_berjalan().bulan:
                  print(bulan.nama, bulan.status_pengisian, bulan.status_laporan)

    REST API  from sibkd_mcp.api import router
              app_saya.include_router(router, prefix="/sibkd")

    MCP       from sibkd_mcp.mcp_server import server
              server.run()                       # atau lewat perintah `sibkd-mcp`

Dua bagian SIBKD tersedia, semuanya berangkat dari satu `KlienSibkd`:

    BkdSister          tabel periode x bulan, detail satu bulan, unduh PDF,
                       serta unggah, sinkron, tunda, dan lanjut proses
    PapanPengumuman    Informasi Terbaru di beranda dan daftar pengumuman

Setelan bisa diberikan tanpa berkas apa pun:

    from sibkd_mcp import atur_setelan
    atur_setelan(SIBKD_USERNAME="0000000000", SIBKD_PASSWORD="sandi")

Impor di sini sengaja hanya menyentuh modul inti. `sibkd_mcp.api` butuh FastAPI
dan `sibkd_mcp.mcp_server` butuh paket mcp, jadi keduanya diimpor sendiri oleh
yang memerlukan; pemakai pustaka tidak dipaksa memasang keduanya.
"""

from __future__ import annotations

from sibkd_mcp.bkd_sister import (
    JENIS_SINKRON,
    BkdSister,
    BulanLaporan,
    BulanTidakDitemukan,
    PeriodeLaporan,
    StatusPelaporan,
)
from sibkd_mcp.bulan import urai_bulan
from sibkd_mcp.detail_laporan import BerkasBkd, DetailLaporan, GolonganPenyetaraan, IdentitasDosen
from sibkd_mcp.konfigurasi import (
    KonfigurasiError,
    akar_proyek,
    atur_akar_proyek,
    atur_setelan,
    baca_pengaturan,
)
from sibkd_mcp.pengumuman import InformasiTerbaru, PapanPengumuman, Pengumuman
from sibkd_mcp.privasi import samarkan
from sibkd_mcp.rantai_tls import buat_konteks_tls
from sibkd_mcp.sibkd_client import KlienSibkd, SibkdError

__version__ = "1.0.0"

__all__ = [
    # sesi
    "KlienSibkd",
    # BKD SISTER v2
    "BkdSister",
    "StatusPelaporan",
    "PeriodeLaporan",
    "BulanLaporan",
    "BerkasBkd",
    "DetailLaporan",
    "IdentitasDosen",
    "GolonganPenyetaraan",
    "JENIS_SINKRON",
    # pengumuman
    "PapanPengumuman",
    "Pengumuman",
    "InformasiTerbaru",
    # alat bantu
    "urai_bulan",
    "samarkan",
    "buat_konteks_tls",
    # setelan
    "atur_setelan",
    "atur_akar_proyek",
    "baca_pengaturan",
    "akar_proyek",
    # kesalahan
    "SibkdError",
    "BulanTidakDitemukan",
    "KonfigurasiError",
    "__version__",
]
