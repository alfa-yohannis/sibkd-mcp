"""Perkakas bersama untuk unit test SIBKD.

Seluruh test berjalan tanpa jaringan: SIBKD digantikan halaman HTML tiruan dan
klien tiruan, sehingga bisa dijalankan kapan saja tanpa kredensial. Struktur
halamannya meniru SIBKD (kelas CSS, id tombol, variabel JavaScript), tetapi
nama, NIDN, NIK, NPWP, nomor HP, tanggal lahir, dan nominalnya dikarang.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pytest

AKAR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AKAR))

from sibkd_mcp import konfigurasi  # noqa: E402
from sibkd_mcp.sibkd_client import SibkdError  # noqa: E402

BASE = "https://sibkd-lldikti3.kemdiktisaintek.go.id"
NIDN = "0000000000"
BERKAS_URL = f"{BASE}/assets/laporan_bkd_sister/{NIDN}/File20261002075709{NIDN}.pdf"

# data pribadi karangan; dipakai untuk memastikan penyamarannya bekerja
NIK = "3210000000001234"
NPWP = "000000000005678"
NO_HP = "081200009876"
TGL_LAHIR = "1990-01-31"


def kartu_bulan(id_periode: str, slug: str, nama: str, *, jadwal: str = "Jadwal belum diatur",
                pengisian: str = "Tutup", titik: str = "", laporan: str = "Belum dibuat",
                berjalan: bool = False) -> str:
    kelas = "bkd-month-card is-current" if berjalan else "bkd-month-card"
    return f"""
    <td>
      <a href="{BASE}/dosen/bkdsister_v2/detail/{id_periode}/{slug}" class="{kelas}" title="{jadwal}">
        <div class="bkd-month-name">{nama}</div>
        <div class="bkd-status-badge">{pengisian}</div>
        <div class="bkd-validation">
          <span class="bkd-dot {titik}"></span>
          <span>{laporan}</span>
        </div>
      </a>
    </td>"""


HALAMAN_STATUS = f"""<!DOCTYPE html><html><body>
<aside class="left-sidebar"><nav class="sidebar-nav"><ul id="sidebarnav">
  <li><a href="javascript:void(0)" class="chatonline"><span>KING KONG<br><small>online</small></span></a></li>
  <li><a href="{BASE}/usulan"><span class="hide-menu">Beranda</span></a></li>
  <!-- <li><a href="{BASE}/dosen/bkdsister">Upload BKD SISTER</a></li> -->
  <li><a href="{BASE}/dosen/bkdsister_v2">BKD SISTER v2</a></li>
  <li><a href="{BASE}/usulan/usulan/logout">Keluar</a></li>
</ul></nav></aside>
<div class="bkd-upload-page">
  <div class="bkd-summary-grid">
    <div class="bkd-summary-card"><div>
      <p class="bkd-summary-label">Tanggal Hari Ini</p>
      <p class="bkd-summary-value">20 Oktober 2026</p></div></div>
    <div class="bkd-summary-card is-green"><div>
      <p class="bkd-summary-label">Status Pengisian</p>
      <p class="bkd-summary-value">Buka</p>
      <p class="bkd-summary-note">2 Oktober 2026 - 24 Oktober 2026</p></div></div>
    <div class="bkd-summary-card is-purple"><div>
      <p class="bkd-summary-label">Periode Pelaporan Aktif</p>
      <p class="bkd-summary-value">Genap 2025/2026</p></div></div>
  </div>
  <table class="bkd-table">
    <thead><tr><th>Periode</th><th>Bulan 1</th><th>Bulan 2</th><th>Bulan 3</th><th>Bulan 4</th>
      <th>Bulan 5</th><th>File BKD Sister</th></tr></thead>
    <tbody>
      <tr>
        <td class="bkd-period"><p class="bkd-period-title">GASAL 2025/2026</p>
          <p class="bkd-period-range">September 2025 - Februari 2026</p></td>
        {kartu_bulan("19", "maret", "Maret 2026")}
        {kartu_bulan("19", "april", "April 2026")}
        <td class="bkd-file-cell"><div class="bkd-file-card">Belum ada file</div></td>
      </tr>
      <tr>
        <td class="bkd-period"><p class="bkd-period-title">GENAP 2025/2026</p>
          <p class="bkd-period-range">Maret 2026 - Agustus 2026</p></td>
        {kartu_bulan("20", "september", "September 2026", jadwal="1 September 2026 - 29 September 2026",
                     titik="tunda", laporan="Tunda")}
        {kartu_bulan("20", "oktober", "Oktober 2026", jadwal="2 Oktober 2026 - 24 Oktober 2026",
                     pengisian="Buka", titik="draft", laporan="Draft", berjalan=True)}
        {kartu_bulan("20", "november", "November - Desember 2026")}
        {kartu_bulan("20", "januari", "Januari 2027")}
        {kartu_bulan("20", "februari", "Februari 2027")}
        <td class="bkd-file-cell">
          <div class="bkd-file-card has-file">
            <a href="{BERKAS_URL}" target="_blank"><i class="fa fa-external-link"> [Lihat File]</i></a>
            <p class="bkd-file-date">Diupload: 2026-10-02 07:57:09</p>
          </div>
        </td>
      </tr>
    </tbody>
  </table>
  <div class="bkd-info"><span class="bkd-info-icon">i</span>
    <span>Jadwal bulan berjalan: 2 Oktober 2026 - 24 Oktober 2026.</span></div>
</div>
</body></html>"""


def halaman_detail(*, bulan: str = "oktober", nama_bulan: str = "Oktober 2026", pengisian: str = "Buka",
                   jadwal: str = "2 Oktober 2026 - 24 Oktober 2026", laporan: str = "Draft",
                   kelas_laporan: str = "is-draft", catatan: str = "Laporan masih draft",
                   terkunci: bool = False, kunci_dalam_komentar: bool = False, dibuat: bool = True,
                   berkas: bool = True, gol: str = "10", tgl_acuan: str = "2026-10-01") -> str:
    """Halaman detail tiruan; variasinya diatur lewat argumen."""
    terbuka = pengisian == "Buka"
    pil_pengisian = "is-success" if terbuka else "is-danger"
    sinkron_identitas = (
        '<button id="sinkron_profil_sister">Sinkron Identitas</button>'
        '<button id="sinkron_homebase_sister">Sinkron Homebase</button>'
        '<button id="sinkron_rwy_pend_sister">Sinkron Pendidikan</button>'
    ) if terbuka else ""
    sinkron_golongan = (
        '<button id="sinkron_jafung_tambah">Sinkron Jafung</button>'
        '<button id="sinkron_golongan_sister">Sinkron Pangkat</button>'
    ) if terbuka else ""
    if terbuka:
        aksi = ('<div class="bkd-detail-actions">'
                '<button id="btn-tunda-proses" class="bkd-btn-tunda">Tunda Proses</button>'
                '<button id="btn-lanjut-proses" class="bkd-btn-lanjut">Lanjut Proses</button></div>')
    else:
        aksi = ('<div class="bkd-detail-actions"><div class="bkd-alert"><i class="fa fa-info-circle"></i>'
                'Pelaporan BKD untuk bulan ini ditutup.</div></div>')
    penggabungan = (
        '<div class="alert alert-info"><strong>Informasi Penggabungan Pelaporan:</strong> Pelaporan BKD '
        'untuk bulan <strong>November 2026</strong> dan <strong>Desember 2026</strong> digabung.</div>'
        if bulan == "november" else ""
    )
    berkas_html = (
        f"""<div class="bkd-upload-current"><div>
              <div class="bkd-upload-current-label">File yang sudah diupload:</div>
              <a href="{BERKAS_URL}" target="_blank"><i class="fa fa-external-link"></i>
                File20261002075709{NIDN}.pdf</a>
              (2026-10-02 07:57:09)</div></div>"""
        if berkas else ""
    )
    isi = ""
    if dibuat:
        isi = f"""
    <div class="bkd-section">
      <div class="bkd-section-header"><i class="fa fa-user-o"></i><span>Identitas Dosen</span></div>
      <div class="bkd-section-body">
        {sinkron_identitas}
        <div class="bkd-info-grid">
          <div><label class="bkd-field-label">NIDN/NUPTK</label><div class="bkd-field-box">{NIDN} / 1111222233334444</div></div>
          <div><label class="bkd-field-label">Nama</label><div class="bkd-field-box">KING KONG</div></div>
          <div><label class="bkd-field-label">No. Serdik</label><div class="bkd-field-box">111111111111111</div></div>
          <div><label class="bkd-field-label">Nama PT</label><div class="bkd-field-box">Universitas Karangan</div></div>
          <div><label class="bkd-field-label">Prodi</label><div class="bkd-field-box">Informatika</div></div>
          <div><label class="bkd-field-label">Status Keaktifan</label><div class="bkd-field-box">Aktif</div></div>
          <div><label class="bkd-field-label">No. HP</label><div class="bkd-field-box">{NO_HP}</div></div>
          <div><label class="bkd-field-label">NPWP</label><div class="bkd-field-box">{NPWP} </div></div>
          <div><label class="bkd-field-label">NIK KTP</label><div class="bkd-field-box">{NIK}</div></div>
          <div><label class="bkd-field-label">Tgl Lahir</label><div class="bkd-field-box">{TGL_LAHIR}</div></div>
          <div><label class="bkd-field-label">Status Kepegawaian</label><div class="bkd-field-box">
            NON ASN       </div></div>
        </div>
      </div>
    </div>
    <div class="bkd-section">
      <div class="bkd-section-header"><i class="fa fa-money"></i><span>Golongan Penyetaraan</span></div>
      <div class="bkd-section-body"><div class="bkd-form-grid">
        {sinkron_golongan}
        <input type="hidden" name="jabatan_no_awal" value="41">
        <input type="hidden" name="tmt_jabatan_awal" value="2020-01-01">
        <input class="form-control" type="hidden" name="gol_penyetaraan" value="{gol}">
        <div style="padding: 16px">
          <div class="form-group row"><label class="col-3">JAD Awal</label>
            <div class="col-9"><input class="form-control" readonly type="text" value="Asisten Ahli (150), 2020-01-01"></div></div>
          <div class="form-group row"><label class="col-3">JAD Terakhir</label>
            <div class="col-9"><input class="form-control" readonly type="text" value="Lektor (200), 2024-04-01"></div></div>
          <div class="form-group row"><label class="col-3">JAD KUM Terkecil</label>
            <div class="col-9"><input class="form-control" readonly type="text" value="Asisten Ahli (150), 2020-01-01"></div></div>
          <div class="form-group row"><label class="col-3">Tanggal Acuan</label>
            <div class="col-9"><input class="form-control" type="text" value="{tgl_acuan}" readonly></div></div>
          <div class="form-group row"><label class="col-3">Pangkat/Golongan Penyetaraan</label>
            <div class="col-9"><input class="form-control" type="text" value="Penata (III/c)" readonly></div></div>
          <div class="form-group row"><label class="col-3">Masa kerja Pangkat/Golongan Penyetaraan</label>
            <div class="col-1"><input class="form-control" type="text" name="thn_masa_kerja_penyetaraan" value="6" readonly> Tahun</div>
            <div class="col-1"><input class="form-control" type="text" name="bln_masa_kerja_penyetaraan" value="9" readonly> Bulan</div></div>
          <div class="form-group row"><label class="col-3">Penyetaraan Pembayaran Tunjangan Sertifikasi</label>
            <div class="col-9"><div class="nominal-sensor-wrap">
              <input class="form-control nominal-sensor-input" type="text" value="Rp. **********"
                     data-real="Rp. 1.234.500" data-masked="Rp. **********" data-masked-state="true" readonly>
              <button type="button" class="btn-toggle-sensor">Lihat</button></div></div></div>
        </div>
      </div></div>
    </div>
    <div class="bkd-section"><div class="bkd-section-body">
      <form id="uploadLaporanBkdSisterForm" enctype="multipart/form-data">
        <input type="hidden" name="id_periode" value="20">
        <input type="hidden" name="bln" value="{bulan}">
        <input type="file" name="berkas" id="bkdFileInput" accept="application/pdf" style="display: none;">
        <p class="bkd-upload-limit">Ukuran maks. 5 MB per file</p>
        {berkas_html}
      </form>
    </div></div>
    <div class="bkd-modal-overlay" id="modalCeklistOverlay"><div class="bkd-modal-box">
      <div class="bkd-modal-info-bar">
        <div class="bkd-modal-info-item"><span class="bkd-modal-info-label">Nama Dosen</span>
          <span class="bkd-modal-info-val">KING KONG</span></div>
        <div class="bkd-modal-info-item"><span class="bkd-modal-info-label">NIDN</span>
          <span class="bkd-modal-info-val">{NIDN}</span></div>
        <div class="bkd-modal-info-item"><span class="bkd-modal-info-label">Bulan Laporan</span>
          <span class="bkd-modal-info-val">{nama_bulan}</span></div>
        <div class="bkd-modal-info-item"><span class="bkd-modal-info-label">Pangkat/Gol. Penyetaraan</span>
          <span class="bkd-modal-info-val">Penata (III/c)</span></div>
        <div class="bkd-modal-info-item"><span class="bkd-modal-info-label">Masa Kerja Penyetaraan</span>
          <span class="bkd-modal-info-val">6 Thn 9 Bln</span></div>
        <div class="bkd-modal-info-item"><span class="bkd-modal-info-label">No. HP</span>
          <span class="bkd-modal-info-val">{NO_HP}</span></div>
        <div class="bkd-modal-info-item"><span class="bkd-modal-info-label">Penyetaraan Pembayaran Tunjangan Sertifikasi</span>
          <span class="bkd-modal-info-val">Rp. 1.234.500</span></div>
      </div>
      <p class="bkd-modal-intro">Dengan ini saya menyatakan bahwa:</p>
      <div class="bkd-ceklist-list">
        <label class="bkd-ceklist-item" for="ck1"><input type="checkbox" id="ck1" class="bkd-ck-input">
          <span class="bkd-ck-text">Data profil dosen adalah <strong>benar dan sesuai</strong>.</span></label>
        <label class="bkd-ceklist-item" for="ck3"><input type="checkbox" id="ck3" class="bkd-ck-input">
          <span class="bkd-ck-text">Data jabatan fungsional dan golongan penyetaraan <strong>akurat</strong>.</span></label>
        <label class="bkd-ceklist-item" for="ck4"><input type="checkbox" id="ck4" class="bkd-ck-input">
          <span class="bkd-ck-text">File laporan yang diupload adalah <strong>dokumen resmi dan sah</strong>.</span></label>
        <label class="bkd-ceklist-item" for="ck5"><input type="checkbox" id="ck5" class="bkd-ck-input">
          <span class="bkd-ck-text">Persetujuan ini <strong>mengikat secara administratif</strong>.</span></label>
      </div>
    </div></div>"""

    kunci = ("$('#sinkron_rwy_pend_sister, #sinkron_profil_sister')\n"
             "    .prop('disabled', true)\n    .attr('title', 'Laporan telah dikunci oleh Admin PT');")
    if kunci_dalam_komentar:
        kunci = f"/* {kunci} */"
    elif not terkunci:
        kunci = ""
    return f"""<!DOCTYPE html><html><body>
<div class="bkd-detail-page">
  <a href="{BASE}/dosen/bkdsister_v2" class="btn btn-info mb-3">Kembali</a>
  {penggabungan}
  <div class="bkd-detail-summary">
    <div class="bkd-detail-card is-blue"><div>
      <p class="bkd-detail-label">Periode Pelaporan</p>
      <p class="bkd-detail-value">GENAP 2025/2026</p></div></div>
    <div class="bkd-detail-card is-blue"><div>
      <p class="bkd-detail-label">Bulan Pengisian</p>
      <p class="bkd-detail-value">{nama_bulan}</p>
      <p class="bkd-detail-note">Status pengisian: <span class="bkd-status-pill {pil_pengisian}"> {pengisian} </span></p>
      <p><span class="bkd-detail-label">{jadwal}</span></p></div></div>
    <div class="bkd-detail-card is-yellow"><div>
      <p class="bkd-detail-label">Status Laporan</p>
      <p class="bkd-detail-value"><span class="bkd-status-pill {kelas_laporan}">{laporan}</span></p>
      <p class="bkd-detail-note">{catatan}</p></div></div>
  </div>
  {aksi}
  {isi}
</div>
<script>
  $(document).ready(function() {{
    var id_periode = "20";
    var bln = "{bulan}";
    var apiurl = "{BASE}/dosen/bkdsister_v2/update_rwy_pend_sister" + id_periode + "/" + bln;
  }});
</script>
<script>
  $(document).ready(function() {{
    {kunci}
    var gol_penyetaraan = "{gol}";
    var thn_masa_kerja_penyetaraan = "6";
    var bln_masa_kerja_penyetaraan = "9";
    var tgl_acuan = "{tgl_acuan}";
    var id_periode = "20";
    var bln = "{bulan}";
  }});
</script>
</body></html>"""


BERANDA = f"""<!DOCTYPE html><html><body>
<header><a class="nav-link profile-pic"><img src="u.png"> <span class="hidden-md-down">KING KONG &nbsp;<i></i></span></a></header>
<ul id="sidebarnav">
  <li><a href="{BASE}/usulan">Beranda</a></li>
  <li><a href="{BASE}/dosen/bkdsister_v2">BKD SISTER v2</a></li>
  <li><a href="{BASE}/usulan/usulan/logout">Keluar</a></li>
</ul>
<div class="row"><div class="col-12">
  <!-- <div class="card"><div class="card-body">Selamat Datang <b>KING KONG</b></div></div> -->
  <div class="card"><div class="card-body">
    Informasi Terbaru: <br><b class='text-danger'>SIBKD V2</b><br>Pelaporan SIBKD V2 PERIODE LAPOR OKTOBER 2026
Bagi Dosen
1. Unggah LKD lalu klik Lanjut Proses.
2. Periksa nominal penyetaraan.        <!-- nidn = 0000000000 -->
  </div></div>
  <div class="card"><div class="card-body">
    <a href="{BASE}/assets/pengumuman/Contoh.pdf">Contoh.pdf</a>
    <a href="{BASE}/all_pengumuman">Lihat lebih banyak pengumuman ...</a>
  </div></div>
</div></div>
</body></html>"""

ALL_PENGUMUMAN = f"""<!DOCTYPE html><html><body>
<table class="table nowarp table-striped table-bordered allpengumuman">
  <thead><tr><th>No.</th><th>Pengumuman</th><th>File Pengumuman</th><th>Tanggal <br>Pengumuman</th></tr></thead>
  <tbody>
    <tr><td class="text-center">1</td><td>Daftar Penerima Tunjangan Sertifikasi Dosen Periode Agustus 2025</td>
      <td class="text-center"><a href="{BASE}/assets/pengumuman/Pencairan_Agustus_2025.pdf" target="_blank">Pencairan_Agustus_2025.pdf</a></td>
      <td class="text-center"> 7 August 2025</td></tr>
    <tr><td class="text-center">2</td><td>REKONSILIASI DATA REKAP SIBKD GASAL 24/25</td>
      <td class="text-center"><a href="{BASE}/assets/pengumuman/HASIL_REKONSILIASI.pdf" target="_blank">HASIL_REKONSILIASI.pdf</a></td>
      <td class="text-center">10 June 2025</td></tr>
  </tbody>
</table>
</body></html>"""

HALAMAN_LOGIN = f"""<!DOCTYPE html><html><body>
<form method="post" action="{BASE}/login/login">
  <input class="form-control" type="text" name="username" placeholder="Username">
  <input class="form-control" type="password" name="password" placeholder="Password">
  <button type="submit">Masuk</button>
</form></body></html>"""

# PDF terkecil yang masih dikenali dari tanda tangannya
PDF_TIRUAN = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


class JawabanTiruan:
    """Pengganti requests.Response seperlunya saja."""

    def __init__(self, teks: str = "", url: str = "", status_code: int = 200, isi_json=None,
                 headers: dict | None = None, isi: bytes = b""):
        self.text = teks
        self.url = url
        self.status_code = status_code
        self._json = isi_json
        self.headers = headers or {}
        self.content = isi or teks.encode()
        self.history = []

    def json(self):
        if self._json is None:
            raise ValueError("bukan JSON")
        return self._json

    def iter_content(self, chunk_size=1):
        yield self.content

    def __enter__(self):
        return self

    def __exit__(self, *galat):
        return False


class KlienTiruan:
    """Pengganti KlienSibkd: halaman diambil dari kamus, kiriman direkam, tanpa jaringan."""

    def __init__(self, halaman: dict[str, str] | None = None, balasan_kirim: dict | None = None):
        self.base_url = BASE
        self.url_beranda = f"{BASE}/usulan/usulan"
        self.nama = "KING KONG"
        self.halaman = halaman if halaman is not None else halaman_bawaan()
        self.balasan_kirim = balasan_kirim or {
            "ok": True, "status": "success", "pesan": "Berhasil", "status_http": 200,
        }
        self.terkirim: list[dict] = []
        self.diunduh: list[tuple[str, Path]] = []

    def login(self):
        return self

    def url(self, path_atau_url: str) -> str:
        if path_atau_url.startswith(("http://", "https://")):
            return path_atau_url
        return urljoin(f"{BASE}/", path_atau_url.lstrip("/"))

    def ambil_halaman(self, path_atau_url: str):
        url = self.url(path_atau_url)
        path = urlparse(url).path
        if path not in self.halaman:
            raise SibkdError(f"Halaman tiruan tidak ada: {path}")
        return JawabanTiruan(teks=self.halaman[path], url=url)

    def kirim(self, path_atau_url: str, *, data=None, files=None, referer: str = "") -> dict:
        self.terkirim.append({"url": self.url(path_atau_url), "data": data, "files": files, "referer": referer})
        return dict(self.balasan_kirim)

    def unduh(self, url: str, tujuan: Path, *, timpa: bool = False):
        tujuan = Path(tujuan)
        self.diunduh.append((url, tujuan))
        if tujuan.exists() and not timpa:
            return tujuan, False
        tujuan.parent.mkdir(parents=True, exist_ok=True)
        tujuan.write_bytes(PDF_TIRUAN)
        return tujuan, True

    def daftar_navigasi(self) -> list[dict]:
        return [{"nama": "Beranda", "url": f"{BASE}/usulan"}, {"nama": "BKD SISTER v2", "url": f"{BASE}/dosen/bkdsister_v2"}]


def halaman_bawaan() -> dict[str, str]:
    """Kamus path -> HTML untuk satu dosen dengan bulan Oktober sedang dibuka."""
    return {
        "/dosen/bkdsister_v2": HALAMAN_STATUS,
        "/dosen/bkdsister_v2/detail/20/september": halaman_detail(
            bulan="september", nama_bulan="September 2026", pengisian="Tutup",
            jadwal="1 September 2026 - 29 September 2026", laporan="Tunda", kelas_laporan="is-tunda",
            catatan="Laporan dalam status Tunda", terkunci=True, tgl_acuan="2026-09-01",
        ),
        "/dosen/bkdsister_v2/detail/20/oktober": halaman_detail(),
        "/dosen/bkdsister_v2/detail/20/november": halaman_detail(
            bulan="november", nama_bulan="November - Desember 2026", pengisian="Tutup",
            jadwal="Jadwal belum diatur", laporan="Belum dibuat", kelas_laporan="is-empty",
            catatan="Laporan belum dibuat", dibuat=False, gol="0", tgl_acuan="2026-11-01",
        ),
        "/usulan": BERANDA,
        "/usulan/usulan": BERANDA,
        "/all_pengumuman": ALL_PENGUMUMAN,
    }


@pytest.fixture(autouse=True)
def tanpa_setelan_mesin(tmp_path, monkeypatch):
    """Setelan dan .env mesin pengembang tidak boleh ikut menentukan hasil uji."""
    for kunci in list(os.environ):
        if kunci.startswith("SIBKD_") or kunci == "BKD_AKAR_PROYEK":
            monkeypatch.delenv(kunci, raising=False)
    konfigurasi.atur_akar_proyek(tmp_path / "akar")
    konfigurasi.atur_setelan()
    yield
    konfigurasi.atur_akar_proyek(None)
    konfigurasi.atur_setelan()
    konfigurasi.lupakan_konfigurasi()


@pytest.fixture
def klien() -> KlienTiruan:
    return KlienTiruan()


@pytest.fixture
def pdf(tmp_path) -> Path:
    berkas = tmp_path / "laporan.pdf"
    berkas.write_bytes(PDF_TIRUAN)
    return berkas
