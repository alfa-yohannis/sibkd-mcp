"""Halaman detail satu bulan laporan BKD (/dosen/bkdsister_v2/detail/<id>/<bulan>).

Halaman ini memuat semua yang perlu diperiksa dosen sebelum menekan "Lanjut
Proses":

    ringkasan          periode, bulan, status pengisian (Buka/Tutup) beserta
                       jadwalnya, status laporan (Belum dibuat/Draft/Valid/Tunda)
    identitas dosen    NIDN/NUPTK, nama, No. Serdik, PT, prodi, status, No. HP,
                       NPWP, NIK KTP, tanggal lahir, status kepegawaian
    golongan           JAD awal/terakhir/KUM terkecil, tanggal acuan, pangkat/
                       golongan penyetaraan, masa kerja, nominal tunjangan
    berkas             PDF laporan yang sudah diunggah beserta waktunya
    persetujuan        empat pernyataan yang harus dicentang sebelum lanjut

Bulan yang belum dibuat laporannya hanya menampilkan ringkasan. Nilai yang
dikirim SIBKD saat lanjut proses tidak diambil dari form, melainkan dari
variabel JavaScript halaman (gol_penyetaraan, thn_masa_kerja_penyetaraan,
bln_masa_kerja_penyetaraan, tgl_acuan); karena itu variabel tersebut ikut dibaca.

Laporan yang dikunci Admin PT tidak ditandai di HTML. Tandanya ada di skrip:
tombol-tombol sinkron dinonaktifkan dengan title "Laporan telah dikunci oleh
Admin PT". Skrip itu hanya dicetak server kalau laporannya memang terkunci.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from sibkd_mcp.bulan import urai_rentang, waktu_iso
from sibkd_mcp.privasi import samarkan, samarkan_pasangan, termasuk_pribadi
from sibkd_mcp.sibkd_client import SibkdError

# id tombol di halaman detail; dipakai untuk tahu aksi mana yang ditawarkan SIBKD
TOMBOL = {
    "lanjut_proses": "btn-lanjut-proses",
    "tunda_proses": "btn-tunda-proses",
    "sinkron_identitas": "sinkron_profil_sister",
    "sinkron_homebase": "sinkron_homebase_sister",
    "sinkron_pendidikan": "sinkron_rwy_pend_sister",
    "sinkron_jafung": "sinkron_jafung_tambah",
    "sinkron_kepangkatan": "sinkron_golongan_sister",
}

LABEL_IDENTITAS = {
    "nama": "nama",
    "no. serdik": "no_serdik",
    "nama pt": "nama_pt",
    "prodi": "prodi",
    "status keaktifan": "status_keaktifan",
    "no. hp": "no_hp",
    "npwp": "npwp",
    "nik ktp": "nik_ktp",
    "tgl lahir": "tgl_lahir",
    "status kepegawaian": "status_kepegawaian",
}

# field identitas yang disamarkan di setiap keluaran (lihat privasi.py)
FIELD_PRIBADI = ("no_hp", "npwp", "nik_ktp", "tgl_lahir")

LABEL_GOLONGAN = {
    "jad awal": "jad_awal",
    "jad terakhir": "jad_terakhir",
    "jad kum terkecil": "jad_kum_terkecil",
    "tanggal acuan": "tanggal_acuan",
    "pangkat/golongan penyetaraan": "pangkat_golongan",
    "penyetaraan pembayaran tunjangan sertifikasi": "tunjangan",
}

POLA_VARIABEL = re.compile(
    r"""var\s+(gol_penyetaraan|thn_masa_kerja_penyetaraan|bln_masa_kerja_penyetaraan|tgl_acuan|id_periode|bln)"""
    r"""\s*=\s*["']([^"']*)["']"""
)
POLA_KUNCI = re.compile(r"""attr\(\s*['"]title['"]\s*,\s*['"]([^'"]*dikunci[^'"]*)['"]""", re.I)
POLA_WAKTU = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")


def teks(elemen) -> str:
    """Teks sebuah elemen, spasi dirapatkan; elemen yang tidak ada jadi kosong."""
    if elemen is None:
        return ""
    return re.sub(r"\s+", " ", elemen.get_text(" ", strip=True)).strip()


def kunci_label(label: str) -> str:
    """'  No. HP ' -> 'no. hp'; bentuk pembanding label."""
    return re.sub(r"\s+", " ", (label or "").strip().lower())


def nama_field(label: str) -> str:
    """Label bebas -> nama field: 'Masa Kerja Penyetaraan' -> 'masa_kerja_penyetaraan'."""
    return re.sub(r"[^a-z0-9]+", "_", (label or "").lower()).strip("_")


@dataclass
class BerkasBkd:
    """PDF laporan BKD yang sudah diunggah ke SIBKD."""

    url: str
    nama: str
    diunggah: str = ""

    @classmethod
    def dari_tautan(cls, url: str, teks_sekitar: str = "") -> "BerkasBkd":
        waktu = POLA_WAKTU.search(teks_sekitar or "")
        return cls(url=url, nama=Path(urlparse(url).path).name, diunggah=waktu.group(0) if waktu else "")

    def sebagai_dict(self) -> dict:
        return asdict(self) | {"diunggah_iso": waktu_iso(self.diunggah)}


@dataclass
class IdentitasDosen:
    """Blok "Identitas Dosen". Nilai disimpan apa adanya; penyamaran terjadi saat dikeluarkan."""

    nidn: str = ""
    nuptk: str = ""
    nama: str = ""
    no_serdik: str = ""
    nama_pt: str = ""
    prodi: str = ""
    status_keaktifan: str = ""
    no_hp: str = ""
    npwp: str = ""
    nik_ktp: str = ""
    tgl_lahir: str = ""
    status_kepegawaian: str = ""
    lainnya: dict[str, str] = field(default_factory=dict)

    def sebagai_dict(self, *, samarkan_pribadi: bool = True) -> dict:
        """Bentuk datar; NIK, NPWP, No. HP, dan tanggal lahir disamarkan kecuali diminta lain."""
        hasil = asdict(self)
        if samarkan_pribadi:
            for kunci in FIELD_PRIBADI:
                hasil[kunci] = samarkan(hasil[kunci])
            hasil["lainnya"] = {
                kunci: samarkan(nilai) if termasuk_pribadi(kunci) else nilai
                for kunci, nilai in self.lainnya.items()
            }
            hasil["disamarkan"] = list(FIELD_PRIBADI)
        return hasil


@dataclass
class GolonganPenyetaraan:
    """Blok "Golongan Penyetaraan": jabatan fungsional, pangkat setara, masa kerja, tunjangan."""

    jad_awal: str = ""
    jad_terakhir: str = ""
    jad_kum_terkecil: str = ""
    tanggal_acuan: str = ""
    pangkat_golongan: str = ""
    masa_kerja_tahun: str = ""
    masa_kerja_bulan: str = ""
    tunjangan: str = ""
    kode_golongan: str = ""
    rincian: list[dict] = field(default_factory=list)

    def sebagai_dict(self) -> dict:
        return asdict(self) | {"rincian": samarkan_pasangan(self.rincian)}


@dataclass
class ParameterLanjut:
    """Nilai yang dimasukkan halaman ke alamat lanjut_proses, dibaca dari variabel JS-nya."""

    gol_penyetaraan: str = ""
    thn_masa_kerja: str = ""
    bln_masa_kerja: str = ""
    tgl_acuan: str = ""


@dataclass
class DetailLaporan:
    """Seluruh isi halaman detail satu bulan laporan."""

    url: str
    id_periode: str
    bulan: str
    periode: str = ""
    nama_bulan: str = ""
    status_pengisian: str = ""
    jadwal: str = ""
    status_laporan: str = ""
    kode_status: str = ""
    keterangan_status: str = ""
    informasi: list[str] = field(default_factory=list)
    pesan_aksi: str = ""
    tombol: dict[str, bool] = field(default_factory=dict)
    terkunci: bool = False
    pesan_kunci: str = ""
    identitas: IdentitasDosen | None = None
    golongan: GolonganPenyetaraan | None = None
    ringkasan_persetujuan: list[dict] = field(default_factory=list)
    pernyataan: list[dict] = field(default_factory=list)
    parameter_lanjut: ParameterLanjut = field(default_factory=ParameterLanjut)
    berkas: BerkasBkd | None = None
    unggah: dict = field(default_factory=dict)

    @property
    def terbuka(self) -> bool:
        """Status pengisian "Buka": bulan ini sedang dalam jadwal pelaporan."""
        return self.status_pengisian.strip().lower() == "buka"

    @property
    def label(self) -> str:
        """Mis. 'Oktober 2026 (GENAP 2025/2026)'."""
        return f"{self.nama_bulan or self.bulan} ({self.periode})" if self.periode else self.nama_bulan or self.bulan

    def sebagai_dict(self, *, samarkan_pribadi: bool = True) -> dict:
        """Bentuk datar siap dikirim REST API/MCP; data pribadi disamarkan secara bawaan."""
        mulai, selesai = urai_rentang(self.jadwal)
        return {
            "url": self.url,
            "id_periode": self.id_periode,
            "bulan": self.bulan,
            "periode": self.periode,
            "nama_bulan": self.nama_bulan,
            "status_pengisian": self.status_pengisian,
            "terbuka": self.terbuka,
            "jadwal": self.jadwal,
            "jadwal_mulai": mulai,
            "jadwal_selesai": selesai,
            "status_laporan": self.status_laporan,
            "kode_status": self.kode_status,
            "keterangan_status": self.keterangan_status,
            "informasi": self.informasi,
            "pesan_aksi": self.pesan_aksi,
            "tombol": self.tombol,
            "terkunci": self.terkunci,
            "pesan_kunci": self.pesan_kunci,
            "identitas": self.identitas.sebagai_dict(samarkan_pribadi=samarkan_pribadi) if self.identitas else None,
            "golongan": self.golongan.sebagai_dict() if self.golongan else None,
            "ringkasan_persetujuan": (
                samarkan_pasangan(self.ringkasan_persetujuan) if samarkan_pribadi else self.ringkasan_persetujuan
            ),
            "pernyataan": self.pernyataan,
            "parameter_lanjut": asdict(self.parameter_lanjut),
            "berkas": self.berkas.sebagai_dict() if self.berkas else None,
            "unggah": self.unggah,
        }


def bersihkan_komentar_js(kode: str) -> str:
    """Buang blok /* */ dan baris yang seluruhnya komentar //.

    Komentar di ujung baris dibiarkan: memotong dari '//' juga akan memotong
    alamat 'https://' di dalam string.
    """
    kode = re.sub(r"/\*.*?\*/", "", kode, flags=re.S)
    return "\n".join(baris for baris in kode.splitlines() if not baris.lstrip().startswith("//"))


def skrip_sebaris(sup) -> str:
    """Gabungan seluruh skrip inline halaman, tanpa komentar JS."""
    return "\n".join(
        bersihkan_komentar_js(skrip.get_text()) for skrip in sup.find_all("script") if not skrip.get("src")
    )


def baca_kartu_ringkasan(halaman) -> dict[str, dict]:
    """Kartu ringkasan di kepala halaman, berkunci label huruf kecil."""
    kartu_semua: dict[str, dict] = {}
    for kartu in halaman.select(".bkd-detail-card"):
        label = teks(kartu.find("p", class_="bkd-detail-label"))
        pil = kartu.select_one(".bkd-status-pill")
        jadwal = kartu.select_one("p > span.bkd-detail-label")
        kartu_semua[kunci_label(label)] = {
            "nilai": teks(kartu.select_one(".bkd-detail-value")),
            "catatan": teks(kartu.select_one(".bkd-detail-note")),
            "pil": teks(pil),
            "kelas_pil": [kelas for kelas in (pil.get("class") or []) if kelas.startswith("is-")] if pil else [],
            "jadwal": teks(jadwal),
        }
    return kartu_semua


def baca_identitas(halaman) -> IdentitasDosen | None:
    """Blok Identitas Dosen (.bkd-info-grid); None kalau laporan belum dibuat."""
    grid = halaman.select_one(".bkd-info-grid")
    if grid is None:
        return None
    identitas = IdentitasDosen()
    for blok in grid.find_all("div", recursive=False):
        label = teks(blok.find("label"))
        nilai = teks(blok.select_one(".bkd-field-box"))
        if not label:
            continue
        kunci = kunci_label(label)
        if kunci == "nidn/nuptk":
            nidn, _, nuptk = nilai.partition("/")
            identitas.nidn, identitas.nuptk = nidn.strip(), nuptk.strip()
        elif kunci in LABEL_IDENTITAS:
            setattr(identitas, LABEL_IDENTITAS[kunci], nilai)
        else:
            identitas.lainnya[nama_field(label)] = nilai
    return identitas


def bagian_berjudul(halaman, *kata: str):
    """Bagian .bkd-section yang kepalanya memuat salah satu kata."""
    for bagian in halaman.select(".bkd-section"):
        kepala = teks(bagian.select_one(".bkd-section-header")).lower()
        if any(satu in kepala for satu in kata):
            return bagian
    return None


def nilai_masukan(masukan) -> str:
    """Nilai input; nominal yang disensor halaman diambil dari data-real-nya."""
    return (masukan.get("data-real") or masukan.get("value") or "").strip()


def baca_golongan(halaman) -> GolonganPenyetaraan | None:
    """Blok Golongan Penyetaraan; None kalau bagiannya tidak ada."""
    bagian = bagian_berjudul(halaman, "golongan", "kepangkatan")
    if bagian is None:
        return None
    golongan = GolonganPenyetaraan()
    tersembunyi = {
        masukan["name"]: masukan.get("value", "")
        for masukan in bagian.find_all("input", {"type": "hidden"})
        if masukan.get("name")
    }
    golongan.kode_golongan = tersembunyi.get("gol_penyetaraan", "")

    for baris in bagian.select(".form-group"):
        label = teks(baris.find("label"))
        masukan = [satu for satu in baris.find_all("input") if (satu.get("type") or "text") != "hidden"]
        if not label or not masukan:
            continue
        nama = {satu.get("name"): nilai_masukan(satu) for satu in masukan if satu.get("name")}
        if "thn_masa_kerja_penyetaraan" in nama or "bln_masa_kerja_penyetaraan" in nama:
            golongan.masa_kerja_tahun = nama.get("thn_masa_kerja_penyetaraan", "")
            golongan.masa_kerja_bulan = nama.get("bln_masa_kerja_penyetaraan", "")
            nilai = f"{golongan.masa_kerja_tahun} tahun {golongan.masa_kerja_bulan} bulan"
        else:
            nilai = " ".join(nilai_masukan(satu) for satu in masukan).strip()
        golongan.rincian.append({"label": label, "nilai": nilai})
        kunci = LABEL_GOLONGAN.get(kunci_label(label))
        if kunci and not getattr(golongan, kunci):
            setattr(golongan, kunci, nilai)
    return golongan


def baca_persetujuan(sup) -> tuple[list[dict], list[dict]]:
    """Isi modal persetujuan: ringkasan nilai yang disetujui dan teks tiap pernyataan."""
    modal = sup.select_one("#modalCeklistOverlay")
    if modal is None:
        return [], []
    ringkasan = [
        {"label": teks(item.select_one(".bkd-modal-info-label")), "nilai": teks(item.select_one(".bkd-modal-info-val"))}
        for item in modal.select(".bkd-modal-info-item")
    ]
    pernyataan = []
    for item in modal.select(".bkd-ceklist-item"):
        kotak = item.find("input")
        pernyataan.append({
            "id": (kotak.get("id") if kotak else "") or item.get("for", ""),
            "teks": teks(item.select_one(".bkd-ck-text")) or teks(item),
        })
    return ringkasan, pernyataan


def baca_form_unggah(sup) -> tuple[dict, BerkasBkd | None]:
    """Form unggah PDF beserta berkas yang sudah ada di SIBKD."""
    form = sup.select_one("form#uploadLaporanBkdSisterForm")
    if form is None:
        return {"tersedia": False}, None
    tersembunyi = {
        masukan["name"]: masukan.get("value", "")
        for masukan in form.find_all("input", {"type": "hidden"})
        if masukan.get("name")
    }
    berkas_input = form.find("input", {"type": "file"})
    unggah = {
        "tersedia": True,
        "id_periode": tersembunyi.get("id_periode", ""),
        "bln": tersembunyi.get("bln", ""),
        "field_berkas": (berkas_input.get("name") if berkas_input else "") or "berkas",
        "accept": berkas_input.get("accept", "") if berkas_input else "",
        "batas": teks(form.select_one(".bkd-upload-limit")),
    }
    sekarang = form.select_one(".bkd-upload-current")
    tautan = sekarang.find("a", href=True) if sekarang else None
    berkas = BerkasBkd.dari_tautan(tautan["href"], teks(sekarang)) if tautan else None
    return unggah, berkas


def urai_detail(html: str, url: str = "", *, id_periode: str = "", bulan: str = "") -> DetailLaporan:
    """Urai halaman detail jadi DetailLaporan.

    `id_periode` dan `bulan` hanya cadangan kalau halamannya sendiri tidak
    menyebut keduanya (variabel JS dan form unggah lebih dipercaya, karena
    SIBKD mengalihkan mis. 'desember' ke 'november').
    """
    sup = BeautifulSoup(html, "lxml")
    halaman = sup.select_one(".bkd-detail-page")
    if halaman is None:
        raise SibkdError(f"Halaman detail SIBKD tidak dikenali (tidak ada .bkd-detail-page) di {url}")

    skrip = skrip_sebaris(sup)
    variabel: dict[str, str] = {}
    for nama, nilai in POLA_VARIABEL.findall(skrip):
        variabel.setdefault(nama, nilai)

    kartu = baca_kartu_ringkasan(halaman)
    bulan_kartu = kartu.get("bulan pengisian", {})
    status_kartu = kartu.get("status laporan", {})
    kode = next((kelas[3:] for kelas in status_kartu.get("kelas_pil", []) if kelas not in ("is-danger", "is-success")), "")

    unggah, berkas = baca_form_unggah(sup)
    ringkasan, pernyataan = baca_persetujuan(sup)

    kunci = POLA_KUNCI.search(skrip)
    title_kunci = next(
        (elemen.get("title") for elemen in sup.find_all(title=True) if "dikunci" in elemen.get("title", "").lower()),
        "",
    )

    tombol = {}
    for nama, id_tombol in TOMBOL.items():
        elemen = sup.find(id=id_tombol)
        tombol[nama] = elemen is not None and not elemen.has_attr("disabled")

    aksi = halaman.select_one(".bkd-detail-actions")
    return DetailLaporan(
        url=url,
        id_periode=variabel.get("id_periode") or unggah.get("id_periode") or id_periode,
        bulan=variabel.get("bln") or unggah.get("bln") or bulan,
        periode=kartu.get("periode pelaporan", {}).get("nilai", ""),
        nama_bulan=bulan_kartu.get("nilai", ""),
        status_pengisian=bulan_kartu.get("pil", ""),
        jadwal=bulan_kartu.get("jadwal", ""),
        status_laporan=status_kartu.get("pil") or status_kartu.get("nilai", ""),
        kode_status=kode if kode != "empty" else "",
        keterangan_status=status_kartu.get("catatan", ""),
        informasi=[teks(alert) for alert in halaman.select(".alert") if teks(alert)],
        pesan_aksi=teks(aksi.select_one(".bkd-alert")) if aksi else "",
        tombol=tombol,
        terkunci=bool(kunci or title_kunci),
        pesan_kunci=(kunci.group(1) if kunci else title_kunci),
        identitas=baca_identitas(halaman),
        golongan=baca_golongan(halaman),
        ringkasan_persetujuan=ringkasan,
        pernyataan=pernyataan,
        parameter_lanjut=ParameterLanjut(
            gol_penyetaraan=variabel.get("gol_penyetaraan", ""),
            thn_masa_kerja=variabel.get("thn_masa_kerja_penyetaraan", ""),
            bln_masa_kerja=variabel.get("bln_masa_kerja_penyetaraan", ""),
            tgl_acuan=variabel.get("tgl_acuan", ""),
        ),
        berkas=berkas,
        unggah=unggah,
    )
