"""Perintah baris perintah SIBKD.

    sibkd-status      tabel periode x bulan, status laporan, dan berkas PDF BKD
    sibkd-detail      rincian satu bulan; NIK, NPWP, No. HP, tgl lahir disamarkan
    sibkd-pengumuman  Informasi Terbaru dan daftar pengumuman
    sibkd-unduh       PDF laporan BKD satu periode, atau berkas pengumuman
    sibkd-unggah      unggah PDF laporan BKD (menulis)
    sibkd-sinkron     tarik ulang data dari SISTER/PDDIKTI (menulis)
    sibkd-tunda       jadikan status laporan Tunda (menulis)
    sibkd-lanjut      setujui empat pernyataan dan lanjut proses (menulis)

Dari klona repositori, semuanya dipanggil lewat peluncur: `./sibkd status`,
`./sibkd detail oktober`, `./sibkd unggah oktober laporan.pdf --uji-coba`.

Perintah pembacaan menerima `--json`. Perintah penulisan menerima `--uji-coba`
untuk melihat apa yang akan dikirim tanpa mengirim apa pun; jalankan itu lebih
dulu. Bulan boleh ditulis "oktober", "Oktober 2026", atau "10".

Pakai:
    sibkd-status
    sibkd-detail oktober --json
    sibkd-unduh laporan --tujuan bukti/bkd
    sibkd-lanjut oktober --uji-coba
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

from sibkd_mcp.bkd_sister import JENIS_SINKRON, BkdSister, daftar_jenis_sinkron
from sibkd_mcp.konfigurasi import KonfigurasiError, dir_data, path_dari_akar, path_masukan
from sibkd_mcp.pengumuman import PapanPengumuman
from sibkd_mcp.sibkd_client import KlienSibkd, SibkdError, galat_jaringan

BANTUAN_BULAN = "Mis. oktober, 'Oktober 2026', atau 10"
BANTUAN_PERIODE = "id_periode; kosong berarti periode aktif"


def jalankan_aman(perintah) -> int:
    """Jalankan satu perintah CLI dengan penanganan kesalahan yang seragam.

    Kesalahan pustaka dan jaringan sengaja tidak dibiarkan menjadi traceback:
    pemakai CLI butuh satu baris pesan yang bisa ditindaklanjuti.
    """
    try:
        return perintah()
    except (SibkdError, KonfigurasiError, ValueError) as galat:
        print(f"Gagal: {galat}", file=sys.stderr)
        return 1
    except requests.RequestException as galat:
        print(f"Gagal: {galat_jaringan(galat)}", file=sys.stderr)
        return 1


def cetak_json(data) -> int:
    """Keluaran untuk dipipa ke perkakas lain."""
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def pengurai(deskripsi: str, *, baca: bool = True) -> argparse.ArgumentParser:
    """Argumen yang sama untuk semua perintah: --json, dan --uji-coba untuk penulisan."""
    hasil = argparse.ArgumentParser(description=deskripsi)
    hasil.add_argument("--json", action="store_true", help="Cetak JSON, bukan teks")
    if not baca:
        hasil.add_argument("--uji-coba", action="store_true",
                           help="Tampilkan yang akan dikirim, tanpa mengirim apa pun ke SIBKD")
    return hasil


def tambah_bulan(pengurai_ini: argparse.ArgumentParser, *, wajib: bool) -> None:
    """Argumen bulan dan --periode; bulan boleh dilewati hanya pada pembacaan."""
    if wajib:
        pengurai_ini.add_argument("bulan", help=BANTUAN_BULAN)
    else:
        pengurai_ini.add_argument("bulan", nargs="?", default="", help=f"{BANTUAN_BULAN}; kosong = bulan berjalan")
    pengurai_ini.add_argument("--periode", default="", metavar="ID", help=BANTUAN_PERIODE)


def main_status() -> int:
    argumen = pengurai("Status laporan BKD SISTER v2: periode, bulan, dan berkas PDF.").parse_args()
    status = BkdSister(KlienSibkd().login()).status()
    if argumen.json:
        return cetak_json(status.sebagai_dict())

    print(f"Hari ini         : {status.tanggal_hari_ini}")
    print(f"Periode aktif    : {status.periode_aktif}")
    jadwal = f" ({status.jadwal_berjalan})" if status.jadwal_berjalan else ""
    print(f"Status pengisian : {status.status_pengisian}{jadwal}")
    if not status.periode:
        print("\nBelum ada periode pelaporan.")
        return 1
    for periode in status.periode:
        print(f"\n{periode.nama}  ({periode.rentang})  id_periode {periode.id_periode}")
        print(f"    {'Bulan':<26} {'Pengisian':<10} {'Laporan':<13} Jadwal")
        for bulan in periode.bulan:
            tanda = ">" if bulan.bulan_berjalan else " "
            print(f"  {tanda} {bulan.nama:<26} {bulan.status_pengisian:<10} {bulan.status_laporan:<13} {bulan.jadwal}")
        if periode.berkas:
            print(f"  Berkas BKD: {periode.berkas.nama}, diunggah {periode.berkas.diunggah}")
        else:
            print("  Berkas BKD: belum ada")
    print("\n> bulan berjalan")
    return 0


def main_detail() -> int:
    pengurai_ini = pengurai("Rincian satu bulan laporan BKD; data pribadi disamarkan.")
    tambah_bulan(pengurai_ini, wajib=False)
    argumen = pengurai_ini.parse_args()

    detail = BkdSister(KlienSibkd().login()).detail(argumen.bulan, argumen.periode)
    data = detail.sebagai_dict()
    if argumen.json:
        return cetak_json(data)

    print(f"{detail.nama_bulan}, {detail.periode} (id_periode {detail.id_periode}, bulan {detail.bulan})")
    jadwal = f" ({detail.jadwal})" if detail.jadwal else ""
    print(f"  Status pengisian : {detail.status_pengisian}{jadwal}")
    keterangan = f", {detail.keterangan_status}" if detail.keterangan_status else ""
    print(f"  Status laporan   : {detail.status_laporan}{keterangan}")
    print(f"  Terkunci         : {'ya, ' + detail.pesan_kunci if detail.terkunci else 'tidak'}")
    if detail.pesan_aksi:
        print(f"  Keterangan       : {detail.pesan_aksi}")
    aksi = [nama for nama, ada in detail.tombol.items() if ada]
    print(f"  Aksi di halaman  : {', '.join(aksi) if aksi else 'tidak ada'}")
    for satu in detail.informasi:
        print(f"  Informasi        : {satu}")

    if data["identitas"]:
        print("\nIdentitas dosen (NIK, NPWP, No. HP, dan tanggal lahir disamarkan)")
        identitas = data["identitas"]
        for label, kunci in (
            ("NIDN", "nidn"), ("NUPTK", "nuptk"), ("Nama", "nama"), ("No. Serdik", "no_serdik"),
            ("Perguruan tinggi", "nama_pt"), ("Prodi", "prodi"), ("Status keaktifan", "status_keaktifan"),
            ("Status kepegawaian", "status_kepegawaian"), ("No. HP", "no_hp"), ("NPWP", "npwp"),
            ("NIK KTP", "nik_ktp"), ("Tgl lahir", "tgl_lahir"),
        ):
            print(f"  {label:<20}: {identitas[kunci]}")
    if data["golongan"]:
        print("\nGolongan penyetaraan")
        for satu in data["golongan"]["rincian"]:
            print(f"  {satu['label'][:44]:<44}: {satu['nilai']}")
    if detail.berkas:
        print(f"\nBerkas laporan: {detail.berkas.nama}, diunggah {detail.berkas.diunggah}")
    elif detail.unggah.get("tersedia"):
        print("\nBerkas laporan: belum ada")
    return 0


def main_pengumuman() -> int:
    argumen = pengurai("Informasi Terbaru di beranda SIBKD dan daftar pengumuman.").parse_args()
    papan = PapanPengumuman(KlienSibkd().login())
    informasi = papan.informasi_terbaru()
    daftar = papan.daftar()
    if argumen.json:
        return cetak_json({
            "informasi_terbaru": informasi.sebagai_dict() if informasi else None,
            "pengumuman": [satu.sebagai_dict() for satu in daftar],
        })
    if informasi:
        print(f"Informasi terbaru: {informasi.judul}")
        for baris in informasi.isi.splitlines():
            print(f"  {baris}")
        print()
    print(f"Pengumuman ({len(daftar)}):")
    for satu in daftar:
        print(f"  {satu.nomor:>3}. {satu.tanggal or satu.tanggal_teks:<10}  {satu.judul}  [{satu.nama_berkas}]")
    return 0


def main_unduh() -> int:
    pengurai_ini = pengurai("Unduh PDF laporan BKD satu periode, atau berkas pengumuman.")
    pengurai_ini.add_argument("jenis", choices=["laporan", "pengumuman"], help="Berkas yang diunduh")
    pengurai_ini.add_argument("--periode", default="", metavar="ID", help=f"Untuk laporan: {BANTUAN_PERIODE}")
    pengurai_ini.add_argument("--cari", default="", help="Untuk pengumuman: saring judul atau nama berkas")
    pengurai_ini.add_argument("--tujuan", default="",
                              help="Folder penyimpanan; bawaannya data/laporan_bkd atau data/pengumuman")
    pengurai_ini.add_argument("--timpa", action="store_true", help="Unduh ulang berkas yang sudah ada")
    argumen = pengurai_ini.parse_args()

    klien = KlienSibkd().login()
    if argumen.jenis == "laporan":
        tujuan = path_dari_akar(argumen.tujuan) if argumen.tujuan else dir_data() / "laporan_bkd"
        hasil = BkdSister(klien).unduh_laporan(tujuan, id_periode=argumen.periode, timpa=argumen.timpa)
    else:
        tujuan = path_dari_akar(argumen.tujuan) if argumen.tujuan else dir_data() / "pengumuman"
        hasil = PapanPengumuman(klien).unduh(tujuan, cari=argumen.cari, timpa=argumen.timpa)
    if argumen.json:
        return cetak_json(hasil)

    print(f"Tujuan: {hasil['tujuan']}")
    for satu in hasil["berkas"]:
        print(f"  diunduh   {Path(satu).name}  ({Path(satu).stat().st_size // 1024} KB)")
    for satu in hasil["dilewati"]:
        print(f"  sudah ada {Path(satu).name}  (pakai --timpa untuk mengunduh ulang)")
    for satu in hasil["gagal"]:
        print(f"  GAGAL     {satu['judul']}: {satu['pesan']}")
    if hasil.get("pesan"):
        print(f"  {hasil['pesan']}")
    return 1 if hasil["gagal"] else 0


def cetak_hasil_tulis(hasil: dict) -> None:
    """Ringkasan satu aksi tulis: alamat, muatan, hambatan, dan balasan SIBKD."""
    awalan = "[uji coba] " if hasil["uji_coba"] else ""
    print(f"{awalan}{hasil['aksi']}: {hasil['bulan']}, {hasil['periode']} (id_periode {hasil['id_periode']})")
    print(f"  {hasil['metode']} {hasil['url']}")
    if hasil["muatan"]:
        print(f"  muatan     : {json.dumps(hasil['muatan'], ensure_ascii=False)}")
    for satu in hasil["hambatan"]:
        print(f"  hambatan   : {satu}")
    for satu in hasil["peringatan"]:
        print(f"  peringatan : {satu}")
    if hasil.get("ringkasan_persetujuan"):
        print("  Nilai yang disetujui:")
        for satu in hasil["ringkasan_persetujuan"]:
            print(f"    {satu['label']}: {satu['nilai']}")
    if hasil.get("pernyataan"):
        print("  Dengan ini saya menyatakan bahwa:")
        for nomor, satu in enumerate(hasil["pernyataan"], start=1):
            print(f"    {nomor}. {satu['teks']}")
    tanda = "terkirim" if hasil["terkirim"] else "tidak dikirim"
    print(f"  [{tanda}] {hasil.get('pesan', '')}")


def selesai_tulis(hasil: dict | list[dict], json_saja: bool) -> int:
    """Cetak hasil satu atau beberapa aksi tulis; kode keluar 1 kalau ada yang tidak OK."""
    semua = hasil if isinstance(hasil, list) else [hasil]
    if json_saja:
        cetak_json(hasil)
    else:
        for satu in semua:
            cetak_hasil_tulis(satu)
    return 0 if all(satu["ok"] for satu in semua) else 1


def main_unggah() -> int:
    pengurai_ini = pengurai("Unggah PDF laporan BKD SISTER untuk satu bulan (MENULIS ke SIBKD).", baca=False)
    tambah_bulan(pengurai_ini, wajib=True)
    pengurai_ini.add_argument("berkas", help="Path PDF laporan; relatif dari direktori kerja, lalu akar proyek")
    argumen = pengurai_ini.parse_args()
    hasil = BkdSister(KlienSibkd().login()).unggah_laporan(
        argumen.bulan, path_masukan(argumen.berkas), id_periode=argumen.periode, uji_coba=argumen.uji_coba
    )
    return selesai_tulis(hasil, argumen.json)


def main_sinkron() -> int:
    pengurai_ini = pengurai("Tarik ulang data dari SISTER/PDDIKTI ke laporan satu bulan (MENULIS ke SIBKD).",
                            baca=False)
    tambah_bulan(pengurai_ini, wajib=True)
    pengurai_ini.add_argument("jenis", help=f"{', '.join(JENIS_SINKRON)}; boleh dipisah koma, atau 'semua'")
    argumen = pengurai_ini.parse_args()
    daftar_jenis_sinkron(argumen.jenis)  # tolak jenis yang salah sebelum login
    hasil = BkdSister(KlienSibkd().login()).sinkronkan_banyak(
        argumen.bulan, argumen.jenis, id_periode=argumen.periode, uji_coba=argumen.uji_coba
    )
    return selesai_tulis(hasil, argumen.json)


def main_tunda() -> int:
    pengurai_ini = pengurai("Jadikan status laporan satu bulan Tunda (MENULIS ke SIBKD).", baca=False)
    tambah_bulan(pengurai_ini, wajib=True)
    argumen = pengurai_ini.parse_args()
    hasil = BkdSister(KlienSibkd().login()).tunda_proses(
        argumen.bulan, id_periode=argumen.periode, uji_coba=argumen.uji_coba
    )
    return selesai_tulis(hasil, argumen.json)


def main_lanjut() -> int:
    pengurai_ini = pengurai(
        "Setujui empat pernyataan dosen dan lanjut proses laporan satu bulan (MENULIS ke SIBKD). "
        "Persetujuan ini mengikat dan tidak bisa dibatalkan tanpa prosedur resmi.",
        baca=False,
    )
    tambah_bulan(pengurai_ini, wajib=True)
    pengurai_ini.add_argument("--setuju", action="store_true",
                              help="Saya sudah membaca dan menyetujui keempat pernyataan (wajib untuk mengirim)")
    argumen = pengurai_ini.parse_args()
    hasil = BkdSister(KlienSibkd().login()).lanjut_proses(
        argumen.bulan, setuju_pernyataan=argumen.setuju, id_periode=argumen.periode, uji_coba=argumen.uji_coba
    )
    return selesai_tulis(hasil, argumen.json)


def jalankan_status() -> int:
    """Titik masuk perintah `sibkd-status`."""
    return jalankan_aman(main_status)


def jalankan_detail() -> int:
    """Titik masuk perintah `sibkd-detail`."""
    return jalankan_aman(main_detail)


def jalankan_pengumuman() -> int:
    """Titik masuk perintah `sibkd-pengumuman`."""
    return jalankan_aman(main_pengumuman)


def jalankan_unduh() -> int:
    """Titik masuk perintah `sibkd-unduh`."""
    return jalankan_aman(main_unduh)


def jalankan_unggah() -> int:
    """Titik masuk perintah `sibkd-unggah`."""
    return jalankan_aman(main_unggah)


def jalankan_sinkron() -> int:
    """Titik masuk perintah `sibkd-sinkron`."""
    return jalankan_aman(main_sinkron)


def jalankan_tunda() -> int:
    """Titik masuk perintah `sibkd-tunda`."""
    return jalankan_aman(main_tunda)


def jalankan_lanjut() -> int:
    """Titik masuk perintah `sibkd-lanjut`."""
    return jalankan_aman(main_lanjut)


if __name__ == "__main__":
    sys.exit(jalankan_status())
