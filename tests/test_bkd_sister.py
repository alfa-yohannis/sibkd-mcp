"""Uji menu BKD SISTER v2: tabel status, pemilihan bulan, halaman detail, dan aksi tulis.

Semua aksi tulis diuji dengan klien tiruan yang merekam kiriman; tidak ada yang
pernah sampai ke SIBKD.
"""

from __future__ import annotations

import pytest

from conftest import BASE, BERKAS_URL, NIK, NO_HP, NPWP, TGL_LAHIR, KlienTiruan, halaman_bawaan, halaman_detail
from sibkd_mcp import konfigurasi
from sibkd_mcp.bkd_sister import (
    BkdSister,
    BulanTidakDitemukan,
    daftar_jenis_sinkron,
    jenis_sinkron,
    urai_status,
)
from sibkd_mcp.detail_laporan import urai_detail
from sibkd_mcp.sibkd_client import SibkdError

URL_BKD = f"{BASE}/dosen/bkdsister_v2"


@pytest.fixture
def menu(klien) -> BkdSister:
    return BkdSister(klien)


def ganti_detail(klien: KlienTiruan, bulan: str = "oktober", **variasi) -> None:
    """Pasang halaman detail lain untuk satu bulan, mis. yang terkunci atau tertutup."""
    klien.halaman[f"/dosen/bkdsister_v2/detail/20/{bulan}"] = halaman_detail(bulan=bulan, **variasi)


# --- tabel status --------------------------------------------------------------


def test_ringkasan_di_atas_tabel(klien):
    status = urai_status(klien.halaman["/dosen/bkdsister_v2"])

    assert status.tanggal_hari_ini == "20 Oktober 2026"
    assert status.status_pengisian == "Buka"
    assert status.jadwal_berjalan == "2 Oktober 2026 - 24 Oktober 2026"
    assert status.periode_aktif == "Genap 2025/2026"


def test_bulan_dibaca_dari_kartu(klien):
    periode = urai_status(klien.halaman["/dosen/bkdsister_v2"]).cari_periode("20")
    september, oktober, gabungan = periode.bulan[:3]

    assert [satu.slug for satu in periode.bulan] == ["september", "oktober", "november", "januari", "februari"]
    assert september.status_laporan == "Tunda" and september.kode_status == "tunda"
    assert oktober.bulan_berjalan and oktober.terbuka and oktober.status_laporan == "Draft"
    assert gabungan.nomor_bulan == [11, 12] and gabungan.tahun == 2026
    assert gabungan.status_laporan == "Belum dibuat" and gabungan.kode_status == ""
    assert gabungan.jadwal == "Jadwal belum diatur"


def test_berkas_satu_periode(klien):
    status = urai_status(klien.halaman["/dosen/bkdsister_v2"])

    assert status.cari_periode("20").berkas.url == BERKAS_URL
    assert status.cari_periode("20").berkas.diunggah == "2026-10-02 07:57:09"
    assert status.cari_periode("19").berkas is None


def test_periode_aktif_dipilih_menurut_namanya_bukan_urutan(klien):
    """Baris pertama tabel tiruan adalah periode lama; yang aktif baris kedua."""
    status = urai_status(klien.halaman["/dosen/bkdsister_v2"])

    assert status.periode_berjalan().id_periode == "20"
    data = status.sebagai_dict()
    assert data["id_periode_aktif"] == "20"
    assert data["bulan_berjalan"] == "Oktober 2026"
    assert data["jadwal_mulai"] == "2026-10-02" and data["tanggal_hari_ini_iso"] == "2026-10-20"


def test_tampilan_yang_berubah_dilaporkan_jelas():
    with pytest.raises(SibkdError, match="bkd-table"):
        urai_status("<html><body>Halaman baru</body></html>")


# --- pemilihan bulan -------------------------------------------------------------


@pytest.mark.parametrize("bulan, slug", [
    ("Oktober 2026", "oktober"),
    ("oktober", "oktober"),
    ("10", "oktober"),
    ("", "oktober"),
    ("September", "september"),
    ("Desember", "november"),
    ("desember 2026", "november"),
    ("Februari 2027", "februari"),
])
def test_bulan_dicocokkan_dengan_kartu_tabel(menu, bulan, slug):
    assert menu.cari_bulan(bulan).slug == slug


@pytest.mark.parametrize("bulan", ["Maret", "Oktober 2025", "bulan depan"])
def test_bulan_di_luar_periode_ditolak(menu, bulan):
    """SIBKD sendiri menampilkan halaman untuk slug apa pun, jadi penolakannya di sini."""
    with pytest.raises(BulanTidakDitemukan):
        menu.cari_bulan(bulan)


def test_periode_lain_yang_ada_di_tabel(menu):
    assert menu.cari_bulan("april", id_periode="19").url == f"{URL_BKD}/detail/19/april"


def test_periode_lama_yang_tidak_tampil_tetap_bisa_dibuka(menu):
    bulan = menu.cari_bulan("September 2025", id_periode="17")

    assert bulan.url == f"{URL_BKD}/detail/17/september"
    with pytest.raises(BulanTidakDitemukan):
        menu.cari_bulan("", id_periode="17")


# --- halaman detail --------------------------------------------------------------


def test_ringkasan_detail(menu):
    detail = menu.detail("oktober")

    assert detail.id_periode == "20" and detail.bulan == "oktober"
    assert detail.periode == "GENAP 2025/2026"
    assert detail.nama_bulan == "Oktober 2026"
    assert detail.status_pengisian == "Buka" and detail.terbuka
    assert detail.jadwal == "2 Oktober 2026 - 24 Oktober 2026"
    assert detail.status_laporan == "Draft" and detail.kode_status == "draft"
    assert detail.terkunci is False
    assert detail.tombol == {
        "lanjut_proses": True, "tunda_proses": True, "sinkron_identitas": True, "sinkron_homebase": True,
        "sinkron_pendidikan": True, "sinkron_jafung": True, "sinkron_kepangkatan": True,
    }


def test_identitas_utuh_di_objek_tetapi_disamarkan_saat_keluar(menu):
    detail = menu.detail("oktober")
    identitas = detail.identitas

    assert identitas.nidn == "0000000000" and identitas.nuptk == "1111222233334444"
    assert identitas.nik_ktp == NIK and identitas.status_kepegawaian == "NON ASN"

    keluar = detail.sebagai_dict()["identitas"]
    assert keluar["nik_ktp"] == "************1234"
    assert keluar["npwp"] == "***********5678"
    assert keluar["no_hp"] == "********9876"
    assert keluar["tgl_lahir"] == "******1-31"
    assert keluar["nama"] == "KING KONG"


def test_tidak_ada_data_pribadi_utuh_di_keluaran(menu):
    """Keluaran MCP/REST tidak boleh memuat NIK, NPWP, No. HP, atau tanggal lahir utuh di mana pun."""
    teks = repr(menu.detail("oktober").sebagai_dict())

    for rahasia in (NIK, NPWP, NO_HP, TGL_LAHIR):
        assert rahasia not in teks


def test_golongan_penyetaraan_dan_nominal_yang_disensor_halaman(menu):
    golongan = menu.detail("oktober").golongan

    assert golongan.jad_awal == "Asisten Ahli (150), 2020-01-01"
    assert golongan.jad_terakhir == "Lektor (200), 2024-04-01"
    assert golongan.tanggal_acuan == "2026-10-01"
    assert golongan.pangkat_golongan == "Penata (III/c)"
    assert (golongan.masa_kerja_tahun, golongan.masa_kerja_bulan) == ("6", "9")
    # halaman menampilkan "Rp. **********"; nilai aslinya di data-real dan boleh ditampilkan
    assert golongan.tunjangan == "Rp. 1.234.500"
    assert golongan.kode_golongan == "10"


def test_variabel_js_untuk_lanjut_proses(menu):
    parameter = menu.detail("oktober").parameter_lanjut

    assert (parameter.gol_penyetaraan, parameter.thn_masa_kerja, parameter.bln_masa_kerja, parameter.tgl_acuan) == (
        "10", "6", "9", "2026-10-01",
    )


def test_pernyataan_dan_ringkasan_persetujuan(menu):
    detail = menu.detail("oktober")

    assert [satu["id"] for satu in detail.pernyataan] == ["ck1", "ck3", "ck4", "ck5"]
    assert "mengikat secara administratif" in detail.pernyataan[-1]["teks"]
    ringkasan = {satu["label"]: satu["nilai"] for satu in detail.sebagai_dict()["ringkasan_persetujuan"]}
    assert ringkasan["Penyetaraan Pembayaran Tunjangan Sertifikasi"] == "Rp. 1.234.500"
    assert ringkasan["No. HP"] == "********9876"


def test_berkas_dan_form_unggah(menu):
    detail = menu.detail("oktober")

    assert detail.berkas.url == BERKAS_URL and detail.berkas.diunggah == "2026-10-02 07:57:09"
    assert detail.unggah == {
        "tersedia": True, "id_periode": "20", "bln": "oktober", "field_berkas": "berkas",
        "accept": "application/pdf", "batas": "Ukuran maks. 5 MB per file",
    }


def test_laporan_terkunci_dikenali_dari_skrip(menu):
    detail = menu.detail("september")

    assert detail.terkunci is True
    assert detail.pesan_kunci == "Laporan telah dikunci oleh Admin PT"
    assert detail.status_laporan == "Tunda" and not detail.terbuka
    assert detail.pesan_aksi == "Pelaporan BKD untuk bulan ini ditutup."
    assert not any(detail.tombol.values())


def test_kunci_di_dalam_komentar_js_tidak_dihitung():
    detail = urai_detail(halaman_detail(kunci_dalam_komentar=True))

    assert detail.terkunci is False


def test_bulan_gabungan_yang_belum_dibuat(menu):
    detail = menu.detail("Desember")

    assert detail.bulan == "november" and detail.nama_bulan == "November - Desember 2026"
    assert detail.identitas is None and detail.golongan is None and detail.berkas is None
    assert any("Penggabungan" in satu for satu in detail.informasi)
    assert detail.unggah == {"tersedia": False}


def test_halaman_yang_bukan_detail_ditolak():
    with pytest.raises(SibkdError, match="bkd-detail-page"):
        urai_detail("<html><body>login</body></html>", f"{BASE}/login/login")


# --- unggah --------------------------------------------------------------------------


def test_unggah_uji_coba_tidak_mengirim_apa_pun(menu, klien, pdf):
    hasil = menu.unggah_laporan("oktober", pdf, uji_coba=True)

    assert klien.terkirim == []
    assert hasil["ok"] is True and hasil["uji_coba"] is True and hasil["terkirim"] is False
    assert hasil["url"] == f"{URL_BKD}/upload_laporan_bkd_sister"
    assert hasil["muatan"]["id_periode"] == "20" and hasil["muatan"]["bln"] == "oktober"
    assert hasil["muatan"]["berkas"]["nama"] == "laporan.pdf"
    assert any("tergantikan" in satu for satu in hasil["peringatan"])


def test_unggah_sungguhan_mengirim_form_yang_sama_dengan_halaman(menu, klien, pdf):
    hasil = menu.unggah_laporan("oktober", pdf)

    assert hasil["ok"] is True and hasil["terkirim"] is True and hasil["pesan"] == "Berhasil"
    kiriman = klien.terkirim[0]
    assert kiriman["url"] == f"{URL_BKD}/upload_laporan_bkd_sister"
    assert kiriman["data"] == {"id_periode": "20", "bln": "oktober"}
    nama, isi, tipe = kiriman["files"]["berkas"]
    assert (nama, tipe) == ("laporan.pdf", "application/pdf") and isi.startswith(b"%PDF")
    assert kiriman["referer"].endswith("/detail/20/oktober")


def test_unggah_bukan_pdf_ditahan(menu, klien, tmp_path):
    palsu = tmp_path / "laporan.pdf"
    palsu.write_text("bukan pdf")

    hasil = menu.unggah_laporan("oktober", palsu)
    assert hasil["ok"] is False and klien.terkirim == []
    assert any("bukan PDF" in satu for satu in hasil["hambatan"])


def test_unggah_terlalu_besar_ditahan(menu, klien, pdf):
    konfigurasi.atur_setelan(ukuran_maks_kb=0)

    hasil = menu.unggah_laporan("oktober", pdf)
    assert hasil["ok"] is False and klien.terkirim == []
    assert any("melebihi batas" in satu for satu in hasil["hambatan"])


def test_unggah_berkas_yang_tidak_ada_ditahan(menu, klien, tmp_path):
    hasil = menu.unggah_laporan("oktober", tmp_path / "hilang.pdf")

    assert hasil["ok"] is False and klien.terkirim == []


def test_unggah_di_luar_jadwal_atau_terkunci_ditahan(menu, klien, pdf):
    hasil = menu.unggah_laporan("september", pdf)

    assert hasil["ok"] is False and klien.terkirim == []
    assert "Laporan telah dikunci oleh Admin PT" in hasil["hambatan"]
    assert any("Tutup" in satu for satu in hasil["hambatan"])


# --- lanjut proses -------------------------------------------------------------------


def test_lanjut_uji_coba_mengembalikan_pernyataan_dan_alamat(menu, klien):
    hasil = menu.lanjut_proses("oktober", uji_coba=True)

    assert klien.terkirim == []
    assert hasil["ok"] is True and hasil["perlu_persetujuan"] is True
    assert hasil["url"] == f"{URL_BKD}/lanjut_proses/20/oktober/10/6/9/2026-10-01"
    assert len(hasil["pernyataan"]) == 4
    assert {satu["label"] for satu in hasil["ringkasan_persetujuan"]} >= {"Pangkat/Gol. Penyetaraan"}
    assert "setuju_pernyataan=True" in hasil["pesan"]


def test_lanjut_tanpa_persetujuan_tidak_dikirim(menu, klien):
    hasil = menu.lanjut_proses("oktober")

    assert hasil["ok"] is False and klien.terkirim == []
    assert any("setuju_pernyataan" in satu for satu in hasil["hambatan"])


def test_lanjut_dengan_persetujuan_dikirim_tanpa_badan(menu, klien):
    hasil = menu.lanjut_proses("oktober", setuju_pernyataan=True)

    assert hasil["terkirim"] is True and hasil["ok"] is True
    assert klien.terkirim == [{
        "url": f"{URL_BKD}/lanjut_proses/20/oktober/10/6/9/2026-10-01",
        "data": None, "files": None, "referer": f"{URL_BKD}/detail/20/oktober",
    }]


def test_lanjut_mengganti_nilai_kosong_dengan_nol_seperti_halaman(menu, klien):
    ganti_detail(klien, gol="", tgl_acuan="")
    hasil = menu.lanjut_proses("oktober", uji_coba=True)

    assert hasil["url"] == f"{URL_BKD}/lanjut_proses/20/oktober/0/6/9/"
    assert len(hasil["peringatan"]) == 2


def test_lanjut_tanpa_berkas_ditahan(menu, klien):
    ganti_detail(klien, berkas=False)
    hasil = menu.lanjut_proses("oktober", setuju_pernyataan=True)

    assert hasil["ok"] is False and klien.terkirim == []
    assert any("Belum ada PDF" in satu for satu in hasil["hambatan"])


def test_lanjut_pada_bulan_tertutup_ditahan_walau_disetujui(menu, klien):
    hasil = menu.lanjut_proses("september", setuju_pernyataan=True)

    assert hasil["ok"] is False and klien.terkirim == []
    assert any("tombol Lanjut Proses" in satu for satu in hasil["hambatan"])


def test_balasan_gagal_dari_sibkd_diteruskan(klien):
    klien.balasan_kirim = {"ok": False, "status": "error", "pesan": "Periode sudah ditutup", "status_http": 200}
    hasil = BkdSister(klien).lanjut_proses("oktober", setuju_pernyataan=True)

    assert hasil["terkirim"] is True and hasil["ok"] is False
    assert hasil["pesan"] == "Periode sudah ditutup"


# --- tunda dan sinkron -----------------------------------------------------------------


def test_tunda_uji_coba_dan_sungguhan(menu, klien):
    uji = menu.tunda_proses("oktober", uji_coba=True)
    assert uji["url"] == f"{URL_BKD}/tunda_proses/20/oktober" and klien.terkirim == []

    menu.tunda_proses("oktober")
    assert [satu["url"] for satu in klien.terkirim] == [f"{URL_BKD}/tunda_proses/20/oktober"]


@pytest.mark.parametrize("jenis, alamat", [
    ("identitas", "update_miror_sister/20/oktober"),
    ("homebase", "update_homebase_sister/20/oktober"),
    ("pendidikan", "update_rwy_pend_sister20/oktober"),
    ("jafung", "api_jafung/20/oktober"),
    ("kepangkatan", "api_kepangkatan_nonapi/20/oktober"),
])
def test_alamat_sinkron_meniru_halaman(menu, klien, jenis, alamat):
    hasil = menu.sinkronkan("oktober", jenis, uji_coba=True)

    assert hasil["url"] == f"{URL_BKD}/{alamat}"
    assert hasil["ok"] is True and klien.terkirim == []


def test_sinkron_pendidikan_diberi_peringatan_soal_garis_miring(menu):
    assert menu.sinkronkan("oktober", "pendidikan", uji_coba=True)["peringatan"]


def test_sinkron_sungguhan_tanpa_badan(menu, klien):
    menu.sinkronkan("oktober", "jafung")

    assert klien.terkirim[0]["url"] == f"{URL_BKD}/api_jafung/20/oktober"
    assert klien.terkirim[0]["data"] is None


def test_sinkron_laporan_terkunci_ditahan(menu, klien):
    hasil = menu.sinkronkan("september", "jafung")

    assert hasil["ok"] is False and klien.terkirim == []
    assert "Laporan telah dikunci oleh Admin PT" in hasil["hambatan"]


def test_sinkron_banyak_membaca_halaman_sekali(menu, klien, monkeypatch):
    dibaca = []
    asli = klien.ambil_halaman
    monkeypatch.setattr(klien, "ambil_halaman", lambda path: dibaca.append(path) or asli(path))

    hasil = menu.sinkronkan_banyak("oktober", "semua", uji_coba=True)
    assert [satu["jenis"] for satu in hasil] == ["identitas", "homebase", "pendidikan", "jafung", "kepangkatan"]
    assert len([path for path in dibaca if "/detail/" in path]) == 1


def test_jenis_sinkron_dan_sebutan_lainnya():
    assert jenis_sinkron("Jafung") == "jafung"
    assert jenis_sinkron("jabatan fungsional") == "jafung"
    assert jenis_sinkron("golongan") == "kepangkatan"
    assert daftar_jenis_sinkron("jafung, pangkat, jafung") == ["jafung", "kepangkatan"]
    with pytest.raises(ValueError, match="Pilihan"):
        jenis_sinkron("nilai")
    with pytest.raises(ValueError):
        daftar_jenis_sinkron(" , ")


def test_alamat_endpoint_bisa_diganti_lewat_setelan(menu):
    """Kalau SIBKD memperbaiki garis miringnya, cukup ubah sibkd.yaml."""
    konfigurasi.atur_setelan(endpoint_sinkron_pendidikan="update_rwy_pend_sister/{id_periode}/{bulan}")

    assert menu.sinkronkan("oktober", "pendidikan", uji_coba=True)["url"] == (
        f"{URL_BKD}/update_rwy_pend_sister/20/oktober"
    )


def test_templat_endpoint_yang_salah_ditolak_jelas(menu):
    konfigurasi.atur_setelan(endpoint_tunda="tunda_proses/{periode}")

    with pytest.raises(konfigurasi.KonfigurasiError, match="endpoint_tunda"):
        menu.tunda_proses("oktober", uji_coba=True)


# --- unduh -------------------------------------------------------------------------------


def test_unduh_laporan_periode_aktif(menu, klien, tmp_path):
    hasil = menu.unduh_laporan(tmp_path)

    assert klien.diunduh == [(BERKAS_URL, tmp_path / "File202610020757090000000000.pdf")]
    assert hasil["berkas"] == [str(tmp_path / "File202610020757090000000000.pdf")]
    assert menu.unduh_laporan(tmp_path)["dilewati"] == hasil["berkas"]


def test_unduh_periode_tanpa_berkas(menu, klien, tmp_path):
    hasil = menu.unduh_laporan(tmp_path, id_periode="19")

    assert hasil["berkas"] == [] and "Belum ada" in hasil["pesan"]
    assert klien.diunduh == []


def test_halaman_bawaan_tidak_berubah_antar_uji():
    """Penjaga kecil: perkakas uji menghasilkan halaman baru setiap kali."""
    assert halaman_bawaan() == halaman_bawaan()
