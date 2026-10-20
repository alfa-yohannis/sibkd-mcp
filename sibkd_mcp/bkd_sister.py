"""Menu BKD SISTER v2 (/dosen/bkdsister_v2): status laporan bulanan dan aksinya.

Halaman utamanya satu tabel: tiap baris satu periode pelaporan (mis. GENAP
2025/2026), tiap kolom satu bulan laporan, ditutup satu sel berkas PDF BKD.
Bulan laporan bukan bulan semesternya: periode GENAP 2025/2026 (Maret sampai
Agustus 2026) dilaporkan pada September 2026 sampai Februari 2027, dan November
serta Desember digabung menjadi satu kartu.

    status()          tabel itu beserta ringkasan periode aktif
    detail(bulan)     halaman detail satu bulan (lihat detail_laporan.py)
    unduh_laporan()   PDF laporan BKD satu periode

Empat aksi menulis, semuanya meniru tombol di halaman detail:

    unggah_laporan()  mengganti PDF laporan periode itu
    sinkronkan()      menarik ulang data dari SISTER/PDDIKTI
    tunda_proses()    menjadikan status laporan Tunda
    lanjut_proses()   pernyataan persetujuan dosen yang mengikat

Semuanya menerima `uji_coba`: dengan uji_coba=True tidak ada yang dikirim, yang
dikembalikan alamat dan muatan yang akan dikirim beserta hambatan yang akan
membuat pengiriman sungguhan ditolak. Hambatannya mengikuti apa yang ditawarkan
halaman: bulan di luar jadwal, laporan yang dikunci Admin PT, atau tombol yang
tidak dicetak SIBKD membuat aksi itu tidak dikirim.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from sibkd_mcp.bulan import (
    bulan_dalam_label,
    nama_bulan,
    slug_bulan,
    tahun_dalam_label,
    tanggal_iso,
    urai_bulan,
    urai_rentang,
)
from sibkd_mcp.detail_laporan import BerkasBkd, DetailLaporan, teks, urai_detail
from sibkd_mcp.konfigurasi import KonfigurasiError, baca_angka, baca_pengaturan
from sibkd_mcp.privasi import samarkan_pasangan
from sibkd_mcp.sibkd_client import KlienSibkd, SibkdError, nama_berkas_aman

PATH_BKD_BAWAAN = "/dosen/bkdsister_v2"
UKURAN_MAKS_BAWAAN_KB = 5048

# Endpoint tulis, relatif terhadap path menu. Garis miring yang hilang pada
# sinkron_pendidikan memang begitu di halaman SIBKD; ditiru apa adanya.
ENDPOINT_BAWAAN = {
    "unggah": "upload_laporan_bkd_sister",
    "lanjut": "lanjut_proses/{id_periode}/{bulan}/{gol_penyetaraan}/{thn_masa_kerja}/{bln_masa_kerja}/{tgl_acuan}",
    "tunda": "tunda_proses/{id_periode}/{bulan}",
    "sinkron_identitas": "update_miror_sister/{id_periode}/{bulan}",
    "sinkron_homebase": "update_homebase_sister/{id_periode}/{bulan}",
    "sinkron_pendidikan": "update_rwy_pend_sister{id_periode}/{bulan}",
    "sinkron_jafung": "api_jafung/{id_periode}/{bulan}",
    "sinkron_kepangkatan": "api_kepangkatan_nonapi/{id_periode}/{bulan}",
}

# jenis sinkronisasi -> keterangan; nama endpoint dan tombolnya "sinkron_<jenis>"
JENIS_SINKRON = {
    "identitas": "identitas dosen dari SISTER/PDDIKTI (nama, serdik, PT, No. HP, NPWP, NIK)",
    "homebase": "homebase: program studi dan instansi dosen",
    "pendidikan": "riwayat pendidikan (gelar, S1, S2, S3)",
    "jafung": "riwayat jabatan fungsional, dasar golongan penyetaraan",
    "kepangkatan": "pangkat/golongan dari SISTER (sumber SIASN), terutama untuk PNS DPK",
}

# sebutan lain yang dipahami pemakai untuk jenis yang sama
ALIAS_SINKRON = {
    "profil": "identitas",
    "data_diri": "identitas",
    "prodi": "homebase",
    "riwayat_pendidikan": "pendidikan",
    "rwy_pend": "pendidikan",
    "jabatan": "jafung",
    "jabatan_fungsional": "jafung",
    "golongan": "kepangkatan",
    "pangkat": "kepangkatan",
}


class BulanTidakDitemukan(SibkdError):
    """Bulan yang diminta tidak ada pada periode itu, atau tulisannya tidak dipahami."""


def jenis_sinkron(jenis: str) -> str:
    """'Jafung', 'jabatan fungsional', 'golongan' -> nama jenis baku; selain itu ValueError."""
    kunci = re.sub(r"[^a-z]+", "_", (jenis or "").strip().lower()).strip("_")
    kunci = ALIAS_SINKRON.get(kunci, kunci)
    if kunci not in JENIS_SINKRON:
        raise ValueError(f"Jenis sinkronisasi {jenis!r} tidak dikenal. Pilihan: {', '.join(JENIS_SINKRON)}")
    return kunci


def daftar_jenis_sinkron(jenis: str) -> list[str]:
    """'jafung, kepangkatan' atau 'semua' -> daftar jenis baku, urut seperti di halaman."""
    if (jenis or "").strip().lower() in ("semua", "all", "*"):
        return list(JENIS_SINKRON)
    hasil: list[str] = []
    for satu in re.split(r"[,;]", jenis or ""):
        if satu.strip():
            baku = jenis_sinkron(satu)
            if baku not in hasil:
                hasil.append(baku)
    if not hasil:
        raise ValueError(f"Jenis sinkronisasi belum diisi. Pilihan: {', '.join(JENIS_SINKRON)}, atau semua")
    return hasil


@dataclass
class BulanLaporan:
    """Satu kartu bulan pada tabel BKD SISTER v2."""

    id_periode: str
    slug: str
    nama: str
    nomor_bulan: list[int]
    tahun: int | None
    url: str
    jadwal: str = ""
    status_pengisian: str = ""
    status_laporan: str = ""
    kode_status: str = ""
    bulan_berjalan: bool = False

    @property
    def terbuka(self) -> bool:
        """Status pengisian "Buka": bulan ini sedang dalam jadwal pelaporan."""
        return self.status_pengisian.strip().lower() == "buka"

    def sebagai_dict(self) -> dict:
        mulai, selesai = urai_rentang(self.jadwal)
        return asdict(self) | {"terbuka": self.terbuka, "jadwal_mulai": mulai, "jadwal_selesai": selesai}


@dataclass
class PeriodeLaporan:
    """Satu baris tabel: periode pelaporan beserta bulan-bulan dan berkas PDF-nya."""

    id_periode: str
    nama: str
    rentang: str
    bulan: list[BulanLaporan] = field(default_factory=list)
    berkas: BerkasBkd | None = None

    def sebagai_dict(self) -> dict:
        return {
            "id_periode": self.id_periode,
            "nama": self.nama,
            "rentang": self.rentang,
            "bulan": [satu.sebagai_dict() for satu in self.bulan],
            "berkas": self.berkas.sebagai_dict() if self.berkas else None,
        }


@dataclass
class StatusPelaporan:
    """Isi halaman BKD SISTER v2: ringkasan di atas tabel dan seluruh periode."""

    tanggal_hari_ini: str = ""
    status_pengisian: str = ""
    jadwal_berjalan: str = ""
    periode_aktif: str = ""
    keterangan: str = ""
    periode: list[PeriodeLaporan] = field(default_factory=list)

    def cari_periode(self, id_periode: str) -> PeriodeLaporan | None:
        return next((satu for satu in self.periode if satu.id_periode == str(id_periode)), None)

    def periode_berjalan(self) -> PeriodeLaporan | None:
        """Periode yang disebut "Periode Pelaporan Aktif", atau satu-satunya yang ada."""
        dicari = re.sub(r"\s+", " ", self.periode_aktif).strip().lower()
        for satu in self.periode:
            if dicari and re.sub(r"\s+", " ", satu.nama).strip().lower() == dicari:
                return satu
        for satu in self.periode:
            if any(bulan.bulan_berjalan for bulan in satu.bulan):
                return satu
        return self.periode[0] if self.periode else None

    def bulan_berjalan(self) -> BulanLaporan | None:
        return next((bulan for satu in self.periode for bulan in satu.bulan if bulan.bulan_berjalan), None)

    def sebagai_dict(self) -> dict:
        aktif = self.periode_berjalan()
        berjalan = self.bulan_berjalan()
        mulai, selesai = urai_rentang(self.jadwal_berjalan)
        return {
            "tanggal_hari_ini": self.tanggal_hari_ini,
            "tanggal_hari_ini_iso": tanggal_iso(self.tanggal_hari_ini),
            "status_pengisian": self.status_pengisian,
            "jadwal_berjalan": self.jadwal_berjalan,
            "jadwal_mulai": mulai,
            "jadwal_selesai": selesai,
            "periode_aktif": self.periode_aktif,
            "id_periode_aktif": aktif.id_periode if aktif else "",
            "bulan_berjalan": berjalan.nama if berjalan else "",
            "keterangan": self.keterangan,
            "periode": [satu.sebagai_dict() for satu in self.periode],
        }


def urai_kartu_bulan(kartu) -> BulanLaporan:
    """Satu a.bkd-month-card jadi BulanLaporan; id dan slug dibaca dari tautannya."""
    alamat = kartu.get("href", "") or ""
    cocok = re.search(r"/detail/([^/]+)/([^/?#]+)", alamat)
    nama = teks(kartu.select_one(".bkd-month-name"))
    validasi = kartu.select_one(".bkd-validation")
    titik = validasi.select_one(".bkd-dot") if validasi else None
    tulisan = [teks(span) for span in validasi.find_all("span") if "bkd-dot" not in (span.get("class") or [])] if validasi else []
    kelas = kartu.get("class") or []
    return BulanLaporan(
        id_periode=cocok.group(1) if cocok else "",
        slug=cocok.group(2).lower() if cocok else "",
        nama=nama,
        nomor_bulan=bulan_dalam_label(nama),
        tahun=tahun_dalam_label(nama),
        url=alamat,
        jadwal=(kartu.get("title") or "").strip(),
        status_pengisian=teks(kartu.select_one(".bkd-status-badge")),
        status_laporan=next((satu for satu in tulisan if satu), ""),
        kode_status=" ".join(k for k in (titik.get("class") or []) if k != "bkd-dot") if titik else "",
        bulan_berjalan="is-current" in kelas,
    )


def urai_status(html: str) -> StatusPelaporan:
    """Urai halaman /dosen/bkdsister_v2 jadi StatusPelaporan."""
    sup = BeautifulSoup(html, "lxml")
    tabel = sup.select_one("table.bkd-table")
    if tabel is None:
        raise SibkdError("Tabel laporan BKD (table.bkd-table) tidak ditemukan; tampilan SIBKD mungkin berubah")

    status = StatusPelaporan()
    for kartu in sup.select(".bkd-summary-card"):
        label = teks(kartu.select_one(".bkd-summary-label")).lower()
        nilai = teks(kartu.select_one(".bkd-summary-value"))
        if "tanggal" in label:
            status.tanggal_hari_ini = nilai
        elif "status pengisian" in label:
            status.status_pengisian = nilai
            status.jadwal_berjalan = teks(kartu.select_one(".bkd-summary-note"))
        elif "periode" in label:
            status.periode_aktif = nilai
    status.keterangan = teks(sup.select_one(".bkd-info"))

    for baris in tabel.select("tbody tr"):
        sel_periode = baris.select_one(".bkd-period")
        if sel_periode is None:
            continue
        bulan = [urai_kartu_bulan(kartu) for kartu in baris.select(".bkd-month-card")]
        kartu_berkas = baris.select_one(".bkd-file-card")
        tautan = kartu_berkas.find("a", href=True) if kartu_berkas else None
        status.periode.append(PeriodeLaporan(
            id_periode=next((satu.id_periode for satu in bulan if satu.id_periode), ""),
            nama=teks(sel_periode.select_one(".bkd-period-title")),
            rentang=teks(sel_periode.select_one(".bkd-period-range")),
            bulan=bulan,
            berkas=BerkasBkd.dari_tautan(tautan["href"], teks(kartu_berkas)) if tautan else None,
        ))
    return status


def periksa_pdf(path: Path, ukuran_maks_kb: int) -> tuple[list[str], bytes]:
    """Hambatan unggah untuk satu berkas, beserta isinya kalau terbaca.

    Meniru pemeriksaan di halaman SIBKD (hanya PDF, batas ukuran), ditambah
    pemeriksaan tanda tangan berkas "%PDF" supaya berkas yang salah tidak
    terkirim hanya karena namanya berakhiran .pdf.
    """
    if not path.is_file():
        return [f"Berkas tidak ditemukan: {path}"], b""
    isi = path.read_bytes()
    hambatan = []
    if path.suffix.lower() != ".pdf" or not isi.startswith(b"%PDF"):
        hambatan.append(f"{path.name} bukan PDF; SIBKD hanya menerima PDF")
    if len(isi) > ukuran_maks_kb * 1024:
        hambatan.append(f"{path.name} berukuran {len(isi) // 1024} KB, melebihi batas {ukuran_maks_kb} KB")
    return hambatan, isi


class BkdSister:
    """Akses menu BKD SISTER v2 untuk satu sesi SIBKD."""

    path_bawaan = PATH_BKD_BAWAAN
    kunci_path = "SIBKD_PATH_BKD"

    def __init__(self, klien: KlienSibkd):
        self.klien = klien

    def path(self) -> str:
        """Path menu ini; bisa dipindah lewat setelan path_bkd."""
        return baca_pengaturan(self.kunci_path, self.path_bawaan).rstrip("/")

    # --- membaca -----------------------------------------------------------

    def status(self) -> StatusPelaporan:
        """Tabel periode x bulan beserta ringkasan periode aktif."""
        return urai_status(self.klien.ambil_halaman(self.path()).text)

    def cari_bulan(self, bulan: str = "", id_periode: str = "", status: StatusPelaporan | None = None) -> BulanLaporan:
        """Kartu bulan yang dimaksud pemakai.

        `bulan` kosong berarti bulan berjalan; `id_periode` kosong berarti
        periode aktif. Bulan dicocokkan dengan kartu pada tabel, bukan disusun
        sendiri, karena SIBKD menampilkan halaman untuk slug apa pun (mis.
        'maret') walau bulan itu bukan bagian periodenya. "Desember" cocok
        dengan kartu "November - Desember". Periode lama yang tidak tampil di
        tabel tetap bisa dibuka dengan menyebut bulannya.
        """
        status = status or self.status()
        if id_periode:
            periode = status.cari_periode(str(id_periode))
            if periode is None:
                if not bulan:
                    raise BulanTidakDitemukan(f"Periode {id_periode} tidak tampil di tabel; sebutkan bulannya")
                nomor, tahun = self._urai(bulan)
                slug = slug_bulan(nomor)
                return BulanLaporan(
                    id_periode=str(id_periode),
                    slug=slug,
                    nama=f"{nama_bulan(nomor)} {tahun}" if tahun else nama_bulan(nomor),
                    nomor_bulan=[nomor],
                    tahun=tahun,
                    url=self.klien.url(f"{self.path()}/detail/{id_periode}/{slug}"),
                )
        else:
            periode = status.periode_berjalan()
            if periode is None:
                raise SibkdError("Tidak ada periode pelaporan pada halaman BKD SISTER v2")

        pilihan = ", ".join(satu.nama for satu in periode.bulan)
        if not bulan:
            berjalan = next((satu for satu in periode.bulan if satu.bulan_berjalan), None)
            if berjalan is None:
                raise BulanTidakDitemukan(f"Tidak ada bulan berjalan pada {periode.nama}; sebutkan bulannya ({pilihan})")
            return berjalan

        nomor, tahun = self._urai(bulan)
        for satu in periode.bulan:
            if nomor in satu.nomor_bulan and (tahun is None or satu.tahun in (None, tahun)):
                return satu
        raise BulanTidakDitemukan(f"Bulan {bulan!r} tidak ada pada periode {periode.nama}. Pilihan: {pilihan}")

    @staticmethod
    def _urai(bulan: str) -> tuple[int, int | None]:
        try:
            return urai_bulan(bulan)
        except ValueError as galat:
            raise BulanTidakDitemukan(str(galat)) from galat

    def detail(self, bulan: str = "", id_periode: str = "") -> DetailLaporan:
        """Isi halaman detail satu bulan. Data pribadi masih utuh di objek ini."""
        sasaran = self.cari_bulan(bulan, id_periode)
        jawaban = self.klien.ambil_halaman(sasaran.url)
        return urai_detail(jawaban.text, jawaban.url, id_periode=sasaran.id_periode, bulan=sasaran.slug)

    def unduh_laporan(self, tujuan: str | Path, *, id_periode: str = "", timpa: bool = False) -> dict:
        """Simpan PDF laporan BKD satu periode (bawaannya periode aktif) ke folder `tujuan`."""
        status = self.status()
        periode = status.cari_periode(str(id_periode)) if id_periode else status.periode_berjalan()
        if periode is None:
            raise SibkdError(f"Periode {id_periode or 'aktif'} tidak tampil di tabel BKD SISTER v2")
        hasil = {"tujuan": str(tujuan), "periode": periode.nama, "berkas": [], "dilewati": [], "gagal": []}
        if periode.berkas is None:
            hasil["pesan"] = f"Belum ada PDF laporan BKD pada periode {periode.nama}"
            return hasil
        path, baru = self.klien.unduh(periode.berkas.url, Path(tujuan) / nama_berkas_aman(periode.berkas.nama), timpa=timpa)
        hasil["berkas" if baru else "dilewati"].append(str(path))
        hasil["diunggah"] = periode.berkas.diunggah
        return hasil

    # --- menulis -----------------------------------------------------------

    def alamat_endpoint(self, nama: str, **nilai: str) -> str:
        """URL penuh sebuah endpoint tulis, dari templat bawaan atau setelan endpoint_<nama>."""
        templat = baca_pengaturan(f"SIBKD_ENDPOINT_{nama.upper()}", ENDPOINT_BAWAAN[nama])
        try:
            relatif = templat.format(**nilai)
        except (KeyError, IndexError) as galat:
            raise KonfigurasiError(f"Setelan endpoint_{nama} memakai isian yang tidak dikenal: {galat}") from galat
        return self.klien.url(f"{self.path()}/{relatif.lstrip('/')}")

    def _hasil(self, aksi: str, detail: DetailLaporan, url: str, muatan: dict, *, uji_coba: bool,
               hambatan: list[str], peringatan: list[str], **lain) -> dict:
        """Bentuk balikan yang sama untuk keempat aksi tulis."""
        return {
            "ok": not hambatan,
            "uji_coba": uji_coba,
            "terkirim": False,
            "aksi": aksi,
            "bulan": detail.nama_bulan or detail.bulan,
            "periode": detail.periode,
            "id_periode": detail.id_periode,
            "status_laporan": detail.status_laporan,
            "status_pengisian": detail.status_pengisian,
            "metode": "POST",
            "url": url,
            "muatan": muatan,
            "hambatan": hambatan,
            "peringatan": peringatan,
            **lain,
        }

    def _kirim_atau_tahan(self, hasil: dict, *, uji_coba: bool, data=None, files=None, referer: str = "") -> dict:
        """Kirim kalau tidak ada hambatan dan bukan uji coba; selain itu jelaskan kenapa tidak."""
        if uji_coba:
            hasil["pesan"] = "Uji coba: tidak ada yang dikirim ke SIBKD."
            if hasil["hambatan"]:
                hasil["pesan"] += " Pengiriman sungguhan akan ditahan: " + "; ".join(hasil["hambatan"]) + "."
            return hasil
        if hasil["hambatan"]:
            hasil["pesan"] = "Tidak dikirim: " + "; ".join(hasil["hambatan"])
            return hasil
        balasan = self.klien.kirim(hasil["url"], data=data, files=files, referer=referer)
        hasil.update(
            ok=balasan["ok"],
            terkirim=True,
            pesan=balasan["pesan"],
            status=balasan["status"],
            status_http=balasan["status_http"],
        )
        return hasil

    @staticmethod
    def hambatan_jadwal(detail: DetailLaporan) -> list[str]:
        """Hambatan yang berlaku untuk semua aksi: di luar jadwal atau dikunci Admin PT."""
        hambatan = []
        if detail.terkunci:
            hambatan.append(f"{detail.pesan_kunci or 'Laporan dikunci Admin PT'}")
        if not detail.terbuka:
            jadwal = f" (jadwal: {detail.jadwal})" if detail.jadwal else ""
            hambatan.append(f"Status pengisian {detail.nama_bulan or detail.bulan} {detail.status_pengisian or 'tidak diketahui'}{jadwal}")
        return hambatan

    def unggah_laporan(self, bulan: str, berkas: str | Path, *, id_periode: str = "", uji_coba: bool = False) -> dict:
        """Unggah PDF laporan BKD SISTER untuk satu bulan. MENULIS ke SIBKD.

        SIBKD menyimpan satu PDF per periode: berkas baru menggantikan yang lama
        di semua bulan periode itu. Yang dikirim sama persis dengan form di
        halaman: id_periode, bln, dan berkas (multipart).
        """
        detail = self.detail(bulan, id_periode)
        path = Path(berkas).expanduser()
        batas_kb = baca_angka("SIBKD_UKURAN_MAKS_KB", UKURAN_MAKS_BAWAAN_KB)
        hambatan_berkas, isi = periksa_pdf(path, batas_kb)
        hambatan = self.hambatan_jadwal(detail) + hambatan_berkas
        if not detail.unggah.get("tersedia"):
            hambatan.append("Halaman detail tidak memuat form unggah")

        peringatan = []
        if detail.berkas:
            peringatan.append(
                f"Berkas yang sudah ada ({detail.berkas.nama}, diunggah {detail.berkas.diunggah or '?'}) akan "
                "tergantikan; SIBKD memakai satu PDF untuk semua bulan pada periode yang sama"
            )
        isian = {
            "id_periode": detail.unggah.get("id_periode") or detail.id_periode,
            "bln": detail.unggah.get("bln") or detail.bulan,
        }
        field_berkas = detail.unggah.get("field_berkas") or "berkas"
        muatan = isian | {field_berkas: {"nama": path.name, "path": str(path), "ukuran_kb": len(isi) // 1024,
                                         "tipe": "application/pdf"}}
        hasil = self._hasil("unggah_laporan", detail, self.alamat_endpoint("unggah"), muatan,
                            uji_coba=uji_coba, hambatan=hambatan, peringatan=peringatan)
        return self._kirim_atau_tahan(
            hasil, uji_coba=uji_coba, data=isian,
            files={field_berkas: (path.name, isi, "application/pdf")}, referer=detail.url,
        )

    def sinkronkan(self, bulan: str, jenis: str, *, id_periode: str = "", uji_coba: bool = False) -> dict:
        """Tarik ulang satu jenis data dari SISTER/PDDIKTI ke laporan bulan itu. MENULIS ke SIBKD.

        Meniru tombol sinkron di halaman detail: POST tanpa badan ke endpointnya.
        Halaman menonaktifkan tombol-tombol ini kalau laporan dikunci Admin PT,
        dan hanya mencetaknya pada bulan yang sedang dibuka.
        """
        baku = jenis_sinkron(jenis)
        return self._sinkronkan(self.detail(bulan, id_periode), baku, uji_coba=uji_coba)

    def sinkronkan_banyak(self, bulan: str, jenis: str, *, id_periode: str = "", uji_coba: bool = False) -> list[dict]:
        """Seperti sinkronkan(), untuk beberapa jenis sekaligus ('jafung, kepangkatan' atau 'semua').

        Halaman detail dibaca sekali saja: alamat dan tombol sinkron tidak
        berubah oleh sinkronisasi sebelumnya.
        """
        daftar = daftar_jenis_sinkron(jenis)
        detail = self.detail(bulan, id_periode)
        return [self._sinkronkan(detail, satu, uji_coba=uji_coba) for satu in daftar]

    def _sinkronkan(self, detail: DetailLaporan, baku: str, *, uji_coba: bool) -> dict:
        nilai = {"id_periode": detail.id_periode, "bulan": detail.bulan}
        hambatan = self.hambatan_jadwal(detail)
        if not detail.tombol.get(f"sinkron_{baku}"):
            hambatan.append(f"Halaman detail tidak menampilkan tombol sinkron {baku}")
        peringatan = []
        if baku == "pendidikan":
            peringatan.append("Alamat ini disusun halaman SIBKD tanpa garis miring sebelum id_periode; ditiru apa adanya")
        hasil = self._hasil(f"sinkron_{baku}", detail, self.alamat_endpoint(f"sinkron_{baku}", **nilai), {},
                            uji_coba=uji_coba, hambatan=hambatan, peringatan=peringatan,
                            jenis=baku, keterangan=JENIS_SINKRON[baku])
        return self._kirim_atau_tahan(hasil, uji_coba=uji_coba, referer=detail.url)

    def tunda_proses(self, bulan: str, *, id_periode: str = "", uji_coba: bool = False) -> dict:
        """Jadikan status laporan bulan itu Tunda. MENULIS ke SIBKD.

        Menurut halaman SIBKD, laporan yang ditunda masih bisa dilanjutkan selama
        periode pengisian masih terbuka.
        """
        detail = self.detail(bulan, id_periode)
        hambatan = self.hambatan_jadwal(detail)
        if not detail.tombol.get("tunda_proses"):
            hambatan.append("Halaman detail tidak menampilkan tombol Tunda Proses")
        url = self.alamat_endpoint("tunda", id_periode=detail.id_periode, bulan=detail.bulan)
        hasil = self._hasil("tunda_proses", detail, url, {}, uji_coba=uji_coba, hambatan=hambatan, peringatan=[])
        return self._kirim_atau_tahan(hasil, uji_coba=uji_coba, referer=detail.url)

    def lanjut_proses(self, bulan: str, *, setuju_pernyataan: bool = False, id_periode: str = "",
                      uji_coba: bool = False) -> dict:
        """Setujui empat pernyataan dan lanjutkan proses laporan. MENULIS ke SIBKD.

        Ini pernyataan dosen yang mengikat secara administratif dan tidak bisa
        dibatalkan tanpa prosedur resmi. Di browser keempat centangnya hanya
        diperiksa JavaScript; server cukup menerima POST ke alamat yang memuat
        golongan penyetaraan, masa kerja, dan tanggal acuan dari halaman. Karena
        itu paket ini mewajibkan `setuju_pernyataan=True` sebagai pengganti
        centang tersebut, dan uji coba mengembalikan teks keempat pernyataan
        beserta nilai yang akan disetujui supaya bisa dibaca pemakai lebih dulu.
        """
        detail = self.detail(bulan, id_periode)
        parameter = detail.parameter_lanjut
        nilai_url = {
            "id_periode": detail.id_periode,
            "bulan": detail.bulan,
            # sama seperti halaman: nilai kosong diganti 0, kecuali tgl_acuan
            "gol_penyetaraan": parameter.gol_penyetaraan or "0",
            "thn_masa_kerja": parameter.thn_masa_kerja or "0",
            "bln_masa_kerja": parameter.bln_masa_kerja or "0",
            "tgl_acuan": parameter.tgl_acuan,
        }
        hambatan = self.hambatan_jadwal(detail)
        if not detail.tombol.get("lanjut_proses"):
            hambatan.append("Halaman detail tidak menampilkan tombol Lanjut Proses")
        if detail.berkas is None:
            hambatan.append("Belum ada PDF laporan yang diunggah; unggah dulu lewat unggah_laporan")
        if not setuju_pernyataan and not uji_coba:
            hambatan.append("setuju_pernyataan belum True: pemakai harus menyetujui keempat pernyataan lebih dulu")

        peringatan = []
        if nilai_url["gol_penyetaraan"] == "0":
            peringatan.append("Golongan penyetaraan bernilai 0; periksa jafung/kepangkatan dan sinkronkan dulu")
        if not parameter.tgl_acuan:
            peringatan.append("Tanggal acuan kosong; alamatnya akan berakhir dengan garis miring, seperti di halaman")

        hasil = self._hasil(
            "lanjut_proses", detail, self.alamat_endpoint("lanjut", **nilai_url), {},
            uji_coba=uji_coba, hambatan=hambatan, peringatan=peringatan,
            nilai_dalam_url=nilai_url,
            pernyataan=detail.pernyataan,
            ringkasan_persetujuan=samarkan_pasangan(detail.ringkasan_persetujuan),
            perlu_persetujuan=True,
        )
        hasil = self._kirim_atau_tahan(hasil, uji_coba=uji_coba, referer=detail.url)
        if uji_coba:
            hasil["pesan"] += (
                " Bacakan keempat pernyataan kepada pemakai; kirim dengan setuju_pernyataan=True dan "
                "uji_coba=False hanya setelah pemakai menyetujuinya. Persetujuan ini mengikat dan tidak "
                "bisa dibatalkan tanpa prosedur resmi."
            )
        return hasil
