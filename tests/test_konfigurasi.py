"""Uji akar proyek (berdiri sendiri vs dipakai proyek lain) dan urutan setelan."""

from __future__ import annotations

import pytest

from sibkd_mcp import konfigurasi
from sibkd_mcp.sibkd_client import SIBKD_BASE_URL_BAWAAN, alamat_sibkd


@pytest.fixture(autouse=True)
def lingkungan_bersih():
    """Mulai dari akar bawaan; conftest sudah membuang variabel SIBKD_ mesin ini."""
    konfigurasi.atur_akar_proyek(None)
    konfigurasi.atur_setelan()
    konfigurasi.lupakan_konfigurasi()
    yield
    konfigurasi.atur_akar_proyek(None)
    konfigurasi.atur_setelan()
    konfigurasi.lupakan_konfigurasi()


@pytest.fixture
def akar_tiruan(tmp_path):
    """Akar proyek tiruan, dipasang lewat API yang dipakai proyek pemanggil."""
    konfigurasi.atur_akar_proyek(tmp_path)
    return tmp_path


# --- akar proyek -----------------------------------------------------------


def test_berdiri_sendiri_berakar_di_repositori_ini():
    """Mode pertama: repositori di-clone lalu dijalankan apa adanya."""
    akar = konfigurasi.akar_bawaan()

    assert (akar / "pyproject.toml").is_file()
    assert konfigurasi.akar_proyek() == akar


def test_env_proyek_induk_tidak_ikut_terpungut(tmp_path):
    """Direktori di atas akar tidak pernah ditelusuri.

    Penelusuran ke atas membuat kredensial yang terpakai bergantung pada letak
    folder, dan bisa jadi milik proyek lain.
    """
    induk = tmp_path / "induk"
    aplikasi = induk / "app"
    aplikasi.mkdir(parents=True)
    (induk / ".env").write_text("SIBKD_USERNAME=induk\nSIBKD_PASSWORD=induk\n")
    konfigurasi.atur_akar_proyek(aplikasi)

    assert konfigurasi.akar_proyek() == aplikasi
    assert konfigurasi.berkas_env() == aplikasi / ".env"
    with pytest.raises(konfigurasi.KonfigurasiError):
        konfigurasi.baca_kredensial("SIBKD_USERNAME", "SIBKD_PASSWORD")


def test_proyek_pemanggil_menentukan_akarnya_sendiri(akar_tiruan):
    """Mode kedua: proyek lain memasang paket ini dan menunjuk akarnya."""
    assert konfigurasi.akar_proyek() == akar_tiruan
    assert konfigurasi.dir_data() == akar_tiruan / "data"


def test_akar_lewat_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("SIBKD_AKAR_PROYEK", str(tmp_path))

    assert konfigurasi.akar_proyek() == tmp_path


def test_bkd_akar_proyek_dari_pembungkus_diterima(tmp_path, monkeypatch):
    """Pembungkus /data2/pradita/bkd/bkd menyetel BKD_AKAR_PROYEK untuk semua aplikasinya."""
    monkeypatch.setenv("BKD_AKAR_PROYEK", str(tmp_path))

    assert konfigurasi.akar_proyek() == tmp_path


def test_path_relatif_dihitung_dari_akar(akar_tiruan):
    assert konfigurasi.path_dari_akar("bukti/bkd") == akar_tiruan / "bukti" / "bkd"
    assert konfigurasi.path_dari_akar("/mutlak/x") == konfigurasi.Path("/mutlak/x")


def test_berkas_masukan_dicari_dari_direktori_kerja_dulu(akar_tiruan, tmp_path, monkeypatch):
    kerja = tmp_path / "kerja"
    kerja.mkdir()
    (kerja / "laporan.pdf").write_bytes(b"%PDF")
    monkeypatch.chdir(kerja)

    assert konfigurasi.path_masukan("laporan.pdf") == (kerja / "laporan.pdf").resolve()
    assert konfigurasi.path_masukan("tidak_ada.pdf") == akar_tiruan / "tidak_ada.pdf"


# --- urutan setelan --------------------------------------------------------


def test_setelan_yaml_dibaca(akar_tiruan):
    (akar_tiruan / "sibkd.yaml").write_text("path_bkd: /dosen/bkd_v3\nbatas_kirim_detik: 600\n")

    assert konfigurasi.baca_pengaturan("SIBKD_PATH_BKD", "/dosen/bkdsister_v2") == "/dosen/bkd_v3"
    assert konfigurasi.baca_angka("SIBKD_BATAS_KIRIM_DETIK", 300) == 600


def test_environment_menang_atas_yaml(akar_tiruan, monkeypatch):
    (akar_tiruan / "sibkd.yaml").write_text("path_bkd: /dosen/bkd_v3\n")
    monkeypatch.setenv("SIBKD_PATH_BKD", "/dosen/bkd_v4")

    assert konfigurasi.baca_pengaturan("SIBKD_PATH_BKD") == "/dosen/bkd_v4"


def test_env_berkas_menang_atas_yaml(akar_tiruan):
    (akar_tiruan / "sibkd.yaml").write_text("path_bkd: /dosen/bkd_v3\n")
    (akar_tiruan / ".env").write_text("SIBKD_PATH_BKD=/dosen/dari_env\n")

    assert konfigurasi.baca_pengaturan("SIBKD_PATH_BKD") == "/dosen/dari_env"


def test_setelan_dari_kode_menang_atas_environment(akar_tiruan, monkeypatch):
    """Proyek yang menyetel dari kode tidak boleh berubah karena environment mesin."""
    (akar_tiruan / "sibkd.yaml").write_text("path_bkd: /dosen/bkd_v3\n")
    monkeypatch.setenv("SIBKD_PATH_BKD", "/dosen/bkd_v4")
    konfigurasi.atur_setelan(path_bkd="/dosen/dari_kode")

    assert konfigurasi.baca_pengaturan("SIBKD_PATH_BKD") == "/dosen/dari_kode"


def test_setelan_dari_kode_menerima_kedua_gaya_nama(akar_tiruan):
    konfigurasi.atur_setelan(SIBKD_BASE_URL="https://a.go.id")
    assert konfigurasi.baca_pengaturan("SIBKD_BASE_URL") == "https://a.go.id"

    konfigurasi.atur_setelan(base_url="https://b.go.id")
    assert konfigurasi.baca_pengaturan("SIBKD_BASE_URL") == "https://b.go.id"


def test_kredensial_boleh_datang_dari_kode_tanpa_berkas_env(akar_tiruan):
    """Proyek pemakai tidak wajib menyediakan .env sama sekali."""
    konfigurasi.atur_setelan(SIBKD_USERNAME="0000000000", SIBKD_PASSWORD="rahasia")

    assert konfigurasi.baca_kredensial("SIBKD_USERNAME", "SIBKD_PASSWORD") == {
        "SIBKD_USERNAME": "0000000000",
        "SIBKD_PASSWORD": "rahasia",
    }


def test_setelan_tanpa_yaml_memakai_nilai_bawaan(akar_tiruan):
    assert konfigurasi.berkas_konfigurasi() is None
    assert konfigurasi.baca_pengaturan("SIBKD_PATH_BKD", "/dosen/bkdsister_v2") == "/dosen/bkdsister_v2"


def test_yaml_yang_bukan_pemetaan_ditolak(akar_tiruan):
    (akar_tiruan / "sibkd.yaml").write_text("- satu\n- dua\n")

    with pytest.raises(konfigurasi.KonfigurasiError, match="pemetaan"):
        konfigurasi.baca_pengaturan("SIBKD_PATH_BKD")


def test_angka_tidak_masuk_akal_ditolak_jelas(akar_tiruan, monkeypatch):
    monkeypatch.setenv("SIBKD_UKURAN_MAKS_KB", "sebesar mungkin")

    with pytest.raises(konfigurasi.KonfigurasiError, match="harus berupa angka"):
        konfigurasi.baca_angka("SIBKD_UKURAN_MAKS_KB", 5048)


def test_kesalahan_setelan_bukan_systemexit(akar_tiruan, monkeypatch):
    """Pustaka tidak boleh menghentikan program yang memakainya."""
    monkeypatch.setenv("SIBKD_UKURAN_MAKS_KB", "bukan angka")

    with pytest.raises(Exception) as galat:
        konfigurasi.baca_angka("SIBKD_UKURAN_MAKS_KB", 5048)
    assert not isinstance(galat.value, SystemExit)


# --- alamat instance -------------------------------------------------------


def test_alamat_bawaan_lldikti3(akar_tiruan):
    assert alamat_sibkd() == SIBKD_BASE_URL_BAWAAN


def test_alamat_diambil_dari_sibkd_website(akar_tiruan):
    """.env pemakai biasanya hanya berisi SIBKD_WEBSITE, alamat halaman login."""
    (akar_tiruan / ".env").write_text("SIBKD_WEBSITE=https://sibkd.lain.go.id/login/login\n")

    assert alamat_sibkd() == "https://sibkd.lain.go.id"


def test_base_url_menang_atas_sibkd_website(akar_tiruan):
    (akar_tiruan / ".env").write_text(
        "SIBKD_WEBSITE=https://sibkd.lain.go.id/login/login\nSIBKD_BASE_URL=https://sibkd.baru.go.id/\n"
    )

    assert alamat_sibkd() == "https://sibkd.baru.go.id"
