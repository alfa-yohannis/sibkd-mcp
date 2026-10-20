"""MCP server SIBKD LLDIKTI III.

Membuka kemampuan yang sama dengan api.py lewat protokol MCP, sehingga asisten AI
bisa memantau laporan BKD SISTER v2 bulanan: status tiap bulan, rincian
golongan penyetaraan dan tunjangan, pengumuman, serta PDF laporan. Empat tool
menulis ke SIBKD dan semuanya menerima `uji_coba`.

Kredensial boleh dikirim per pemanggilan, atau dibiarkan kosong supaya jatuh ke
SIBKD_USERNAME / SIBKD_PASSWORD di berkas .env.

Daftarkan ke Claude Code (perintah `sibkd-mcp` ikut terpasang bersama paketnya):
    claude mcp add sibkd-mcp -- sibkd-mcp
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from sibkd_mcp import __version__
from sibkd_mcp.bkd_sister import JENIS_SINKRON, BkdSister, BulanTidakDitemukan, daftar_jenis_sinkron
from sibkd_mcp.konfigurasi import baca_pengaturan, dir_data, path_dari_akar, path_masukan
from sibkd_mcp.pengumuman import PapanPengumuman
from sibkd_mcp.sibkd_client import KlienSibkd, SibkdError, alamat_sibkd

# instruksi menyebut instansi dan alamatnya supaya asisten tahu sistem mana yang
# sedang dipakai; keduanya ikut setelan, bukan ditanam di teks
NAMA_INSTANSI = baca_pengaturan("SIBKD_NAMA_INSTANSI", "LLDIKTI Wilayah III")
ALAMAT_INSTANSI = alamat_sibkd()

server = MCPServer(
    name="sibkd-mcp",
    version=__version__,
    instructions=(
        f"Memantau dan mengelola laporan BKD SISTER v2 bulanan dosen bersertifikat pendidik di "
        f"SIBKD {NAMA_INSTANSI} ({ALAMAT_INSTANSI}). Urutan yang disarankan: status_laporan untuk "
        "melihat periode, bulan, status pengisian (Buka/Tutup) beserta jadwalnya, dan status laporan "
        "(Belum dibuat/Draft/Valid/Tunda); detail_laporan untuk rincian satu bulan, termasuk golongan "
        "penyetaraan dan nominal tunjangan sertifikasi; pengumuman untuk instruksi pelaporan terbaru. "
        "Bulan boleh ditulis 'Oktober 2026', 'oktober', atau '10'; id_periode kosong berarti periode "
        "aktif. NIK, NPWP, nomor HP, dan tanggal lahir selalu disamarkan. Semua tool hanya membaca, "
        "kecuali empat yang MENULIS ke SIBKD: unggah_laporan (mengganti PDF laporan periode itu), "
        "sinkronkan_data (menarik ulang data dari SISTER/PDDIKTI), tunda_proses (status jadi Tunda), "
        "dan lanjut_proses (pernyataan persetujuan dosen yang mengikat dan tidak bisa dibatalkan "
        "tanpa prosedur resmi; wajib setuju_pernyataan=True). Jalankan keempatnya dengan "
        "uji_coba=True lebih dulu, tunjukkan hasilnya kepada pemakai, dan kirim sungguhan hanya "
        "setelah pemakai menyetujuinya."
    ),
)


def buka_klien(username: str = "", password: str = "") -> KlienSibkd:
    """Login SIBKD; kredensial kosong jatuh ke .env."""
    return KlienSibkd(username or None, password or None).login()


def gagal(galat: Exception) -> dict:
    """Balikan seragam untuk permintaan yang tidak bisa dipenuhi."""
    return {"ok": False, "pesan": str(galat)}


@server.tool()
def cek_login(username: str = "", password: str = "") -> dict:
    """Cek apakah NIDN dan password SIBKD bisa dipakai."""
    try:
        klien = buka_klien(username, password)
    except SibkdError as galat:
        return gagal(galat)
    return {"ok": True, "beranda": klien.url_beranda, "nama": klien.nama}


@server.tool()
def daftar_menu(username: str = "", password: str = "") -> list[dict]:
    """Menu SIBKD yang tersedia bagi akun ini (Beranda, BKD SISTER v2, Pengumuman)."""
    return buka_klien(username, password).daftar_navigasi()


@server.tool()
def status_laporan(username: str = "", password: str = "") -> dict:
    """Status laporan BKD SISTER v2: tiap periode, tiap bulan, dan PDF laporannya.

    Tiap bulan membawa status pengisian (Buka berarti sedang dalam jadwal) dan
    jadwalnya, status laporan (Belum dibuat, Draft, Valid, atau Tunda), serta
    penanda bulan berjalan. Ringkasannya: tanggal hari ini, periode aktif, dan
    jadwal bulan berjalan. Bulan laporan bukan bulan semester: periode GENAP
    2025/2026 dilaporkan September 2026 sampai Februari 2027, dan November
    serta Desember digabung menjadi satu kartu.
    """
    return BkdSister(buka_klien(username, password)).status().sebagai_dict()


@server.tool()
def detail_laporan(bulan: str = "", id_periode: str = "", username: str = "", password: str = "") -> dict:
    """Rincian satu bulan laporan BKD: status, identitas, golongan penyetaraan, berkas, dan pernyataan.

    `bulan` kosong berarti bulan berjalan. Hasilnya memuat jadwal dan status
    pengisian, status laporan, apakah laporan dikunci Admin PT, aksi yang
    ditawarkan halaman, identitas dosen, JAD awal/terakhir, pangkat/golongan
    penyetaraan, masa kerja, nominal tunjangan sertifikasi, PDF yang sudah
    diunggah, dan teks keempat pernyataan persetujuan.

    NIK KTP, NPWP, nomor HP, dan tanggal lahir hanya menyisakan 4 karakter
    terakhir: data itu tidak perlu ikut tersimpan di riwayat percakapan. Nominal
    tunjangan ditampilkan apa adanya karena SIBKD meminta dosen memeriksanya.
    """
    try:
        detail = BkdSister(buka_klien(username, password)).detail(bulan, id_periode)
    except BulanTidakDitemukan as galat:
        return gagal(galat)
    return detail.sebagai_dict(samarkan_pribadi=True)


@server.tool()
def pengumuman(username: str = "", password: str = "") -> dict:
    """Informasi Terbaru di beranda SIBKD dan daftar pengumuman beserta berkas PDF-nya.

    Informasi Terbaru biasanya berisi instruksi pelaporan bulan berjalan;
    pengumuman berisi mis. daftar penerima tunjangan sertifikasi.
    """
    papan = PapanPengumuman(buka_klien(username, password))
    informasi = papan.informasi_terbaru()
    return {
        "informasi_terbaru": informasi.sebagai_dict() if informasi else None,
        "pengumuman": [satu.sebagai_dict() for satu in papan.daftar()],
    }


@server.tool()
def unduh_berkas(
    jenis: str = "laporan",
    id_periode: str = "",
    cari: str = "",
    tujuan: str = "",
    timpa: bool = False,
    username: str = "",
    password: str = "",
) -> dict:
    """Simpan PDF dari SIBKD ke disk: laporan BKD satu periode, atau berkas pengumuman.

    `jenis` "laporan" mengunduh PDF laporan BKD SISTER periode `id_periode`
    (kosong = periode aktif) ke data/laporan_bkd. `jenis` "pengumuman"
    mengunduh berkas pengumuman yang judul atau nama berkasnya memuat `cari`
    (kosong = semua) ke data/pengumuman. `tujuan` mengganti foldernya; path
    relatif dihitung dari akar proyek. Berkas yang sudah ada dilewati kecuali
    `timpa` bernilai True. Hanya membaca SIBKD.
    """
    jenis = (jenis or "laporan").strip().lower()
    if jenis not in ("laporan", "pengumuman"):
        return gagal(ValueError("jenis harus 'laporan' atau 'pengumuman'"))
    bawaan = dir_data() / ("laporan_bkd" if jenis == "laporan" else "pengumuman")
    lokasi = path_dari_akar(tujuan) if tujuan else bawaan
    klien = buka_klien(username, password)
    if jenis == "laporan":
        return BkdSister(klien).unduh_laporan(lokasi, id_periode=id_periode, timpa=timpa)
    return PapanPengumuman(klien).unduh(lokasi, cari=cari, timpa=timpa)


@server.tool()
def sinkronkan_data(
    bulan: str,
    jenis: str,
    id_periode: str = "",
    uji_coba: bool = False,
    username: str = "",
    password: str = "",
) -> list[dict]:
    """Tarik ulang data dari SISTER/PDDIKTI ke laporan satu bulan, seperti tombol sinkron di SIBKD.

    MENULIS ke SIBKD: data lokal SIBKD diganti dengan data terbaru dari SISTER.
    `jenis` salah satu dari identitas, homebase, pendidikan, jafung,
    kepangkatan; boleh beberapa dipisah koma, atau "semua". Tombolnya hanya ada
    pada bulan yang sedang dibuka dan tidak dikunci Admin PT; selain itu
    permintaannya ditahan. Jalankan dengan `uji_coba=True` lebih dulu dan minta
    persetujuan pemakai sebelum mengirim sungguhan.
    """
    try:
        daftar_jenis_sinkron(jenis)  # tolak jenis yang salah sebelum login
        return BkdSister(buka_klien(username, password)).sinkronkan_banyak(
            bulan, jenis, id_periode=id_periode, uji_coba=uji_coba
        )
    except (BulanTidakDitemukan, ValueError) as galat:
        return [gagal(galat) | {"pilihan_jenis": list(JENIS_SINKRON)}]


@server.tool()
def unggah_laporan(
    bulan: str,
    berkas: str,
    id_periode: str = "",
    uji_coba: bool = False,
    username: str = "",
    password: str = "",
) -> dict:
    """Unggah PDF laporan BKD SISTER (LKD) untuk satu bulan, seperti form "Upload File BKD".

    MENULIS ke SIBKD. SIBKD menyimpan satu PDF per periode, jadi berkas baru
    menggantikan PDF lama untuk semua bulan pada periode itu. `berkas` adalah
    path PDF (maks. 5048 KB); path relatif dicari dari direktori kerja, lalu
    akar proyek. Hanya bisa pada bulan yang sedang dibuka dan tidak dikunci
    Admin PT. Jalankan dengan `uji_coba=True` lebih dulu dan minta persetujuan
    pemakai sebelum mengirim sungguhan.
    """
    try:
        return BkdSister(buka_klien(username, password)).unggah_laporan(
            bulan, path_masukan(berkas), id_periode=id_periode, uji_coba=uji_coba
        )
    except BulanTidakDitemukan as galat:
        return gagal(galat)


@server.tool()
def tunda_proses(
    bulan: str,
    id_periode: str = "",
    uji_coba: bool = False,
    username: str = "",
    password: str = "",
) -> dict:
    """Jadikan status laporan satu bulan Tunda, seperti tombol "Tunda Proses".

    MENULIS ke SIBKD. Laporan yang ditunda masih bisa dilanjutkan selama jadwal
    pengisiannya terbuka. Jalankan dengan `uji_coba=True` lebih dulu dan minta
    persetujuan pemakai sebelum mengirim sungguhan.
    """
    try:
        return BkdSister(buka_klien(username, password)).tunda_proses(
            bulan, id_periode=id_periode, uji_coba=uji_coba
        )
    except BulanTidakDitemukan as galat:
        return gagal(galat)


@server.tool()
def lanjut_proses(
    bulan: str,
    setuju_pernyataan: bool = False,
    id_periode: str = "",
    uji_coba: bool = False,
    username: str = "",
    password: str = "",
) -> dict:
    """Setujui empat pernyataan dosen dan lanjutkan proses laporan, seperti tombol "Lanjut Proses".

    MENULIS ke SIBKD, dan persetujuan ini mengikat secara administratif serta
    tidak bisa dibatalkan tanpa prosedur resmi. Isinya: data profil benar,
    data jabatan fungsional dan golongan penyetaraan akurat, PDF yang diunggah
    dokumen resmi, dan pemahaman bahwa persetujuan ini mengikat.

    Wajib dua langkah. Pertama panggil dengan `uji_coba=True`: hasilnya memuat
    teks keempat pernyataan dan nilai yang disetujui (golongan, masa kerja,
    nominal tunjangan). Bacakan semuanya kepada pemakai. Baru setelah pemakai
    menyatakan setuju, panggil lagi dengan `setuju_pernyataan=True` dan
    `uji_coba=False`. Tanpa `setuju_pernyataan=True` tidak ada yang dikirim.
    """
    try:
        return BkdSister(buka_klien(username, password)).lanjut_proses(
            bulan, setuju_pernyataan=setuju_pernyataan, id_periode=id_periode, uji_coba=uji_coba
        )
    except BulanTidakDitemukan as galat:
        return gagal(galat)


def jalankan() -> None:
    """Titik masuk perintah `sibkd-mcp` (stdio)."""
    server.run()


if __name__ == "__main__":
    jalankan()
